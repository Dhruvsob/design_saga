"""Notification Center — the single toast bus for the entire ERP.

Design goals
------------
* One collection: `notifications` — every module writes here via `emit()`.
* Poll-based delivery (frontend hits GET /notifications every 30s).
  Architected so WebSockets can be added later WITHOUT touching call sites —
  emit() just needs to also push to a channel.
* Idempotent per-day dedup keys so the daily scanner can safely be re-run.

Notification schema
-------------------
{
  id, user_id,           # recipient
  kind,                  # task_assigned | task_due | task_overdue |
                         # vendor_bill_due | vendor_bill_overdue |
                         # invoice_due | invoice_overdue |
                         # milestone_due | milestone_overdue |
                         # leave_request | leave_decided |
                         # attendance_pending | payroll_due | account_approved | account_rejected
  title, body,           # short user-facing strings
  link,                  # relative frontend path e.g. "/tasks/tsk_xxx"
  priority,              # low | normal | high | urgent
  read,                  # bool
  meta,                  # dict — free-form context (amount, project_id, …)
  dedup_key,             # optional; unique per (user_id, dedup_key) to avoid dupes
  created_at, expires_at (optional)
}
"""
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from core.db import db
from core.helpers import iso_now, new_id


VALID_KINDS = {
    "task_assigned", "task_due", "task_overdue",
    "vendor_bill_due", "vendor_bill_overdue",
    "invoice_due", "invoice_overdue",
    "milestone_due", "milestone_overdue",
    "leave_request", "leave_decided",
    "attendance_pending", "attendance_decided", "payroll_due",
    "account_approved", "account_rejected",
    "meeting", "reminder",
    "info",
}


async def emit(user_ids: List[str], kind: str, title: str, body: str = "",
               link: Optional[str] = None, priority: str = "normal",
               meta: Optional[dict] = None, dedup_key: Optional[str] = None,
               expires_at: Optional[str] = None) -> int:
    """Fan-out a notification to N users. Returns number of docs inserted."""
    if not user_ids:
        return 0
    if kind not in VALID_KINDS:
        kind = "info"
    now_iso = iso_now()
    # Resolve each recipient's org so notifications stay tenant-tagged.
    org_by_uid = {}
    async for u in db.users.find({"user_id": {"$in": [x for x in set(user_ids) if x]}},
                                 {"_id": 0, "user_id": 1, "org_id": 1}):
        org_by_uid[u["user_id"]] = u.get("org_id")
    docs = []
    for uid in set(user_ids):
        if not uid:
            continue
        # Dedup — if a doc with the same key already exists for this user, skip.
        if dedup_key:
            existing = await db.notifications.find_one(
                {"user_id": uid, "dedup_key": dedup_key}, {"_id": 0, "id": 1},
            )
            if existing:
                continue
        docs.append({
            "id": new_id("ntf_"),
            "user_id": uid,
            "org_id": org_by_uid.get(uid),
            "kind": kind,
            "title": title,
            "body": body,
            "link": link,
            "priority": priority,
            "meta": meta or {},
            "read": False,
            "dedup_key": dedup_key,
            "created_at": now_iso,
            "expires_at": expires_at,
        })
    if docs:
        await db.notifications.insert_many(docs)
    return len(docs)


async def emit_admins(kind: str, title: str, body: str = "",
                      link: Optional[str] = None, priority: str = "normal",
                      meta: Optional[dict] = None, dedup_key: Optional[str] = None,
                      org_id: Optional[str] = None) -> int:
    """Broadcast to active Admin / Director users. Pass `org_id` to keep the
    fan-out tenant-scoped (REQUIRED for anything triggered inside an org)."""
    q = {"role": {"$in": ["Admin", "Director"]}, "is_active": {"$ne": False}}
    if org_id:
        q["org_id"] = org_id
    ids = []
    async for u in db.users.find(q, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    return await emit(ids, kind, title, body, link, priority, meta, dedup_key)


async def emit_finance(kind: str, title: str, body: str = "",
                       link: Optional[str] = None, priority: str = "normal",
                       meta: Optional[dict] = None, dedup_key: Optional[str] = None,
                       org_id: Optional[str] = None) -> int:
    """Broadcast to Admin / Director / Accountant (tenant-scoped via org_id)."""
    q = {"role": {"$in": ["Admin", "Director", "Accountant"]}, "is_active": {"$ne": False}}
    if org_id:
        q["org_id"] = org_id
    ids = []
    async for u in db.users.find(q, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    return await emit(ids, kind, title, body, link, priority, meta, dedup_key)


async def emit_hr(kind: str, title: str, body: str = "",
                  link: Optional[str] = None, priority: str = "normal",
                  meta: Optional[dict] = None, dedup_key: Optional[str] = None,
                  org_id: Optional[str] = None) -> int:
    q = {"role": {"$in": ["Admin", "Director", "HR"]}, "is_active": {"$ne": False}}
    if org_id:
        q["org_id"] = org_id
    ids = []
    async for u in db.users.find(q, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    return await emit(ids, kind, title, body, link, priority, meta, dedup_key)
