"""Team capacity heatmap (P2.5): planned task hours and logged hours against
each person's available hours, week by week (rules in core.capacity).

GET /capacity?start=YYYY-MM-DD&weeks=10
  Managers (attendance.approve or projects.update) see the whole team plus a
  "Not assigned" row; everyone else sees only their own row. Task titles are
  limited to tasks the viewer may see (task_visibility_query).
"""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request

from core import capacity as cap
from core.access_control import merge_query, task_visibility_query, user_identity_ids
from core.attendance_engine import emp_name, get_holiday_dates
from core.deps import require_user
from core.helpers import business_today
from core.rbac import has_any_permission
from core.tenancy import is_super_admin
from core.scoped_db import sdb

router = APIRouter()

MAX_TASKS = 5000
TASKS_PER_CELL = 12
UNASSIGNED = "_unassigned"


def _can_see_team(user: dict) -> bool:
    return has_any_permission(user, "*.*", "attendance.approve", "projects.update")


@router.get("/capacity")
async def team_capacity(request: Request, start: Optional[str] = None, weeks: int = 10,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if is_super_admin(user) and not user.get("org_id"):
        raise HTTPException(403, "Open a workspace to see its capacity")
    today = business_today()
    weeks = max(1, min(int(weeks or 10), 16))
    first = cap.monday(cap.parse(start) or (today - timedelta(days=14)))
    last = first + timedelta(days=weeks * 7 - 1)
    this_week = cap.monday(today)
    week_list = [first + timedelta(days=7 * n) for n in range(weeks)]
    week_keys = [w.isoformat() for w in week_list]
    team = _can_see_team(user)

    policy = await sdb.attendance_policies.find_one({}, {"_id": 0, "weekly_off_days": 1}) or {}
    default_offs = set(policy.get("weekly_off_days") or [6])
    holidays: set[str] = set()
    for year in range(first.year, last.year + 1):
        holidays |= await get_holiday_dates(year)

    # People: current staff (employees), linked to their login by user_id or email.
    users = await sdb.users.find({}, {"_id": 0, "user_id": 1, "email": 1}).to_list(5000)
    uid_by_email = {(u.get("email") or "").lower(): u["user_id"] for u in users if u.get("email")}
    employees = await sdb.employees.find({"employment_status": {"$ne": "terminated"}}, {"_id": 0}).to_list(2000)
    mine = await user_identity_ids(user)
    people, by_identity, none_row = [], {}, None
    for e in employees:
        uid = e.get("user_id") or uid_by_email.get((e.get("email") or "").lower())
        ids = {x for x in (e.get("id"), uid) if x}
        if not team and not (ids & mine):
            continue
        offs = set(e["weekly_offs"]) if e.get("weekly_offs") is not None else default_offs
        p = {"id": e["id"], "user_id": uid, "name": emp_name(e), "designation": e.get("designation"),
             "weekly_hours": float(e.get("weekly_hours") or cap.DEFAULT_WEEKLY_HOURS),
             "offs": offs, "is_me": bool(ids & mine), "planned": {}, "tasks": {},
             "unscheduled_hours": 0.0, "unestimated": 0}
        p["day_hours"] = cap.hours_per_day(p["weekly_hours"], offs)
        people.append(p)
        for x in ids:
            by_identity[x] = p
    if team:
        none_row = {"id": UNASSIGNED, "user_id": None, "name": "Not assigned", "designation": None,
                    "weekly_hours": 0.0, "day_hours": 0.0, "offs": default_offs, "is_me": False,
                    "planned": {}, "tasks": {}, "unscheduled_hours": 0.0, "unestimated": 0}

    # Approved leave in the window, per employee.
    leave_by_emp: dict[str, list] = {}
    async for lv in sdb.leaves.find({"status": "approved", "from_date": {"$lte": last.isoformat()},
                                     "to_date": {"$gte": first.isoformat()}}, {"_id": 0}):
        leave_by_emp.setdefault(lv.get("employee_id"), []).append(lv)

    # Open tasks the viewer may see: every estimated one (it may be overdue or
    # start inside the window), plus unestimated ones due inside the window so
    # people can see where estimates are missing. Two narrow queries keep a
    # workspace with thousands of open tasks from truncating the plan.
    visibility = await task_visibility_query(user)
    fields = {"_id": 0, "id": 1, "title": 1, "project_id": 1, "assignee_id": 1,
              "assignees": 1, "estimate_hours": 1, "start_date": 1, "due_date": 1}
    estimated = await sdb.tasks.find(merge_query(
        {"status": {"$ne": "done"}, "estimate_hours": {"$gt": 0}}, visibility), fields).to_list(MAX_TASKS)
    due_here = await sdb.tasks.find(merge_query(
        {"status": {"$ne": "done"}, "due_date": {"$gte": first.isoformat(), "$lte": last.isoformat()}},
        visibility), {"_id": 0, "id": 1, "assignee_id": 1, "assignees": 1, "estimate_hours": 1,
                      "due_date": 1}).to_list(MAX_TASKS)
    tasks = estimated + [t for t in due_here if not float(t.get("estimate_hours") or 0) > 0]
    project_ids = sorted({t["project_id"] for t in tasks if t.get("project_id")})
    projects = {p["id"]: p.get("name") for p in await sdb.projects.find(
        {"id": {"$in": project_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(project_ids) + 1)} if project_ids else {}

    for t in tasks:
        ids = [x for x in dict.fromkeys([t.get("assignee_id"), *(t.get("assignees") or [])]) if x]
        owners = [by_identity[x] for x in ids if x in by_identity]
        owners = list({id(o): o for o in owners}.values())
        if not owners:
            if not team:
                continue
            owners = [none_row]
        due = cap.parse(t.get("due_date"))
        est = float(t.get("estimate_hours") or 0)
        share = 1 / len(owners)
        for p in owners:
            if est <= 0:
                if due and first <= due <= last:
                    p["unestimated"] += 1
                continue
            if not due:
                p["unscheduled_hours"] += est * share
                continue
            for wk, hours in cap.spread(t, today, p["offs"], holidays).items():
                if wk not in week_keys:
                    continue
                h = hours * share
                p["planned"][wk] = p["planned"].get(wk, 0.0) + h
                p["tasks"].setdefault(wk, []).append({
                    "id": t["id"], "title": t.get("title"), "project_id": t.get("project_id"),
                    "project_name": projects.get(t.get("project_id")), "hours": round(h, 1),
                    "due_date": t.get("due_date"), "overdue": bool(due < today)})

    # Hours logged on timesheets (all statuses: what people say they worked).
    logged: dict[tuple, float] = {}
    async for e in sdb.time_entries.find({"week": {"$gte": first.isoformat(), "$lte": week_keys[-1]}},
                                         {"_id": 0, "user_id": 1, "week": 1, "hours": 1}):
        key = (e.get("user_id"), e.get("week"))
        logged[key] = logged.get(key, 0.0) + float(e.get("hours") or 0)

    rows = people + ([none_row] if team and (none_row["planned"] or none_row["unscheduled_hours"]
                                             or none_row["unestimated"]) else [])
    totals = {k: {"capacity": 0.0, "load": 0.0, "over": 0} for k in week_keys}
    out_rows = []
    for p in rows:
        leave = cap.leave_dates(leave_by_emp.get(p["id"], []), first, last)
        cells = []
        for w in week_list:
            k = w.isoformat()
            if p["id"] == UNASSIGNED:
                capacity, hol, lv = 0.0, 0, 0
            else:
                capacity, hol, lv = cap.week_capacity(w, p["day_hours"], p["offs"], holidays, leave)
            planned = round(p["planned"].get(k, 0.0), 1)
            done = round(logged.get((p["user_id"], k), 0.0), 1) if p["user_id"] else 0.0
            load = done if w < this_week else (round(done + planned, 1) if w == this_week else planned)
            pct = round(load / capacity, 3) if capacity else None
            band = cap.band(pct) if capacity else ("over" if load else "off")
            if p["id"] != UNASSIGNED:
                totals[k]["capacity"] += capacity
                totals[k]["load"] += load
                totals[k]["over"] += 1 if band == "over" else 0
            tasks_here = sorted(p["tasks"].get(k, []), key=lambda x: -x["hours"])
            cells.append({"week": k, "capacity": capacity, "planned": planned, "logged": done, "load": load,
                          "pct": pct, "band": band, "holidays": hol, "leave_days": lv,
                          "tasks": tasks_here[:TASKS_PER_CELL], "more_tasks": max(0, len(tasks_here) - TASKS_PER_CELL)})
        out_rows.append({"id": p["id"], "name": p["name"], "designation": p["designation"], "is_me": p["is_me"],
                         "weekly_hours": p["weekly_hours"], "cells": cells,
                         "unscheduled_hours": round(p["unscheduled_hours"], 1), "unestimated_tasks": p["unestimated"]})
    out_rows.sort(key=lambda r: (r["id"] == UNASSIGNED, not r["is_me"], r["name"].lower()))
    return {
        "today": today.isoformat(),
        "weeks": [{"week": k, "is_current": w == this_week, "is_past": w < this_week}
                  for w, k in zip(week_list, week_keys)],
        "rows": out_rows,
        "totals": [{"week": k, "capacity": round(v["capacity"], 1), "load": round(v["load"], 1),
                    "pct": round(v["load"] / v["capacity"], 3) if v["capacity"] else None,
                    "overbooked": v["over"]} for k, v in totals.items()],
        "team_view": team,
    }
