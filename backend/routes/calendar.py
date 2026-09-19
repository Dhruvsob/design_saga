"""Unified ERP Calendar.

Two parts:
1. `calendar_events` — tenant-scoped manual events (meetings / reminders)
   with full CRUD. Creator or Admin can edit/delete.
2. `GET /calendar/feed` — a read-only aggregator that merges, for a given
   date window:
     - tasks (due dates)
     - payment milestones
     - project deadlines (end_date)
     - holidays (incl. recurring, expanded per-year)
     - approved leaves
     - unpaid invoice due dates (permission-gated)
     - manual events (meetings / reminders)

Every item is normalised to:
  {id, kind, date, end_date?, time?, title, subtitle?, link?, meta{}}
so the frontend calendar can render any source uniformly.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date as _date, datetime, timezone, timedelta

from core.scoped_db import sdb
from core.helpers import iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from core.tenancy import user_org_id
from core.notifications import emit
from core.audit import audit

router = APIRouter()

EVENT_KINDS = ["meeting", "reminder", "deadline", "other"]
IST = timezone(timedelta(hours=5, minutes=30))   # calendar times are entered/displayed in IST


# ==================================================
# Models
# ==================================================
class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: str = "meeting"                      # meeting | reminder | deadline | other
    date: str                                  # YYYY-MM-DD
    end_date: Optional[str] = None
    start_time: Optional[str] = None           # HH:MM
    end_time: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    vendor_id: Optional[str] = None            # tag a vendor / agency (vendors incl. agency_type)
    employee_ids: Optional[List[str]] = None   # tag employees (also notified if they have a login)
    attendee_ids: Optional[List[str]] = None   # user_ids to notify directly
    visibility: Optional[str] = None           # private | org  (default: private)
    reminder_minutes: Optional[int] = None     # minutes before start to remind (None = no reminder)
    location: Optional[str] = None
    notes: Optional[str] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    kind: Optional[str] = None
    date: Optional[str] = None
    end_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    vendor_id: Optional[str] = None
    employee_ids: Optional[List[str]] = None
    attendee_ids: Optional[List[str]] = None
    visibility: Optional[str] = None
    reminder_minutes: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None


def _valid_date(s: str) -> bool:
    try:
        _date.fromisoformat((s or "")[:10])
        return True
    except Exception:
        return False


VISIBILITIES = ["private", "org"]


def _cal_can_see_all(user: dict) -> bool:
    """Admins / SuperAdmins see every event in the tenant; others see their own,
    events shared with the org, and events they're tagged/invited to."""
    return bool(user.get("is_super_admin")) or has_permission(user, "*.*")


def _visibility_filter(user: dict) -> dict:
    """Mongo filter enforcing per-employee calendar privacy for non-admins.
    Private events are only visible to their creator + tagged attendees."""
    if _cal_can_see_all(user):
        return {}
    uid = user["user_id"]
    return {"$or": [
        {"visibility": {"$ne": "private"}},   # 'org' or legacy events without the field
        {"created_by": uid},
        {"attendee_ids": uid},
    ]}


async def _resolve_notify_ids(user: dict, attendee_ids, employee_ids) -> list:
    """Union of directly-invited user_ids and the login user_ids of tagged
    employees, minus the creator (who doesn't need to notify themselves)."""
    ids = {a for a in (attendee_ids or []) if a}
    emp_ids = [e for e in (employee_ids or []) if e]
    if emp_ids:
        async for emp in sdb.employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "user_id": 1}):
            if emp.get("user_id"):
                ids.add(emp["user_id"])
    ids.discard(user["user_id"])
    return list(ids)


# ==================================================
# Manual events CRUD
# ==================================================
@router.get("/calendar/events")
async def list_events(request: Request, start: Optional[str] = None, end: Optional[str] = None,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "calendar.read"):
        raise HTTPException(403, "Missing permission: calendar.read")
    q: dict = {}
    if start and end:
        q["date"] = {"$gte": start[:10], "$lte": end[:10]}
    vis = _visibility_filter(user)
    if vis:
        q = {"$and": [q, vis]} if q else vis
    rows = await sdb.calendar_events.find(q, {"_id": 0}).sort("date", 1).to_list(1000)
    return rows


