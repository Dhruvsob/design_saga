"""Notifications API — poll, mark read, dismiss, daily scan.

All emit-side code lives in `core/notifications.py`. This module is
strictly the HTTP surface + the scheduled scanner.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel

from core.db import db
from core.scoped_db import sdb
from core.helpers import business_today, iso_now, now_utc
from core.deps import require_user
from core.access_control import unique_legacy_assignee_user_id
from core.notifications import emit, emit_admins, emit_finance
from core.tenancy import user_org_id
from core.rbac import has_any_permission


router = APIRouter()


class NotificationPreferencesIn(BaseModel):
    tasks: bool = True
    finance: bool = True
    attendance: bool = True
    calendar: bool = True


def _preference_response(row: Optional[dict] = None) -> dict:
    row = row or {}
    return {
        "tasks": row.get("tasks", True),
        "finance": row.get("finance", True),
        "attendance": row.get("attendance", True),
        "calendar": row.get("calendar", True),
    }


def _require_scan_permission(user: dict) -> None:
    if not has_any_permission(user, "*.*", "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")


def notification_owner_filter(user: dict, **extra) -> dict:
    """Bind personal notifications to both identity and current tenant.

    User IDs are globally random, but a platform administrator can reassign a
    user to another tenant. Filtering only by user_id would expose stale
    notifications from the previous company after that reassignment.
    """
    return {
        "user_id": user["user_id"],
        "org_id": user_org_id(user),
        **extra,
    }


# ==================================================
# List / count / mark read / dismiss
# ==================================================
@router.get("/notifications/preferences")
async def get_notification_preferences(
        request: Request,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    row = await db.notification_preferences.find_one(
        {"user_id": user["user_id"], "org_id": user_org_id(user)}, {"_id": 0})
    return _preference_response(row)


@router.put("/notifications/preferences")
async def update_notification_preferences(
        payload: NotificationPreferencesIn, request: Request,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    org_id = user_org_id(user)
    values = payload.model_dump()
    await db.notification_preferences.update_one(
        {"user_id": user["user_id"], "org_id": org_id},
        {"$set": {**values, "updated_at": iso_now()},
         "$setOnInsert": {"user_id": user["user_id"], "org_id": org_id}},
        upsert=True,
    )
    return values


@router.get("/notifications")
async def list_notifications(request: Request,
                             unread_only: bool = False,
                             kind: Optional[str] = None,
                             limit: int = 100,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q = notification_owner_filter(user)
    if unread_only:
        q["read"] = False
    if kind:
        q["kind"] = kind
    rows = await db.notifications.find(q, {"_id": 0}) \
                                 .sort("created_at", -1) \
                                 .limit(min(max(limit, 1), 500)).to_list(500)
    unread = await db.notifications.count_documents(
        notification_owner_filter(user, read=False))
    return {"unread_count": unread, "notifications": rows}


@router.get("/notifications/unread-count")
async def unread_count(request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    n = await db.notifications.count_documents(
        notification_owner_filter(user, read=False))
    return {"unread_count": n}


@router.post("/notifications/{ntf_id}/read")
async def mark_read(ntf_id: str, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    res = await db.notifications.update_one(
        notification_owner_filter(user, id=ntf_id),
        {"$set": {"read": True, "read_at": iso_now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/notifications/mark-all-read")
async def mark_all_read(request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    res = await db.notifications.update_many(
        notification_owner_filter(user, read=False),
        {"$set": {"read": True, "read_at": iso_now()}},
    )
    return {"ok": True, "marked": res.modified_count}


@router.delete("/notifications/{ntf_id}")
async def dismiss_notification(ntf_id: str, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await db.notifications.delete_one(notification_owner_filter(user, id=ntf_id))
    return {"ok": True}


# ==================================================
# Daily scanner — emits due / overdue notifications.
# Idempotent per day via dedup_key.
# ==================================================
async def run_scan(caller_org):
    """Scan due/overdue bills, invoices, milestones and tasks for ONE org and
    emit idempotent notifications. Callers must have already set the tenant
    scope (request dependency or scheduler's set_scope_from_user)."""
    today = business_today().isoformat()
    counts = {
        "vendor_bill_due": 0, "vendor_bill_overdue": 0,
        "invoice_due": 0, "invoice_overdue": 0,
        "milestone_due": 0, "milestone_overdue": 0,
        "collection_reminder": 0, "collection_due": 0,
        "collection_overdue": 0,
        "task_overdue": 0,
    }

    # ---- Vendor bills ---------------------------------------------------
    async for b in sdb.vendor_bills.find(
        {"status": {"$in": ["received", "partially_paid", "overdue"]},
         "due_date": {"$ne": None}}, {"_id": 0},
    ):
        due = b.get("due_date") or ""
        vendor_name = b.get("vendor_name", "vendor")
        outstanding = b.get("outstanding") or b.get("total") or 0
        if due < today:
            k = f"vbill_overdue:{b['id']}:{today}"
            counts["vendor_bill_overdue"] += await emit_finance(
                "vendor_bill_overdue",
                f"Vendor bill overdue · {vendor_name}",
                f"₹{outstanding:,.0f} · {b.get('bill_number','')} · due {due}",
                link=f"/vendors/{b['vendor_id']}",
                priority="high",
                meta={"bill_id": b["id"], "amount": outstanding},
                dedup_key=k,
                org_id=caller_org,
            )
        elif due == today:
            k = f"vbill_due:{b['id']}:{today}"
            counts["vendor_bill_due"] += await emit_finance(
                "vendor_bill_due",
                f"Vendor bill due today · {vendor_name}",
                f"₹{outstanding:,.0f} · {b.get('bill_number','')}",
                link=f"/vendors/{b['vendor_id']}",
                meta={"bill_id": b["id"], "amount": outstanding},
                dedup_key=k,
                org_id=caller_org,
            )

    # ---- Invoices -------------------------------------------------------
    async for inv in sdb.invoices.find(
        {"status": {"$in": ["sent", "overdue", "partially_paid"]},
         "doc_type": {"$ne": "quotation"}},
        {"_id": 0},
    ):
        due = inv.get("due_date") or ""
        if not due:
            continue
        client_name = inv.get("client_name", "client")
        amt = max(0.0, float(inv.get("total") or 0)
                  - float(inv.get("paid_amount") or 0))
        if amt <= 0:
            continue
        if due < today:
            k = f"inv_overdue:{inv['id']}:{today}"
            counts["invoice_overdue"] += await emit_finance(
                "invoice_overdue",
                f"Invoice overdue · {client_name}",
                f"₹{amt:,.0f} · {inv.get('number','')} · due {due}",
                link=f"/invoices/{inv['id']}",
                priority="high",
                meta={"invoice_id": inv["id"], "amount": amt},
                dedup_key=k,
                org_id=caller_org,
            )
        elif due == today:
            k = f"inv_due:{inv['id']}:{today}"
            counts["invoice_due"] += await emit_finance(
                "invoice_due",
                f"Invoice due today · {client_name}",
                f"₹{amt:,.0f} · {inv.get('number','')}",
                link=f"/invoices/{inv['id']}",
                meta={"invoice_id": inv["id"], "amount": amt},
                dedup_key=k,
                org_id=caller_org,
            )

    # ---- Payment milestones ---------------------------------------------
    async for m in sdb.payment_milestones.find(
        {"status": {"$nin": ["paid", "cancelled"]}}, {"_id": 0},
    ):
        due = m.get("due_date") or ""
        if not due:
            continue
        amt = max(0.0, float(m.get("amount") or 0)
                  - float(m.get("paid_amount") or 0))
        if amt <= 0:
            continue
        proj = m.get("project_id")
        if due < today:
            k = f"ms_overdue:{m.get('id')}:{today}"
            counts["milestone_overdue"] += await emit_finance(
                "milestone_overdue",
                f"Milestone overdue · {m.get('title','Payment')}",
                f"₹{amt:,.0f} · due {due}",
                link=f"/projects/{proj}" if proj else "/accounting",
                priority="high",
                meta={"milestone_id": m.get("id"), "amount": amt},
                dedup_key=k,
                org_id=caller_org,
            )
        elif due == today:
            k = f"ms_due:{m.get('id')}:{today}"
            counts["milestone_due"] += await emit_finance(
                "milestone_due",
                f"Milestone due today · {m.get('title','Payment')}",
                f"₹{amt:,.0f}",
                link=f"/projects/{proj}" if proj else "/accounting",
                meta={"milestone_id": m.get("id"), "amount": amt},
                dedup_key=k,
                org_id=caller_org,
            )

    # ---- Planned commissions and other receivables ---------------------
    collection_sources = (
        (sdb.vendor_commissions,
         {"status": {"$in": ["pending", "invoiced"]}}, "vendor_commission"),
        (sdb.collection_receivables,
         {"status": {"$in": ["pending", "partially_received"]}}, "other_receivable"),
    )
    for collection, query, source_type in collection_sources:
        async for row in collection.find(query, {"_id": 0}):
            amount = max(0.0, float(row.get("amount") or 0)
                         - float(row.get("received_amount") or 0))
            if amount <= 0:
                continue
            due = row.get("due_date") or ""
            reminder = row.get("reminder_date") or ""
            party = (row.get("vendor_name") or row.get("name")
                     or row.get("reference") or "Expected collection")
            if reminder == today and due != today:
                key = f"collection_reminder:{source_type}:{row['id']}:{today}"
                counts["collection_reminder"] += await emit_finance(
                    "collection_reminder",
                    f"Collection reminder · {party}",
                    f"₹{amount:,.0f}" + (f" · due {due}" if due else ""),
                    link="/accounting",
                    meta={"source_type": source_type, "source_id": row["id"],
                          "amount": amount},
                    dedup_key=key, org_id=caller_org,
                )
            if due and due < today:
                key = f"collection_overdue:{source_type}:{row['id']}:{today}"
                counts["collection_overdue"] += await emit_finance(
                    "collection_overdue",
                    f"Collection overdue · {party}",
                    f"₹{amount:,.0f} · due {due}",
                    link="/accounting", priority="high",
                    meta={"source_type": source_type, "source_id": row["id"],
                          "amount": amount},
                    dedup_key=key, org_id=caller_org,
                )
            elif due == today:
                key = f"collection_due:{source_type}:{row['id']}:{today}"
                counts["collection_due"] += await emit_finance(
                    "collection_due",
                    f"Collection due today · {party}",
                    f"₹{amount:,.0f}", link="/accounting",
                    meta={"source_type": source_type, "source_id": row["id"],
                          "amount": amount},
                    dedup_key=key, org_id=caller_org,
                )

    # ---- Overdue tasks (per assignee) -----------------------------------
    async for t in sdb.tasks.find(
        {"status": {"$ne": "done"},
         "due_date": {"$lt": today, "$ne": None}}, {"_id": 0},
    ):
        # Find the assignee's user_id from `assignee_name` (best-effort).
        assignee_uid = t.get("assignee_id")
        if not assignee_uid and t.get("assignee_name"):
            assignee_uid = await unique_legacy_assignee_user_id(
                caller_org, t["assignee_name"])
        if not assignee_uid:
            continue
        k = f"task_overdue:{t['id']}:{today}"
        counts["task_overdue"] += await emit(
            [assignee_uid], "task_overdue",
            f"Task overdue · {t.get('title','Task')[:60]}",
            f"Was due {t.get('due_date')}",
            link=f"/tasks/{t['id']}",
            priority="high",
            meta={"task_id": t["id"]},
            dedup_key=k,
        )

    return {"ok": True, "date": today, "emitted": counts}


@router.post("/notifications/scan")
async def scan_and_emit(request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """Manually trigger the tenant scan; routine scans run in the scheduler."""
    user = await require_user(request, session_token, authorization)
    _require_scan_permission(user)
    return await run_scan(user_org_id(user))


async def scheduled_scan_all_orgs():
    """Daily automated scan across every active organisation (no manual
    bell-click needed). Invoked from the server's background scheduler."""
    from core.scoped_db import set_scope_from_user, clear_scope
    results = {}
    org_ids = [o["org_id"] async for o in db.organizations.find(
        {"status": {"$ne": "suspended"}}, {"_id": 0, "org_id": 1})]
    for oid in org_ids:
        try:
            set_scope_from_user({"org_id": oid, "email": "", "is_super_admin": False})
            results[oid] = (await run_scan(oid)).get("emitted")
        except Exception as exc:            # never let one org break the loop
            results[oid] = {"error": str(exc)[:200]}
        finally:
            clear_scope()
    return results
