"""Timesheets, cost rates and project profitability (P2.4 / P2.5).

* Everyone logs their own hours per day against projects they can see, optionally
  a project phase, billable or not. A week is saved as a grid and submitted.
* Approvers (``attendance.approve``) approve or return a submitted week. Nobody
  approves their own week except an Admin. Approval snapshots the person's hourly
  cost on each entry so later salary changes never rewrite history; approved
  weeks are locked.
* Hourly cost: the rate HR/finance set on the employee, else monthly gross pay x 12
  / (weekly hours x 52). Rates and costs are shown only to finance/payroll roles.
* Project time: hours by phase and person. Profitability (finance roles): fee,
  invoiced, vendor bills, project expenses and approved labour cost.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field

from core.access_control import get_visible_project, project_visibility_query
from core.audit import audit
from core.deps import require_user
from core.helpers import business_today, iso_now, new_id
from core.rbac import has_any_permission, has_permission
from core.scoped_db import sdb
from core.tenancy import is_super_admin

router = APIRouter()

MAX_DAY_HOURS = 24.0
LOCKED = ("submitted", "approved")


# ---------------------------------------------------------------- pure helpers
def week_start(value) -> date:
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return d - timedelta(days=d.weekday())


def hourly_cost(employee: Optional[dict]) -> Optional[float]:
    """Explicit rate, else derived from monthly gross pay and weekly hours."""
    e = employee or {}
    if e.get("cost_rate_hourly"):
        return round(float(e["cost_rate_hourly"]), 2)
    monthly = float((e.get("salary") or {}).get("gross_monthly") or 0) or float(e.get("monthly_salary") or 0)
    weekly = float(e.get("weekly_hours") or 45) or 45
    if monthly <= 0:
        return None
    return round(monthly * 12 / (weekly * 52), 2)


def week_status(entries: List[dict]) -> str:
    states = {e.get("status") for e in entries}
    if not entries:
        return "empty"
    if "rejected" in states:
        return "rejected"
    if states == {"approved"}:
        return "approved"
    if "submitted" in states or "approved" in states:
        return "submitted"
    return "draft"


def can_see_costs(user: dict) -> bool:
    return has_any_permission(user, "*.*", "finance.read", "payroll.read")


def _strip_costs(entry: dict, user: dict) -> dict:
    if can_see_costs(user):
        return entry
    return {k: v for k, v in entry.items() if k not in ("cost_rate", "cost")}


# ---------------------------------------------------------------- models
class EntryIn(BaseModel):
    date: str
    project_id: str = Field(min_length=1, max_length=60)
    phase_id: Optional[str] = Field(default=None, max_length=60)
    hours: float = Field(gt=0, le=MAX_DAY_HOURS)
    billable: bool = True
    note: str = Field(default="", max_length=300)


class WeekIn(BaseModel):
    week: str
    entries: List[EntryIn] = Field(default_factory=list, max_length=200)


class WeekRef(BaseModel):
    week: str


class DecisionIn(BaseModel):
    user_id: str
    week: str
    reason: str = Field(default="", max_length=300)


class CostRateIn(BaseModel):
    cost_rate_hourly: Optional[float] = Field(default=None, ge=0, le=100000)


def _require_workspace_member(user: dict) -> None:
    """Hours belong to people in a workspace; platform staff outside one have none."""
    if is_super_admin(user) and not user.get("org_id"):
        raise HTTPException(403, "Open a workspace to log time")


async def _sum(cursor, field: str) -> float:
    total = 0.0
    async for row in cursor:
        total += float(row.get(field) or 0)
    return total


def _week(value: str) -> date:
    try:
        return week_start(value)
    except ValueError:
        raise HTTPException(400, "week must be a date (YYYY-MM-DD)")


async def _entries(user_id: str, week: date) -> List[dict]:
    return await sdb.time_entries.find({"user_id": user_id, "week": week.isoformat()},
                                       {"_id": 0}).sort("date", 1).to_list(500)


async def _employee_for(user_id: str) -> Optional[dict]:
    u = await sdb.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    terms = [{"user_id": user_id}] + ([{"email": u["email"]}] if (u or {}).get("email") else [])
    return await sdb.employees.find_one({"$or": terms}, {"_id": 0})


# ---------------------------------------------------------------- my week
@router.get("/timesheets/week")
async def get_week(request: Request, week: Optional[str] = None, user_id: Optional[str] = None,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    target = user_id or user["user_id"]
    if target != user["user_id"] and not has_permission(user, "attendance.approve"):
        raise HTTPException(403, "You can only view your own timesheet")
    start = _week(week or business_today().isoformat())
    entries = [_strip_costs(e, user) for e in await _entries(target, start)]
    projects = await sdb.projects.find(
        {**(await project_visibility_query(user)), "archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1}).sort("name", 1).to_list(500)
    ids = [p["id"] for p in projects]
    phases = await sdb.project_phases.find({"project_id": {"$in": ids}},
                                           {"_id": 0, "id": 1, "project_id": 1, "name": 1, "order": 1}
                                           ).sort("order", 1).to_list(3000)
    return {
        "week": start.isoformat(), "days": [(start + timedelta(days=i)).isoformat() for i in range(7)],
        "user_id": target, "status": week_status(entries), "entries": entries,
        "total_hours": round(sum(float(e.get("hours") or 0) for e in entries), 2),
        "projects": projects, "phases": phases,
        "can_approve": has_permission(user, "attendance.approve"),
        "can_see_costs": can_see_costs(user),
        "can_set_rates": has_any_permission(user, "*.*", "payroll.create"),
    }


@router.put("/timesheets/week")
async def save_week(payload: WeekIn, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    """Replace the caller's draft (or returned) hours for one week."""
    user = await require_user(request, session_token, authorization)
    _require_workspace_member(user)
    start = _week(payload.week)
    existing = await _entries(user["user_id"], start)
    if any(e.get("status") in LOCKED for e in existing):
        raise HTTPException(409, "This week is submitted. Ask your approver to return it before editing.")
    days = {(start + timedelta(days=i)).isoformat() for i in range(7)}
    visible = {p["id"] for p in await sdb.projects.find(
        await project_visibility_query(user), {"_id": 0, "id": 1}).to_list(5000)}
    phase_project = {}
    wanted_phases = [e.phase_id for e in payload.entries if e.phase_id]
    if wanted_phases:
        async for ph in sdb.project_phases.find({"id": {"$in": wanted_phases}}, {"_id": 0, "id": 1, "project_id": 1}):
            phase_project[ph["id"]] = ph["project_id"]
    per_day: dict = {}
    docs = []
    for e in payload.entries:
        if e.date not in days:
            raise HTTPException(400, f"{e.date} is not in the week starting {start.isoformat()}")
        if e.project_id not in visible:
            raise HTTPException(404, "Project not found")
        if e.phase_id and phase_project.get(e.phase_id) != e.project_id:
            raise HTTPException(400, "That phase belongs to a different project")
        hours = round(round(e.hours * 4) / 4, 2)        # quarter hours
        if hours <= 0:
            raise HTTPException(400, "Hours must be at least 0.25")
        per_day[e.date] = per_day.get(e.date, 0) + hours
        if per_day[e.date] > MAX_DAY_HOURS:
            raise HTTPException(400, f"More than 24 hours logged on {e.date}")
        docs.append({"id": new_id("te_"), "user_id": user["user_id"], "week": start.isoformat(),
                     "date": e.date, "project_id": e.project_id, "phase_id": e.phase_id,
                     "hours": hours, "billable": e.billable, "note": e.note.strip(),
                     "status": "draft", "created_at": iso_now()})
    await sdb.time_entries.delete_many({"user_id": user["user_id"], "week": start.isoformat(),
                                        "status": {"$nin": list(LOCKED)}})
    if docs:
        await sdb.time_entries.insert_many([dict(d) for d in docs])
    return {"week": start.isoformat(), "status": week_status(docs), "entries": docs,
            "total_hours": round(sum(d["hours"] for d in docs), 2)}


