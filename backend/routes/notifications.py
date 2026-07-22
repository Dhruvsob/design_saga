"""Notifications API — poll, mark read, dismiss, daily scan.

All emit-side code lives in `core/notifications.py`. This module is
strictly the HTTP surface + the scheduled scanner.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional
from datetime import datetime, timezone, timedelta

from core.db import db
from core.helpers import iso_now, now_utc
from core.deps import require_user
from core.notifications import emit, emit_admins, emit_finance


router = APIRouter()


# ==================================================
# List / count / mark read / dismiss
# ==================================================
@router.get("/notifications")
async def list_notifications(request: Request,
                             unread_only: bool = False,
                             kind: Optional[str] = None,
                             limit: int = 100,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q: dict = {"user_id": user["user_id"]}
    if unread_only:
        q["read"] = False
    if kind:
        q["kind"] = kind
    rows = await db.notifications.find(q, {"_id": 0}) \
                                 .sort("created_at", -1) \
                                 .limit(min(max(limit, 1), 500)).to_list(500)
    unread = await db.notifications.count_documents(
        {"user_id": user["user_id"], "read": False}
    )
    return {"unread_count": unread, "notifications": rows}


@router.get("/notifications/unread-count")
async def unread_count(request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    n = await db.notifications.count_documents(
        {"user_id": user["user_id"], "read": False}
    )
    return {"unread_count": n}


@router.post("/notifications/{ntf_id}/read")
async def mark_read(ntf_id: str, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    res = await db.notifications.update_one(
        {"id": ntf_id, "user_id": user["user_id"]},
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
        {"user_id": user["user_id"], "read": False},
        {"$set": {"read": True, "read_at": iso_now()}},
    )
    return {"ok": True, "marked": res.modified_count}


@router.delete("/notifications/{ntf_id}")
async def dismiss_notification(ntf_id: str, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await db.notifications.delete_one({"id": ntf_id, "user_id": user["user_id"]})
    return {"ok": True}


# ==================================================
# Daily scanner — emits due / overdue notifications.
# Idempotent per day via dedup_key.
# ==================================================
@router.post("/notifications/scan")
async def scan_and_emit(request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """Trigger a scan. Any authenticated user can hit this — it's cheap and
    idempotent (each notification has a per-day dedup_key)."""
    await require_user(request, session_token, authorization)

    today = now_utc().date().isoformat()
    counts = {
        "vendor_bill_due": 0, "vendor_bill_overdue": 0,
        "invoice_due": 0, "invoice_overdue": 0,
        "milestone_due": 0, "milestone_overdue": 0,
        "task_overdue": 0,
    }

    # ---- Vendor bills ---------------------------------------------------
    async for b in db.vendor_bills.find(
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
            )

    # ---- Invoices -------------------------------------------------------
    async for inv in db.invoices.find(
        {"status": {"$in": ["sent", "overdue"]}, "doc_type": {"$ne": "quotation"}},
        {"_id": 0},
    ):
        due = inv.get("due_date") or ""
        if not due:
            continue
        client_name = inv.get("client_name", "client")
        amt = inv.get("total") or 0
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
            )

    # ---- Payment milestones ---------------------------------------------
    async for m in db.payment_milestones.find(
        {"status": {"$ne": "paid"}}, {"_id": 0},
    ):
        due = m.get("due_date") or ""
        if not due:
            continue
        amt = m.get("amount") or 0
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
            )

    # ---- Overdue tasks (per assignee) -----------------------------------
    async for t in db.tasks.find(
        {"status": {"$ne": "done"},
         "due_date": {"$lt": today, "$ne": None}}, {"_id": 0},
    ):
        # Find the assignee's user_id from `assignee_name` (best-effort).
        assignee_uid = t.get("assignee_id")
        if not assignee_uid and t.get("assignee_name"):
            u = await db.users.find_one({"name": t["assignee_name"]}, {"_id": 0, "user_id": 1})
            if u:
                assignee_uid = u["user_id"]
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
