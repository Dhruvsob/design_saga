"""Reminders for Collections Due — one source of truth, reflected everywhere.

A collection (vendor incentive plan or other receivable) may carry a reminder:
``reminder_date`` + ``reminder_time`` (India time), ``remind_before_days`` and
``repeat_every`` (none | daily | weekly).  ``refresh()`` reconciles, idempotently:

* timed alerts  (``reminder_alerts``)      -> ERP notification + sound at fire time
* one calendar event per collection         -> ERP calendar + Google Calendar
  (popup/email alerts at the same times; repeats as a recurring event)
* one automatic Payment Reminder document   -> Invoices > Payment Reminders

When the collection is received in full, cancelled or loses its reminder, the
pending alerts are cancelled, the calendar/Google event is removed and the
reminder document is closed.  Nothing here ever posts accounting.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from core.db import db
from core.helpers import iso_now, new_id, next_sequence
from core.scoped_db import current_org_id, sdb

REPEAT_CHOICES = ("none", "daily", "weekly")
MAX_REPEATS = 12
DEFAULT_TIME = "10:00"
SOURCES = {
    "vendor_commission": "vendor_commissions",
    "other_receivable": "collection_receivables",
}
OPEN_STATUSES = {"pending", "invoiced", "partially_received"}


def _tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("BUSINESS_TIMEZONE", "Asia/Kolkata"))


def now_local_key() -> str:
    """'YYYY-MM-DDTHH:MM' in business time — the format alerts are stored in."""
    return datetime.now(_tz()).strftime("%Y-%m-%dT%H:%M")


def _clean_time(value: Optional[str]) -> str:
    v = str(value or "").strip()
    if len(v) >= 5 and v[2] == ":" and v[:2].isdigit() and v[3:5].isdigit():
        hh, mm = int(v[:2]), int(v[3:5])
        if 0 <= hh < 24 and 0 <= mm < 60:
            return f"{hh:02d}:{mm:02d}"
    return DEFAULT_TIME


def occurrences(row: dict) -> list[tuple[str, str]]:
    """[(label, 'YYYY-MM-DDTHH:MM'), ...] for a collection's reminder settings."""
    day = str(row.get("reminder_date") or "")[:10]
    if len(day) != 10:
        return []
    try:
        main = datetime.fromisoformat(f"{day}T{_clean_time(row.get('reminder_time'))}")
    except ValueError:
        return []
    out = []
    before = max(0, min(30, int(row.get("remind_before_days") or 0)))
    if before:
        out.append(("advance", (main - timedelta(days=before)).strftime("%Y-%m-%dT%H:%M")))
    out.append(("main", main.strftime("%Y-%m-%dT%H:%M")))
    repeat = row.get("repeat_every") if row.get("repeat_every") in REPEAT_CHOICES else "none"
    if repeat != "none":
        step = timedelta(days=1 if repeat == "daily" else 7)
        for i in range(1, MAX_REPEATS + 1):
            out.append(("repeat", (main + step * i).strftime("%Y-%m-%dT%H:%M")))
    return out


def outstanding(row: dict) -> float:
    return round(max(0.0, float(row.get("amount") or 0) - float(row.get("received_amount") or 0)), 2)


def is_active(row: Optional[dict]) -> bool:
    return bool(row) and row.get("status") in OPEN_STATUSES and outstanding(row) > 0.004