@router.post("/calendar/events")
async def create_event(payload: EventIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "calendar.read"):
        raise HTTPException(403, "Missing permission: calendar.read")
    if not _valid_date(payload.date):
        raise HTTPException(400, "Invalid date (expected YYYY-MM-DD)")
    if payload.end_date and not _valid_date(payload.end_date):
        raise HTTPException(400, "Invalid end_date (expected YYYY-MM-DD)")
    kind = payload.kind if payload.kind in EVENT_KINDS else "other"
    visibility = payload.visibility if payload.visibility in VISIBILITIES else "private"
    reminder = payload.reminder_minutes
    if reminder is not None and (reminder < 0 or reminder > 44640):   # cap ~31 days
        reminder = None
    doc = payload.model_dump()
    doc.update({
        "id": new_id("evt_"),
        "kind": kind,
        "date": payload.date[:10],
        "visibility": visibility,
        "reminder_minutes": reminder,
        "employee_ids": [e for e in (payload.employee_ids or []) if e],
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "created_by_name": user.get("name"),
        "org_id": user_org_id(user),
    })
    await sdb.calendar_events.insert_one(dict(doc))
    await audit(user, "calendar_event.create", target=doc["id"], target_type="calendar_event",
                meta={"title": doc["title"], "date": doc["date"], "kind": kind})
    # Notify tagged people (invited users + tagged employees), excluding creator
    notify_ids = await _resolve_notify_ids(user, payload.attendee_ids, payload.employee_ids)
    if notify_ids:
        label = "Meeting" if kind == "meeting" else "Reminder" if kind == "reminder" else "Event"
        await emit(notify_ids, "meeting" if kind == "meeting" else "reminder",
                   f"{label}: {doc['title']}",
                   body=f"{doc['date']}" + (f" · {doc.get('start_time')}" if doc.get("start_time") else ""),
                   link="/calendar", priority="normal",
                   meta={"event_id": doc["id"]}, dedup_key=f"evt_invite_{doc['id']}")
    return await sdb.calendar_events.find_one({"id": doc["id"]}, {"_id": 0})


