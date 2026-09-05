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
from datetime import date as _date, datetime

from core.scoped_db import sdb
from core.helpers import iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from core.tenancy import user_org_id
from core.notifications import emit
from core.audit import audit

router = APIRouter()

EVENT_KINDS = ["meeting", "reminder", "deadline", "other"]


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
    attendee_ids: Optional[List[str]] = None   # user_ids to notify
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
    attendee_ids: Optional[List[str]] = None
    location: Optional[str] = None
    notes: Optional[str] = None


def _valid_date(s: str) -> bool:
    try:
        _date.fromisoformat((s or "")[:10])
        return True
    except Exception:
        return False


# ==================================================
# Manual events CRUD
# ==================================================
@router.get("/calendar/events")
async def list_events(request: Request, start: Optional[str] = None, end: Optional[str] = None,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q: dict = {}
    if start and end:
        q["date"] = {"$gte": start[:10], "$lte": end[:10]}
    rows = await sdb.calendar_events.find(q, {"_id": 0}).sort("date", 1).to_list(1000)
    return rows


@router.post("/calendar/events")
async def create_event(payload: EventIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not _valid_date(payload.date):
        raise HTTPException(400, "Invalid date (expected YYYY-MM-DD)")
    if payload.end_date and not _valid_date(payload.end_date):
        raise HTTPException(400, "Invalid end_date (expected YYYY-MM-DD)")
    kind = payload.kind if payload.kind in EVENT_KINDS else "other"
    doc = payload.model_dump()
    doc.update({
        "id": new_id("evt_"),
        "kind": kind,
        "date": payload.date[:10],
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "created_by_name": user.get("name"),
        "org_id": user_org_id(user),
    })
    await sdb.calendar_events.insert_one(dict(doc))
    await audit(user, "calendar_event.create", target=doc["id"], target_type="calendar_event",
                meta={"title": doc["title"], "date": doc["date"], "kind": kind})
    # Notify attendees (excluding creator)
    attendees = [a for a in (payload.attendee_ids or []) if a and a != user["user_id"]]
    if attendees:
        label = "Meeting" if kind == "meeting" else "Reminder" if kind == "reminder" else "Event"
        await emit(attendees, "meeting" if kind == "meeting" else "reminder",
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

    # ---- 7) Manual events ----
    evts = await sdb.calendar_events.find(
        {"date": {"$gte": start, "$lte": end}}, {"_id": 0},
    ).to_list(1000)
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