def event_id(org_id: str, source_type: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{org_id}:{source_type}:{source_id}".encode()).hexdigest()[:20]
    return f"evt_col_{digest}"


async def _finance_user_ids(org_id: str) -> list[str]:
    ids = []
    async for u in db.users.find(
            {"org_id": org_id, "role": {"$in": ["Admin", "Director", "Accountant"]},
             "is_active": {"$ne": False}}, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    return ids


async def _party_and_project(source_type: str, row: dict) -> tuple[str, Optional[str]]:
    party = None
    if row.get("vendor_id"):
        v = await sdb.vendors_acc.find_one({"id": row["vendor_id"]}, {"_id": 0, "name": 1})
        party = (v or {}).get("name") or row.get("vendor_name")
    if not party and row.get("client_id"):
        c = await sdb.clients.find_one({"id": row["client_id"]}, {"_id": 0, "name": 1})
        party = (c or {}).get("name")
    party = party or row.get("name") or "Expected collection"
    project_name = row.get("project_name")
    if not project_name and row.get("project_id"):
        p = await sdb.projects.find_one({"id": row["project_id"]}, {"_id": 0, "name": 1})
        project_name = (p or {}).get("name")
    return party, project_name


def _inr(v: float) -> str:
    whole = int(round(v))
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        s = f"{head},{tail}"
    return s


def _title(source_type: str, party: str, amount: float) -> str:
    what = "Vendor incentive" if source_type == "vendor_commission" else "Payment"
    return f"{what} reminder · {party} · Rs. {_inr(amount)}"


async def _upsert_document(org_id: str, source_type: str, row: dict, party: str,
                           project_name: Optional[str], user_id: Optional[str]) -> Optional[str]:
    """One automatic Payment Reminder (PR-xxxx) per collection; kept in step."""
    existing = await sdb.payment_reminders.find_one(
        {"source_type": source_type, "source_id": row["id"], "auto": True}, {"_id": 0})
    fields = {
        "title": row.get("name") or ("Vendor incentive" if source_type == "vendor_commission" else "Payment due"),
        "reference": row.get("reference"), "party_name": party,
        "client_id": row.get("client_id"), "vendor_id": row.get("vendor_id"),
        "project_id": row.get("project_id"), "project_name": project_name,
        "total_amount": round(float(row.get("amount") or 0), 2),
        "received_before": round(float(row.get("received_amount") or 0), 2),
        "amount_due": outstanding(row), "original_due_date": row.get("due_date"),
        "due_by": row.get("due_date") or row.get("reminder_date"),
        "reminder_date": row.get("reminder_date"), "reminder_time": _clean_time(row.get("reminder_time")),
        "message": row.get("notes"), "status": "active", "updated_at": iso_now(),
    }
    if existing:
        await sdb.payment_reminders.update_one({"id": existing["id"]}, {"$set": fields})
        return existing["id"]
    phone = None
    if row.get("vendor_id"):
        phone = ((await sdb.vendors_acc.find_one({"id": row["vendor_id"]}, {"_id": 0, "phone": 1})) or {}).get("phone")
    elif row.get("client_id"):
        phone = ((await sdb.clients.find_one({"id": row["client_id"]}, {"_id": 0, "phone": 1})) or {}).get("phone")
    seq = await next_sequence(org_id, "payment_reminder", 0)
    doc = {"id": new_id("rem_"), "number": f"PR-{seq:04d}", "auto": True,
           "source_type": source_type, "source_id": row["id"], "party_phone": phone,
           "created_at": iso_now(), "created_by": user_id or row.get("created_by"), **fields}
    await sdb.payment_reminders.insert_one(dict(doc))
    return doc["id"]


async def _upsert_event(org_id: str, source_type: str, row: dict, occ: list, party: str,
                        project_name: Optional[str], user_id: Optional[str]) -> str:
    eid = event_id(org_id, source_type, row["id"])
    main = next(t for label, t in occ if label == "main")
    before = max(0, min(30, int(row.get("remind_before_days") or 0)))
    alert_minutes = sorted({0, before * 1440})            # Google popups/emails
    repeat = row.get("repeat_every") if row.get("repeat_every") in REPEAT_CHOICES else "none"
    recurrence = None
    if repeat != "none":
        recurrence = [f"RRULE:FREQ={'DAILY' if repeat == 'daily' else 'WEEKLY'};COUNT={MAX_REPEATS + 1}"]
    due = row.get("due_date")
    notes = "\n".join(filter(None, [
        f"Amount still due: Rs. {_inr(outstanding(row))}",
        f"Due date: {due[8:10]}/{due[5:7]}/{due[:4]}" if due else None,
        f"Reference: {row['reference']}" if row.get("reference") else None,
        row.get("notes"),
        "Record the payment in Design Saga > Accounting > Collections Due when it arrives.",
    ]))
    doc = {
        "id": eid, "org_id": org_id, "title": _title(source_type, party, outstanding(row)),
        "kind": "reminder", "date": main[:10], "start_time": main[11:16], "end_time": None,
        "project_id": row.get("project_id"), "notes": notes,
        # ERP sound comes from the timed alerts; this stays None so the event's
        # own same-day check doesn't play it twice.
        "reminder_minutes": None, "alert_minutes": alert_minutes, "recurrence": recurrence,
        "visibility": "private", "attendee_ids": await _finance_user_ids(org_id), "employee_ids": [],
        "source_type": source_type, "source_id": row["id"], "collection_reminder": True,
        "updated_at": iso_now(),
    }
    existing = await sdb.calendar_events.find_one({"id": eid}, {"_id": 0, "id": 1})
    if existing:
        await sdb.calendar_events.update_one({"id": eid}, {"$set": doc})
    else:
        doc.update({"created_at": iso_now(), "created_by": user_id or row.get("created_by"),
                    "created_by_name": "Collections Due"})
        await sdb.calendar_events.insert_one(dict(doc))
    return eid


async def _replace_alerts(org_id: str, source_type: str, row: dict, occ: list,
                          title: str, project_name: Optional[str]) -> int:
    """Pending alerts mirror the current settings; ones already sent are kept."""
    wanted = {t: label for label, t in occ}
    now_key = now_local_key()
    pending = await sdb.reminder_alerts.find(
        {"source_type": source_type, "source_id": row["id"], "status": "pending"},
        {"_id": 0, "id": 1, "fire_at": 1}).to_list(200)
    for a in pending:
        if a["fire_at"] not in wanted:
            await sdb.reminder_alerts.update_one(
                {"id": a["id"], "status": "pending"},
                {"$set": {"status": "cancelled", "cancelled_at": iso_now(), "reason": "rescheduled"}})
    known = {a["fire_at"] async for a in sdb.reminder_alerts.find(
        {"source_type": source_type, "source_id": row["id"], "status": {"$in": ["pending", "sent"]}},
        {"_id": 0, "fire_at": 1})}
    added = 0
    for fire_at, label in wanted.items():
        if fire_at in known or fire_at < now_key[:16] and label != "main":
            continue
        await sdb.reminder_alerts.update_one(
            {"dedup": f"{org_id}:{source_type}:{row['id']}:{fire_at}"},
            {"$setOnInsert": {
                "id": new_id("ral_"), "org_id": org_id, "dedup": f"{org_id}:{source_type}:{row['id']}:{fire_at}",
                "source_type": source_type, "source_id": row["id"], "fire_at": fire_at,
                "label": label, "status": "pending", "created_at": iso_now()}},
            upsert=True)
        added += 1
    await sdb.reminder_alerts.update_many(
        {"source_type": source_type, "source_id": row["id"], "status": "pending"},
        {"$set": {"title": title, "project_name": project_name, "amount": outstanding(row),
                  "due_date": row.get("due_date")}})
    return added


async def _queue_google(org_id: str, eid: str, operation: str) -> None:
    try:
        from core.google_calendar import sync_source
        await sync_source(org_id, "calendar_event", eid, operation)
    except Exception:  # noqa: BLE001 - Google must never block ERP writes
        pass


async def refresh(source_type: str, source_id: str, user_id: Optional[str] = None) -> dict:
    """Bring alerts, calendar/Google event and reminder document in line with the row."""
    if source_type not in SOURCES:
        return {"skipped": True}
    org_id = current_org_id() or "org_default"
    row = await getattr(sdb, SOURCES[source_type]).find_one({"id": source_id}, {"_id": 0})
    occ = occurrences(row) if row else []
    eid = event_id(org_id, source_type, source_id)
    if not (is_active(row) and occ):
        await sdb.reminder_alerts.update_many(
            {"source_type": source_type, "source_id": source_id, "status": "pending"},
            {"$set": {"status": "cancelled", "cancelled_at": iso_now(),
                      "reason": "received" if row and outstanding(row) <= 0.004 else "closed"}})
        if await sdb.calendar_events.find_one({"id": eid}, {"_id": 0, "id": 1}):
            await sdb.calendar_events.delete_one({"id": eid})
            await _queue_google(org_id, eid, "delete")
        settled = bool(row) and outstanding(row) <= 0.004
        await sdb.payment_reminders.update_many(
            {"source_type": source_type, "source_id": source_id, "auto": True, "status": "active"},
            {"$set": {"status": "settled" if settled else "cancelled", "updated_at": iso_now(),
                      **({"amount_due": 0.0} if settled else {})}})
        return {"active": False}
    party, project_name = await _party_and_project(source_type, row)
    title = _title(source_type, party, outstanding(row))
    reminder_id = await _upsert_document(org_id, source_type, row, party, project_name, user_id)
    eid = await _upsert_event(org_id, source_type, row, occ, party, project_name, user_id)
    added = await _replace_alerts(org_id, source_type, row, occ, title, project_name)
    await _queue_google(org_id, eid, "upsert")
    return {"active": True, "event_id": eid, "reminder_id": reminder_id, "alerts_added": added}


async def refresh_all_open(limit: int = 500) -> int:
    """Catch-up for rows changed by other paths (reversals, older records)."""
    n = 0
    for source_type, coll in SOURCES.items():
        async for row in getattr(sdb, coll).find(
                {"$or": [{"reminder_date": {"$nin": [None, ""]}},
                         {"status": {"$in": ["received", "cancelled"]}}]},
                {"_id": 0, "id": 1}).limit(limit):
            await refresh(source_type, row["id"])
            n += 1
    return n


async def process_due_alerts(limit: int = 100) -> int:
    """Fire every alert whose time has come (all companies), exactly once."""
    from core.notifications import emit_finance
    from core.scoped_db import clear_scope, set_scope_from_user
    now_key = now_local_key()
    fired = 0
    for _ in range(limit):
        alert = await db.reminder_alerts.find_one_and_update(
            {"status": "pending", "fire_at": {"$lte": now_key}},
            {"$set": {"status": "sending", "claimed_at": iso_now()}},
            projection={"_id": 0})
        if not alert:
            break
        org_id = alert.get("org_id") or "org_default"
        set_scope_from_user({"org_id": org_id, "role": "Admin", "user_id": "system:reminders"})
        try:
            coll = SOURCES.get(alert["source_type"])
            row = await getattr(sdb, coll).find_one({"id": alert["source_id"]}, {"_id": 0}) if coll else None
            if not is_active(row):
                await db.reminder_alerts.update_one({"id": alert["id"]}, {"$set": {
                    "status": "cancelled", "reason": "received" if row else "closed"}})
                continue
            prefix = {"advance": "Coming up", "repeat": "Still due"}.get(alert.get("label"), "Reminder")
            due = alert.get("due_date")
            await emit_finance(
                "collection_reminder", f"{prefix}: {alert.get('title') or 'Payment reminder'}",
                " · ".join(filter(None, [alert.get("project_name"),
                                          f"due {due[8:10]}/{due[5:7]}/{due[:4]}" if due else None])),
                link="/invoices/reminders", priority="high",
                meta={"source_type": alert["source_type"], "source_id": alert["source_id"],
                      "alert_id": alert["id"], "sound": True},
                dedup_key=f"collection_alert:{alert['id']}", org_id=org_id)
            await db.reminder_alerts.update_one({"id": alert["id"]}, {"$set": {
                "status": "sent", "sent_at": iso_now()}})
            fired += 1
        except Exception:  # noqa: BLE001 - retry next minute
            await db.reminder_alerts.update_one({"id": alert["id"], "status": "sending"},
                                                {"$set": {"status": "pending"}})
        finally:
            clear_scope()
    return fired


async def recent_alerts_for(window_minutes: int = 10) -> list[dict]:
    """Alerts sent in the last few minutes (current company) — for the in-app sound."""
    since = (datetime.now(_tz()) - timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M")
    rows = await sdb.reminder_alerts.find(
        {"status": "sent", "fire_at": {"$gte": since, "$lte": now_local_key()}},
        {"_id": 0}).to_list(50)
    return rows
