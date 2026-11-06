"""Project phases from architecture-practice templates (PRJ-01).

A project gets an editable, tenant-scoped phase plan copied from a built-in
template (Consultancy design services or Turnkey design-and-build). Each phase
carries planned/actual dates, a fee share and a deliverables checklist.
Optionally one fee milestone per phase is created in the existing payment
milestone (Collections Due) workflow, only when the project has none yet.

Every route resolves the project through `get_visible_project`, which applies
the permission check, tenant scope and assignment visibility.
"""
from datetime import date, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from core.access_control import get_visible_project, require_permission
from core.audit import audit
from core.deps import require_user
from core.helpers import business_today, iso_now, new_id
from core.scoped_db import sdb
from core.tenancy import user_org_id

router = APIRouter()

PHASE_STATUSES = ("not_started", "in_progress", "done")

PHASE_TEMPLATES = {
    "consultancy": {
        "label": "Architecture & interior design services",
        "description": "Brief to handover for a design-fee engagement.",
        "phases": [
            ("Brief & requirements", 5, 2, ["Client brief", "Site survey & measurements", "Area programme"]),
            ("Concept design", 15, 3, ["Concept plans", "Mood boards", "3D views"]),
            ("Schematic design", 15, 3, ["Schematic plans & elevations", "Preliminary cost estimate"]),
            ("Design development", 20, 4, ["Detailed drawings", "Materials & finishes schedule", "Lighting & electrical layouts"]),
            ("Statutory approvals", 10, 4, ["Submission drawings", "Approval received"]),
            ("Construction documentation", 20, 4, ["Working (GFC) drawings", "BOQ & specifications", "Tender package"]),
            ("Site supervision", 10, 12, ["Site visit reports", "Snag list"]),
            ("Handover & closeout", 5, 1, ["As-built drawings", "Handover checklist", "Warranties & manuals"]),
        ],
    },
    "turnkey": {
        "label": "Design & build (turnkey)",
        "description": "Design through procurement, execution and handover.",
        "phases": [
            ("Brief & site survey", 5, 1, ["Client brief", "Site measurements"]),
            ("Design & approvals", 15, 4, ["Approved layouts", "3D views", "Materials selection"]),
            ("BOQ & quotation sign-off", 10, 2, ["Final BOQ", "Signed quotation"]),
            ("Procurement", 20, 3, ["Purchase orders issued", "Materials received"]),
            ("Site execution", 40, 10, ["Civil & services", "Carpentry & finishes", "Site progress reports"]),
            ("Snagging & handover", 10, 2, ["Snag list closed", "Handover checklist", "Warranties"]),
        ],
    },
}


def _template_payload(key: str) -> dict:
    tpl = PHASE_TEMPLATES[key]
    return {
        "key": key, "label": tpl["label"], "description": tpl["description"],
        "phases": [{"name": n, "fee_pct": f, "weeks": w, "deliverables": d} for n, f, w, d in tpl["phases"]],
        "total_weeks": sum(w for _, _, w, _ in tpl["phases"]),
    }


def build_phase_docs(template_key: str, project_id: str, start: date) -> List[dict]:
    """Pure: sequential planned dates from `start`, one doc per template phase."""
    docs, cursor = [], start
    for order, (name, fee_pct, weeks, deliverables) in enumerate(PHASE_TEMPLATES[template_key]["phases"]):
        end = cursor + timedelta(weeks=weeks) - timedelta(days=1)
        docs.append({
            "id": new_id("ph_"), "project_id": project_id, "order": order, "name": name,
            "template": template_key, "status": "not_started", "fee_pct": fee_pct,
            "planned_start": cursor.isoformat(), "planned_end": end.isoformat(),
            "actual_start": None, "actual_end": None, "notes": "",
            "deliverables": [{"id": new_id("dl_"), "name": d, "done": False} for d in deliverables],
        })
        cursor = end + timedelta(days=1)
    return docs


def fee_milestone_amounts(fee: float, percents: List[float]) -> List[float]:
    """Exact paise per phase; the last phase takes the remainder so they sum to `fee`."""
    from core.money import percent_of, round_paise
    amounts = [percent_of(fee, p) for p in percents]
    if amounts and abs(sum(percents) - 100) < 0.001:
        amounts[-1] = round_paise(fee) - sum(amounts[:-1], round_paise(0))
    return [float(a) for a in amounts]


def phase_summary(phases: List[dict]) -> dict:
    total = len(phases)
    done = sum(1 for p in phases if p.get("status") == "done")
    current = next((p for p in phases if p.get("status") == "in_progress"), None) \
        or next((p for p in phases if p.get("status") == "not_started"), None)
    deliverables = [d for p in phases for d in (p.get("deliverables") or [])]
    today = business_today().isoformat()
    overdue = [p["name"] for p in phases
               if p.get("status") != "done" and (p.get("planned_end") or "9999") < today]
    return {
        "total": total, "done": done,
        "progress_pct": round(done * 100 / total) if total else 0,
        "deliverables_done": sum(1 for d in deliverables if d.get("done")),
        "deliverables_total": len(deliverables),
        "current_phase": current["name"] if current else None,
        "overdue_phases": overdue,
    }