@router.patch("/calendar/events/{event_id}")
async def update_event(event_id: str, payload: EventUpdate, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    row = await sdb.calendar_events.find_one({"id": event_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Event not found")
    if row.get("created_by") != user["user_id"] and not has_permission(user, "*.*"):
        raise HTTPException(403, "Only the creator or an Admin can edit this event")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "date" in upd and not _valid_date(upd["date"]):
        raise HTTPException(400, "Invalid date")
    if "kind" in upd and upd["kind"] not in EVENT_KINDS:
        upd["kind"] = "other"
    if "visibility" in upd and upd["visibility"] not in VISIBILITIES:
        upd.pop("visibility")
    if "reminder_minutes" in upd and (upd["reminder_minutes"] < 0 or upd["reminder_minutes"] > 44640):
        upd.pop("reminder_minutes")
    upd["updated_at"] = iso_now()
    await sdb.calendar_events.update_one({"id": event_id}, {"$set": upd})
    return await sdb.calendar_events.find_one({"id": event_id}, {"_id": 0})


@router.delete("/calendar/events/{event_id}")
async def delete_event(event_id: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    row = await sdb.calendar_events.find_one({"id": event_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Event not found")
    if row.get("created_by") != user["user_id"] and not has_permission(user, "*.*"):
        raise HTTPException(403, "Only the creator or an Admin can delete this event")
    await sdb.calendar_events.delete_one({"id": event_id})
    await audit(user, "calendar_event.delete", target=event_id, target_type="calendar_event",
                meta={"title": row.get("title")})
    return {"ok": True}


# ==================================================
# Aggregated feed
# ==================================================
@router.get("/calendar/feed")
async def calendar_feed(start: str, end: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "calendar.read"):
        raise HTTPException(403, "Missing permission: calendar.read")
    if not (_valid_date(start) and _valid_date(end)):
        raise HTTPException(400, "start and end must be YYYY-MM-DD")
    start, end = start[:10], end[:10]
    if start > end:
        raise HTTPException(400, "start must be <= end")
    end_hi = end + "\uffff"     # include full-ISO datetimes on the end day

    items: List[dict] = []

    # ---- 1) Tasks (due dates) ----
    tasks = await sdb.tasks.find(
        {"due_date": {"$gte": start, "$lte": end_hi}},
        {"_id": 0, "id": 1, "title": 1, "due_date": 1, "status": 1,
         "priority": 1, "assignee_name": 1, "project_id": 1},
    ).to_list(2000)
    proj_ids = {t["project_id"] for t in tasks if t.get("project_id")}
    proj_names = {}
    if proj_ids:
        async for p in sdb.projects.find({"id": {"$in": list(proj_ids)}}, {"_id": 0, "id": 1, "name": 1}):
            proj_names[p["id"]] = p.get("name")
    for t in tasks:
        items.append({
            "id": f"task:{t['id']}",
            "kind": "task",
            "date": (t.get("due_date") or "")[:10],
            "title": t.get("title") or "Task",
            "subtitle": " · ".join(x for x in [proj_names.get(t.get("project_id")), t.get("assignee_name")] if x),
            "link": f"/tasks/{t['id']}",
            "meta": {"status": t.get("status"), "priority": t.get("priority")},
        })

    # ---- 2) Payment milestones ----
    ms = await sdb.payment_milestones.find(
        {"due_date": {"$gte": start, "$lte": end_hi}},
        {"_id": 0, "id": 1, "name": 1, "due_date": 1, "amount": 1, "status": 1, "project_id": 1},
    ).to_list(500)
    ms_proj = {m["project_id"] for m in ms if m.get("project_id")}
    if ms_proj:
        async for p in sdb.projects.find({"id": {"$in": list(ms_proj)}}, {"_id": 0, "id": 1, "name": 1}):
            proj_names[p["id"]] = p.get("name")
    for m in ms:
        items.append({
            "id": f"milestone:{m['id']}",
            "kind": "milestone",
            "date": (m.get("due_date") or "")[:10],
            "title": m.get("name") or "Milestone",
            "subtitle": proj_names.get(m.get("project_id")) or "",
            "link": f"/projects/{m['project_id']}" if m.get("project_id") else None,
            "meta": {"amount": m.get("amount"), "status": m.get("status")},
        })

    # ---- 3) Project deadlines ----
    projs = await sdb.projects.find(
        {"end_date": {"$gte": start, "$lte": end_hi}, "archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "end_date": 1, "stage": 1},
    ).to_list(500)
    for p in projs:
        items.append({
            "id": f"project:{p['id']}",
            "kind": "project_deadline",
            "date": (p.get("end_date") or "")[:10],
            "title": f"{p.get('name')} — deadline",
            "subtitle": p.get("stage") or "",
            "link": f"/projects/{p['id']}",
            "meta": {},
        })

    # ---- 4) Holidays (exact + recurring expansion) ----
    y0, y1 = int(start[:4]), int(end[:4])
    async for h in sdb.holidays.find({"active": {"$ne": False}}, {"_id": 0}):
        hd = (h.get("date") or "")[:10]
        if not _valid_date(hd):
            continue
        dates = []
        if h.get("recurring"):
            for y in range(y0, y1 + 1):
                try:
                    cand = _date(y, int(hd[5:7]), int(hd[8:10])).isoformat()
                    dates.append(cand)
                except ValueError:
                    continue
        else:
            dates.append(hd)
        for d in dates:
            if start <= d <= end:
                items.append({
                    "id": f"holiday:{h.get('id') or hd}:{d}",
                    "kind": "holiday",
                    "date": d,
                    "title": h.get("name") or "Holiday",
                    "subtitle": (h.get("kind") or "company").title(),
                    "link": "/holidays",
                    "meta": {},
                })

    # ---- 5) Approved leaves overlapping window ----
    leaves = await sdb.leaves.find(
        {"status": "approved", "from_date": {"$lte": end}, "to_date": {"$gte": start}},
        {"_id": 0, "id": 1, "employee_name": 1, "leave_type": 1, "from_date": 1, "to_date": 1},
    ).to_list(500)
    for l in leaves:
        items.append({
            "id": f"leave:{l['id']}",
            "kind": "leave",
            "date": max((l.get("from_date") or start)[:10], start),
            "end_date": min((l.get("to_date") or end)[:10], end),
            "title": f"{l.get('employee_name') or 'Employee'} · {l.get('leave_type') or ''} leave".strip(),
            "subtitle": f"{l.get('from_date')} → {l.get('to_date')}",
            "link": "/attendance",
            "meta": {},
        })

    # ---- 6) Invoice due dates (finance permission gated) ----
    if has_permission(user, "finance.read") or has_permission(user, "invoices.read"):
        invs = await sdb.invoices.find(
            {"due_date": {"$gte": start, "$lte": end_hi},
             "status": {"$nin": ["paid", "cancelled"]}},
            {"_id": 0, "id": 1, "number": 1, "client_name": 1, "due_date": 1, "total": 1, "status": 1},
        ).to_list(500)
        for inv in invs:
            items.append({
                "id": f"invoice:{inv['id']}",
                "kind": "invoice_due",
                "date": (inv.get("due_date") or "")[:10],
                "title": f"{inv.get('number') or 'Invoice'} due",
                "subtitle": inv.get("client_name") or "",
                "link": "/invoices",
                "meta": {"amount": inv.get("total"), "status": inv.get("status")},
            })

    # ---- 7) Manual events (privacy-filtered for non-admins) ----
    evt_q: dict = {"date": {"$gte": start, "$lte": end}}
    vis = _visibility_filter(user)
    if vis:
        evt_q = {"$and": [evt_q, vis]}
    evts = await sdb.calendar_events.find(evt_q, {"_id": 0}).to_list(1000)
    for e in evts:
        items.append({
            "id": f"event:{e['id']}",
            "kind": e.get("kind") or "other",
            "date": e.get("date"),
            "end_date": e.get("end_date"),
            "time": e.get("start_time"),
            "title": e.get("title"),
            "subtitle": " · ".join(x for x in [e.get("location"), e.get("created_by_name")] if x),
            "link": None,
            "event": e,          # full doc so UI can edit/delete
            "meta": {"notes": e.get("notes")},
        })

    items.sort(key=lambda x: (x.get("date") or "", x.get("time") or "99:99"))
    return {"start": start, "end": end, "count": len(items), "items": items}



# ==================================================
# Reminders — imminent events for the current user
# ==================================================
@router.get("/calendar/reminders/due")
async def calendar_reminders_due(request: Request, window: int = 5,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    """Return the current user's events whose reminder is currently due.

    A reminder is 'due' when now (IST) is within `reminder_minutes` before the
    event's start_time and up to `window` minutes after it started. Only events
    the user created or is invited/tagged to are returned. The frontend dedups
    so each reminder is surfaced (toast + optional sound) once per session.
    """
    user = await require_user(request, session_token, authorization)
    uid = user["user_id"]
    now_ist = datetime.now(IST)
    today = now_ist.date().isoformat()
    q = {
        "date": today,
        "start_time": {"$nin": [None, ""]},
        "reminder_minutes": {"$ne": None},
        "$or": [{"created_by": uid}, {"attendee_ids": uid}],
    }
    rows = await sdb.calendar_events.find(q, {"_id": 0}).to_list(200)
    due = []
    for e in rows:
        rm = e.get("reminder_minutes")
        st = (e.get("start_time") or "").strip()
        if rm is None or ":" not in st:
            continue
        try:
            hh, mm = int(st[:2]), int(st[3:5])
            start_dt = now_ist.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:
            continue
        minutes_until = (start_dt - now_ist).total_seconds() / 60.0
        # Fire from `rm` minutes before start until `window` minutes after start.
        if -abs(window) <= minutes_until <= rm:
            due.append({
                "id": e["id"],
                "title": e.get("title"),
                "date": e.get("date"),
                "start_time": st,
                "kind": e.get("kind"),
                "location": e.get("location"),
                "minutes_until": round(minutes_until),
                "reminder_minutes": rm,
            })
    due.sort(key=lambda x: x["minutes_until"])
    return {"count": len(due), "reminders": due}
