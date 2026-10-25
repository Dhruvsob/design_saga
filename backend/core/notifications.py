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
  dedup_key,             # optional; unique per (org_id, user_id, dedup_key)
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

NOTIFICATION_CATEGORY_BY_KIND = {
    "task_assigned": "tasks", "task_due": "tasks", "task_overdue": "tasks",
    "vendor_bill_due": "finance", "vendor_bill_overdue": "finance",
    "invoice_due": "finance", "invoice_overdue": "finance",
    "milestone_due": "finance", "milestone_overdue": "finance",
    "payroll_due": "finance",
    "leave_request": "attendance", "leave_decided": "attendance",
    "attendance_pending": "attendance", "attendance_decided": "attendance",
    "meeting": "calendar", "reminder": "calendar",
}

# Account state messages must always reach the affected user.
MANDATORY_KINDS = {"account_approved", "account_rejected", "info"}


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
    async for u in db.users.find({
            "user_id": {"$in": [x for x in set(user_ids) if x]},
            "is_active": {"$ne": False},
            "approval_status": {"$nin": ["pending", "rejected"]},
        },
                                 {"_id": 0, "user_id": 1, "org_id": 1}):
        org_by_uid[u["user_id"]] = u.get("org_id") or "org_default"
    # Tenant isolation: inside a tenant request, recipients from any other
    # organisation (or unknown users) are silently dropped.
    from core.scoped_db import current_org_id
    scope_org = current_org_id()
    preferences = {}
    candidate_ids = list(org_by_uid)
    if kind not in MANDATORY_KINDS and candidate_ids:
        preference_keys = [
            {"user_id": uid, "org_id": org_by_uid[uid]}
            for uid in candidate_ids
        ]
        async for pref in db.notification_preferences.find(
                {"$or": preference_keys}, {"_id": 0}):
            preferences[(pref.get("user_id"), pref.get("org_id"))] = pref
    category = NOTIFICATION_CATEGORY_BY_KIND.get(kind)
    docs = []
    for uid in set(user_ids):
        if not uid:
            continue
        if uid not in org_by_uid:
            continue
        if scope_org and org_by_uid[uid] != scope_org:
            continue
        pref_key = (uid, org_by_uid[uid])
        if category and preferences.get(pref_key, {}).get(category) is False:
            continue
        doc = {
            "id": new_id("ntf_"),
            "user_id": uid,
            "org_id": org_by_uid[uid],
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
        }
        if dedup_key:
            # Include tenant ownership so reassignment cannot let a stale row
            # in the previous company suppress a valid notification in the
            # user's new company.
            doc["dedup_id"] = f"{doc['org_id'] or 'org_default'}:{uid}:{dedup_key}"
        docs.append(doc)
    if not docs:
        return 0
    if not dedup_key:
        await db.notifications.insert_many(docs)
        return len(docs)
    inserted = 0
    for doc in docs:
        result = await db.notifications.update_one(
            {"dedup_id": doc["dedup_id"]}, {"$setOnInsert": doc}, upsert=True)
        inserted += int(getattr(result, "upserted_id", None) is not None)
    return inserted


async def emit_admins(kind: str, title: str, body: str = "",
                      link: Optional[str] = None, priority: str = "normal",
                      meta: Optional[dict] = None, dedup_key: Optional[str] = None,
                      org_id: Optional[str] = None) -> int:
    """Broadcast to active Admin / Director users. Pass `org_id` to keep the
    fan-out tenant-scoped (REQUIRED for anything triggered inside an org)."""
    q = {"role": {"$in": ["Admin", "Director"]}, "is_active": {"$ne": False}}
    if not org_id:
        from core.scoped_db import current_org_id
        org_id = current_org_id()
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
    if not org_id:
        from core.scoped_db import current_org_id
        org_id = current_org_id()
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
    if not org_id:
        from core.scoped_db import current_org_id
        org_id = current_org_id()
    if org_id:
        q["org_id"] = org_id
    ids = []
    async for u in db.users.find(q, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    return await emit(ids, kind, title, body, link, priority, meta, dedup_key)