def _valid_date(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError("Dates must be YYYY-MM-DD")


class ApplyTemplateIn(BaseModel):
    template: Literal["consultancy", "turnkey"]
    start_date: Optional[str] = None
    create_fee_milestones: bool = False

    @field_validator("start_date")
    @classmethod
    def _check_start(cls, value):
        return _valid_date(value)


class DeliverableIn(BaseModel):
    id: Optional[str] = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    done: bool = False


class PhaseUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    status: Optional[Literal["not_started", "in_progress", "done"]] = None
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    deliverables: Optional[List[DeliverableIn]] = Field(default=None, max_length=40)

    @field_validator("planned_start", "planned_end")
    @classmethod
    def _check_dates(cls, value):
        return _valid_date(value)


async def _phases(project_id: str) -> List[dict]:
    return await sdb.project_phases.find({"project_id": project_id}, {"_id": 0}).sort("order", 1).to_list(100)


@router.get("/project-phase-templates")
async def list_templates(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    require_permission(user, "projects.read")
    return [_template_payload(k) for k in PHASE_TEMPLATES]


@router.get("/projects/{project_id}/phases")
async def list_project_phases(project_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id)
    phases = await _phases(project_id)
    return {"phases": phases, "summary": phase_summary(phases)}


@router.post("/projects/{project_id}/phases/apply")
async def apply_template(project_id: str, payload: ApplyTemplateIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    project = await get_visible_project(user, project_id, "projects.update")
    if await sdb.project_phases.find_one({"project_id": project_id}, {"_id": 0, "id": 1}):
        raise HTTPException(409, "This project already has phases. Edit them instead of applying a template again.")
    start = date.fromisoformat(payload.start_date or project.get("start_date") or business_today().isoformat())
    docs = build_phase_docs(payload.template, project_id, start)
    milestones = []
    if payload.create_fee_milestones:
        fee = float(project.get("budget") or 0)
        if fee <= 0:
            raise HTTPException(400, "Set the project fee/budget before creating fee milestones.")
        if await sdb.payment_milestones.find_one({"project_id": project_id}, {"_id": 0, "id": 1}):
            raise HTTPException(409, "This project already has payment milestones; fee milestones were not created.")
        amounts = fee_milestone_amounts(fee, [d["fee_pct"] for d in docs])
        for phase, amount in zip(docs, amounts):
            if amount <= 0:
                continue
            ms = {
                "id": new_id("ms_"), "project_id": project_id, "org_id": user_org_id(user),
                "name": f"{phase['name']} fee", "percent": phase["fee_pct"], "amount": amount,
                "due_date": phase["planned_end"], "status": "pending", "phase_id": phase["id"],
                "notes": "Created from the project phase plan", "created_at": iso_now(),
                "created_by": user["user_id"],
            }
            phase["milestone_id"] = ms["id"]
            milestones.append(ms)
    for doc in docs:
        doc["created_at"] = iso_now()
        doc["created_by"] = user["user_id"]
    await sdb.project_phases.insert_many([dict(d) for d in docs])
    if milestones:
        await sdb.payment_milestones.insert_many([dict(m) for m in milestones])
    await audit(user, "project.phases_applied", target=project_id, target_type="project",
                meta={"template": payload.template, "phases": len(docs), "fee_milestones": len(milestones)})
    phases = await _phases(project_id)
    return {"phases": phases, "summary": phase_summary(phases), "milestones_created": len(milestones)}


@router.patch("/projects/{project_id}/phases/{phase_id}")
async def update_phase(project_id: str, phase_id: str, payload: PhaseUpdateIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id, "projects.update")
    phase = await sdb.project_phases.find_one({"id": phase_id, "project_id": project_id}, {"_id": 0})
    if not phase:
        raise HTTPException(404, "Phase not found")
    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "deliverables" in patch:
        patch["deliverables"] = [
            {"id": d.get("id") or new_id("dl_"), "name": d["name"].strip(), "done": bool(d["done"])}
            for d in patch["deliverables"]
        ]
    start = patch.get("planned_start", phase.get("planned_start"))
    end = patch.get("planned_end", phase.get("planned_end"))
    if start and end and end < start:
        raise HTTPException(400, "Planned end cannot be before planned start")
    status = patch.get("status")
    today = business_today().isoformat()
    if status and status != phase.get("status"):
        if status == "in_progress" and not phase.get("actual_start"):
            patch["actual_start"] = today
        if status == "done":
            patch["actual_end"] = today
            patch.setdefault("actual_start", phase.get("actual_start") or today)
        if status == "not_started":
            patch["actual_start"] = None
            patch["actual_end"] = None
    patch["updated_at"] = iso_now()
    patch["updated_by"] = user["user_id"]
    await sdb.project_phases.update_one({"id": phase_id, "project_id": project_id}, {"$set": patch})
    await audit(user, "project.phase_updated", target=phase_id, target_type="project_phase",
                meta={"project_id": project_id, "fields": sorted(k for k in patch if not k.startswith("updated"))})
    phases = await _phases(project_id)
    return {"phases": phases, "summary": phase_summary(phases)}


@router.delete("/projects/{project_id}/phases/{phase_id}")
async def delete_phase(project_id: str, phase_id: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id, "projects.update")
    phase = await sdb.project_phases.find_one({"id": phase_id, "project_id": project_id}, {"_id": 0})
    if not phase:
        raise HTTPException(404, "Phase not found")
    if phase.get("status") != "not_started":
        raise HTTPException(409, "Only phases that have not started can be removed.")
    if phase.get("milestone_id") and await sdb.payment_milestones.find_one(
            {"id": phase["milestone_id"], "status": {"$ne": "pending"}}, {"_id": 0, "id": 1}):
        raise HTTPException(409, "This phase's fee milestone has payments; correct it from Collections first.")
    await sdb.project_phases.delete_one({"id": phase_id, "project_id": project_id})
    await audit(user, "project.phase_removed", target=phase_id, target_type="project_phase",
                meta={"project_id": project_id, "name": phase.get("name")})
    phases = await _phases(project_id)
    return {"phases": phases, "summary": phase_summary(phases)}