@router.post("/timesheets/week/submit")
async def submit_week(payload: WeekRef, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_workspace_member(user)
    start = _week(payload.week)
    open_rows = [e for e in await _entries(user["user_id"], start) if e.get("status") not in LOCKED]
    if not open_rows:
        raise HTTPException(400, "Nothing to submit for this week")
    await sdb.time_entries.update_many(
        {"user_id": user["user_id"], "week": start.isoformat(), "status": {"$in": ["draft", "rejected"]}},
        {"$set": {"status": "submitted", "submitted_at": iso_now(), "rejection_reason": None}})
    from core.notifications import emit
    approvers = [u["user_id"] async for u in sdb.users.find(
        {"role": {"$in": ["Admin", "Director", "ProjectManager", "HR"]}, "is_active": {"$ne": False},
         "user_id": {"$ne": user["user_id"]}}, {"_id": 0, "user_id": 1})]
    await emit(approvers, "reminder", f"Timesheet submitted: {user.get('name') or user.get('email')}",
               f"Week of {start.strftime('%d %b %Y')} · {sum(float(e['hours']) for e in open_rows):g} h",
               link="/timesheets?tab=approvals", dedup_key=f"ts-submit:{user['user_id']}:{start.isoformat()}")
    return {"week": start.isoformat(), "status": "submitted"}


# ---------------------------------------------------------------- approvals
@router.get("/timesheets/approvals")
async def approvals(request: Request, week: Optional[str] = None, status: str = "submitted",
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "attendance.approve"):
        raise HTTPException(403, "Missing permission: attendance.approve")
    q = {"status": status} if status in ("submitted", "approved", "rejected") else {"status": {"$in": list(LOCKED)}}
    if week:
        q["week"] = _week(week).isoformat()
    groups: dict = {}
    async for e in sdb.time_entries.find(q, {"_id": 0}).sort("week", -1).limit(5000):
        key = (e["user_id"], e["week"])
        g = groups.setdefault(key, {"user_id": e["user_id"], "week": e["week"], "hours": 0.0,
                                    "billable_hours": 0.0, "entries": 0, "submitted_at": e.get("submitted_at")})
        g["hours"] += float(e.get("hours") or 0)
        g["billable_hours"] += float(e.get("hours") or 0) if e.get("billable") else 0
        g["entries"] += 1
    names = {u["user_id"]: u.get("name") or u.get("email") async for u in sdb.users.find(
        {"user_id": {"$in": list({k[0] for k in groups})}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})}
    rows = []
    for g in groups.values():
        rows.append({**g, "name": names.get(g["user_id"], "—"), "hours": round(g["hours"], 2),
                     "billable_hours": round(g["billable_hours"], 2),
                     "own": g["user_id"] == user["user_id"]})
    return sorted(rows, key=lambda r: (r["week"], r["name"]), reverse=True)


async def _decide(payload: DecisionIn, user: dict, approve: bool) -> dict:
    start = _week(payload.week)
    if payload.user_id == user["user_id"] and not has_permission(user, "*.*"):
        raise HTTPException(403, "Ask another approver to approve your own timesheet")
    rows = [e for e in await _entries(payload.user_id, start) if e.get("status") == "submitted"]
    if not rows:
        raise HTTPException(404, "No submitted hours for that person and week")
    if approve:
        rate = hourly_cost(await _employee_for(payload.user_id))
        for e in rows:
            await sdb.time_entries.update_one({"id": e["id"], "status": "submitted"}, {"$set": {
                "status": "approved", "approved_by": user["user_id"], "approved_at": iso_now(),
                "cost_rate": rate, "cost": round(rate * float(e["hours"]), 2) if rate else None}})
    else:
        await sdb.time_entries.update_many(
            {"user_id": payload.user_id, "week": start.isoformat(), "status": "submitted"},
            {"$set": {"status": "rejected", "rejection_reason": payload.reason.strip() or "Returned for changes",
                      "rejected_by": user["user_id"], "rejected_at": iso_now()}})
    await audit(user, "timesheet.approve" if approve else "timesheet.return", target=payload.user_id,
                target_type="timesheet", meta={"week": start.isoformat(), "entries": len(rows)})
    from core.notifications import emit
    await emit([payload.user_id], "reminder",
               f"Timesheet {'approved' if approve else 'returned'}: week of {start.strftime('%d %b')}",
               "" if approve else (payload.reason.strip() or "Please review and submit again."),
               link=f"/timesheets?week={start.isoformat()}",
               dedup_key=f"ts-{'ok' if approve else 'back'}:{payload.user_id}:{start.isoformat()}:{iso_now()[:16]}")
    return {"user_id": payload.user_id, "week": start.isoformat(), "status": "approved" if approve else "rejected"}


@router.post("/timesheets/approve")
async def approve_week(payload: DecisionIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "attendance.approve"):
        raise HTTPException(403, "Missing permission: attendance.approve")
    return await _decide(payload, user, approve=True)


@router.post("/timesheets/return")
async def return_week(payload: DecisionIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "attendance.approve"):
        raise HTTPException(403, "Missing permission: attendance.approve")
    return await _decide(payload, user, approve=False)


# ---------------------------------------------------------------- cost rates
@router.get("/timesheets/cost-rates")
async def cost_rates(request: Request, session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not can_see_costs(user):
        raise HTTPException(403, "Missing permission: payroll.read")
    rows = []
    async for e in sdb.employees.find({"employment_status": {"$ne": "terminated"}}, {"_id": 0}).sort("first_name", 1):
        rows.append({"id": e["id"], "employee_id": e.get("employee_id"),
                     "name": " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x) or e.get("employee_id"),
                     "designation": e.get("designation"), "cost_rate_hourly": e.get("cost_rate_hourly"),
                     "derived_rate": hourly_cost({**e, "cost_rate_hourly": None}),
                     "effective_rate": hourly_cost(e)})
    return rows


@router.patch("/employees/{employee_id}/cost-rate")
async def set_cost_rate(employee_id: str, payload: CostRateIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """Set (or clear, with null) the hourly cost used for new approvals."""
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "*.*", "payroll.create"):
        raise HTTPException(403, "Missing permission: payroll.create")
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0, "id": 1})
    if not emp:
        raise HTTPException(404, "Employee not found")
    rate = round(payload.cost_rate_hourly, 2) if payload.cost_rate_hourly else None
    await sdb.employees.update_one({"id": employee_id}, {"$set": {"cost_rate_hourly": rate, "updated_at": iso_now()}})
    await audit(user, "employee.cost_rate", target=employee_id, target_type="employee", meta={"rate": rate})
    return {"id": employee_id, "cost_rate_hourly": rate}


