"""Project timeline: task dates, dependencies and baselines (P2.8).

GET   /projects/{id}/timeline   tasks the caller may see, phases, baseline variance
PATCH /tasks/{id}/schedule      start/due dates and predecessors; successors ripple
POST  /projects/{id}/baseline   freeze every task's current dates for comparison

Scheduling rules live in core.scheduling. Changing dates or dependencies needs
`projects.update` on the project, because a change can move other people's tasks.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field

from core import scheduling as sch
from core.access_control import get_visible_project, get_visible_task, merge_query, task_visibility_query
from core.audit import audit
from core.deps import require_user
from core.helpers import iso_now, new_id
from core.rbac import has_permission
from core.scoped_db import sdb
from core.tenancy import user_org_id

router = APIRouter()

_FIELDS = {"_id": 0, "id": 1, "title": 1, "start_date": 1, "due_date": 1, "depends_on": 1,
           "status": 1, "status_detail": 1, "baseline": 1, "assignee_name": 1, "priority": 1,
           "category": 1, "area": 1, "project_id": 1}


class ScheduleIn(BaseModel):
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    depends_on: Optional[List[str]] = Field(default=None, max_length=30)


def _event(user: dict, details: str) -> dict:
    return {"id": new_id("evt_"), "event": "updated", "details": details, "actor": user.get("user_id"),
            "actor_name": user.get("name"), "at": iso_now()}


async def _project_tasks(project_id: str) -> Dict[str, dict]:
    rows = await sdb.tasks.find({"project_id": project_id}, _FIELDS).to_list(5000)
    return {t["id"]: t for t in rows}


async def apply_moves(user: dict, tasks: Dict[str, dict], moved: Dict[str, dict], cause: str) -> List[dict]:
    """Persist ripple moves with a timeline note on each task; returns what moved."""
    out = []
    for tid, dates in moved.items():
        await sdb.tasks.update_one({"id": tid}, {
            "$set": {**dates, "updated_at": iso_now()},
            "$push": {"timeline": _event(user, f"Moved to {dates['start_date']} - {dates['due_date']} "
                                               f"because {cause} changed")}})
        out.append({"id": tid, "title": tasks[tid].get("title"), **dates})
    if out:
        try:
            from core.google_calendar import sync_sources
            await sync_sources(user_org_id(user), "task", [m["id"] for m in out])
        except Exception:  # noqa: BLE001 - calendar sync retries on its own
            pass
    return out


async def ripple_after_edit(user: dict, task_id: str) -> List[dict]:
    """Called after an ordinary task edit changed its dates: move its successors."""
    task = await sdb.tasks.find_one({"id": task_id}, _FIELDS)
    if not task or not task.get("project_id"):
        return []
    tasks = await _project_tasks(task["project_id"])
    if not any(task_id in (t.get("depends_on") or []) for t in tasks.values()):
        return []
    moved = sch.reschedule(tasks, [task_id])
    return await apply_moves(user, tasks, moved, f"\"{task.get('title') or 'a predecessor'}\"")


@router.get("/projects/{project_id}/timeline")
async def project_timeline(project_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    project = await get_visible_project(user, project_id)
    q = merge_query({"project_id": project_id}, await task_visibility_query(user))
    tasks = await sdb.tasks.find(q, _FIELDS).to_list(5000)
    phases = await sdb.project_phases.find(
        {"project_id": project_id},
        {"_id": 0, "id": 1, "name": 1, "order": 1, "planned_start": 1, "planned_end": 1, "status": 1}
    ).sort("order", 1).to_list(100)
    behind, worst = 0, 0
    for t in tasks:
        start, due = sch.span(t)
        t["start"], t["finish"] = (start.isoformat() if start else None), (due.isoformat() if due else None)
        t["variance_days"] = sch.baseline_variance(t)
        if (t["variance_days"] or 0) > 0 and t.get("status") != "done":
            behind += 1
            worst = max(worst, t["variance_days"])
    dated = [t for t in tasks if t["finish"]]
    return {
        "project": {"id": project_id, "name": project.get("name"),
                    "baseline_set_at": project.get("baseline_set_at")},
        "tasks": sorted(dated, key=lambda t: (t["start"], t["finish"], t.get("title") or "")),
        "undated": [{"id": t["id"], "title": t.get("title")} for t in tasks if not t["finish"]],
        "phases": phases,
        "summary": {"dated": len(dated), "undated": len(tasks) - len(dated),
                    "behind_baseline": behind, "worst_slip_days": worst},
        "can_edit": has_permission(user, "projects.update"),
    }


@router.patch("/tasks/{task_id}/schedule")
async def set_schedule(task_id: str, payload: ScheduleIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    task = await get_visible_task(user, task_id, "tasks.update")
    if not task.get("project_id"):
        raise HTTPException(400, "Add the task to a project to schedule it")
    await get_visible_project(user, task["project_id"], "projects.update")
    tasks = await _project_tasks(task["project_id"])
    start = sch.parse(payload.start_date) if payload.start_date else None
    due = sch.parse(payload.due_date) if payload.due_date else None
    if (payload.start_date and not start) or (payload.due_date and not due):
        raise HTTPException(400, "Dates must be YYYY-MM-DD")
    if start and due and due < start:
        raise HTTPException(400, "The task can't end before it starts")
    deps = list(dict.fromkeys(payload.depends_on if payload.depends_on is not None
                              else (task.get("depends_on") or [])))
    for d in deps:
        if d not in tasks:
            raise HTTPException(400, "A task it depends on is not in this project")
    if sch.creates_cycle(tasks, task_id, deps):
        raise HTTPException(400, "That would make a loop: a task can't wait for itself")
    updates = {"start_date": start.isoformat() if start else None,
               "due_date": due.isoformat() if due else None, "depends_on": deps}
    tasks[task_id] = {**tasks[task_id], **updates}
    # Predecessors first (may push this task later), then this task's successors.
    moved = sch.reschedule(tasks, deps + [task_id])
    own = moved.pop(task_id, None)
    if own:
        updates.update(own)
    details = f"Schedule: {updates['start_date'] or '—'} to {updates['due_date'] or '—'}"
    if deps:
        details += f"; waits for {len(deps)} task{'s' if len(deps) != 1 else ''}"
    await sdb.tasks.update_one({"id": task_id}, {"$set": {**updates, "updated_at": iso_now(),
                                                          "updated_by": user["user_id"]},
                                                 "$push": {"timeline": _event(user, details)}})
    title = task.get("title") or "this task"
    out = await apply_moves(user, tasks, moved, f"\"{title}\"")
    try:
        from core.google_calendar import sync_source
        await sync_source(user_org_id(user), "task", task_id)
    except Exception:  # noqa: BLE001
        pass
    return {"task": await sdb.tasks.find_one({"id": task_id}, {"_id": 0}),
            "moved_self": bool(own), "moved": out}


@router.post("/projects/{project_id}/baseline")
async def save_baseline(project_id: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """Freeze the current plan so later slips show against it."""
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id, "projects.update")
    tasks = await _project_tasks(project_id)
    now = iso_now()
    count = 0
    for t in tasks.values():
        start, due = sch.span(t)
        if not due:
            continue
        await sdb.tasks.update_one({"id": t["id"]}, {"$set": {"baseline": {
            "start_date": start.isoformat(), "due_date": due.isoformat(), "set_at": now}}})
        count += 1
    await sdb.projects.update_one({"id": project_id}, {"$set": {"baseline_set_at": now,
                                                                "baseline_set_by": user["user_id"]}})
    await audit(user, "project.baseline", target=project_id, target_type="project", meta={"tasks": count})
    return {"baseline_set_at": now, "tasks": count}