# ---------------------------------------------------------------- project views
@router.get("/projects/{project_id}/time")
async def project_time(project_id: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    """Submitted and approved hours by phase and by person (costs for finance roles)."""
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id)
    show_cost = can_see_costs(user)
    phases = {p["id"]: p["name"] async for p in sdb.project_phases.find(
        {"project_id": project_id}, {"_id": 0, "id": 1, "name": 1})}
    by_phase: dict = {}
    by_person: dict = {}
    totals = {"hours": 0.0, "billable_hours": 0.0, "approved_hours": 0.0, "cost": 0.0}
    async for e in sdb.time_entries.find({"project_id": project_id, "status": {"$in": list(LOCKED)}}, {"_id": 0}):
        h = float(e.get("hours") or 0)
        phase = phases.get(e.get("phase_id"), "No phase")
        for bucket, key in ((by_phase, phase), (by_person, e["user_id"])):
            row = bucket.setdefault(key, {"hours": 0.0, "billable_hours": 0.0, "cost": 0.0})
            row["hours"] += h
            row["billable_hours"] += h if e.get("billable") else 0
            row["cost"] += float(e.get("cost") or 0) if e.get("status") == "approved" else 0
        totals["hours"] += h
        totals["billable_hours"] += h if e.get("billable") else 0
        totals["approved_hours"] += h if e.get("status") == "approved" else 0
        totals["cost"] += float(e.get("cost") or 0) if e.get("status") == "approved" else 0
    names = {u["user_id"]: u.get("name") or u.get("email") async for u in sdb.users.find(
        {"user_id": {"$in": list(by_person)}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})}

    def clean(row: dict) -> dict:
        out = {k: round(v, 2) for k, v in row.items()}
        if not show_cost:
            out.pop("cost", None)
        return out
    result = {
        "totals": clean(totals),
        "by_phase": [{"phase": k, **clean(v)} for k, v in sorted(by_phase.items(), key=lambda kv: -kv[1]["hours"])],
        "by_person": [{"user_id": k, "name": names.get(k, "—"), **clean(v)}
                      for k, v in sorted(by_person.items(), key=lambda kv: -kv[1]["hours"])],
        "can_see_costs": show_cost,
    }
    return result


@router.get("/projects/{project_id}/profitability")
async def project_profitability(project_id: str, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    """Fee and billing against what the project has cost so far."""
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "*.*", "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    project = await get_visible_project(user, project_id)
    invoiced = await _sum(sdb.invoices.find(
        {"project_id": project_id, "doc_type": {"$ne": "quotation"},
         "status": {"$nin": ["draft", "cancelled"]}}, {"_id": 0, "total": 1}), "total")
    vendor = await _sum(sdb.vendor_bills.find(
        {"project_id": project_id, "status": {"$nin": ["draft", "cancelled"]}}, {"_id": 0, "total": 1}), "total")
    expenses = await _sum(sdb.expenses.find(
        {"project_id": project_id, "status": {"$in": ["approved", "reimbursed"]}}, {"_id": 0, "total": 1}), "total")
    labour = hours = 0.0
    unpriced = 0.0
    async for e in sdb.time_entries.find({"project_id": project_id, "status": "approved"},
                                         {"_id": 0, "hours": 1, "cost": 1}):
        hours += float(e.get("hours") or 0)
        if e.get("cost") is None:
            unpriced += float(e.get("hours") or 0)
        labour += float(e.get("cost") or 0)
    fee = float(project.get("budget") or 0)
    cost = vendor + expenses + labour

    def pct(part: float, whole: float) -> Optional[float]:
        return round(part * 100 / whole, 1) if whole else None
    return {
        "fee": round(fee, 2), "invoiced": round(invoiced, 2),
        "costs": {"vendor_bills": round(vendor, 2), "expenses": round(expenses, 2),
                  "labour": round(labour, 2), "total": round(cost, 2)},
        "approved_hours": round(hours, 2), "unpriced_hours": round(unpriced, 2),
        "margin_on_invoiced": round(invoiced - cost, 2), "margin_on_invoiced_pct": pct(invoiced - cost, invoiced),
        "margin_on_fee": round(fee - cost, 2) if fee else None, "margin_on_fee_pct": pct(fee - cost, fee),
        "fee_used_pct": pct(cost, fee),
    }
