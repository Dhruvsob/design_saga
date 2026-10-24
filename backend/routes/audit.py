"""Audit log read endpoints.

- Company Admins see the audit for their own org only (scoped via sdb).
- SuperAdmin sees all rows across the platform (scope-free).
- Per-record activity is only shown when the caller can read that record.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional

from core.db import db
from core.scoped_db import sdb
from core.deps import require_user
from core.rbac import has_permission, has_any_permission
from core.tenancy import is_super_admin, user_org_id
from core.audit import verify_chain
from core.access_control import get_visible_project, get_visible_purchase_order, get_visible_task


router = APIRouter()

# target_type -> permissions (any) required to read that record's history
_ACTIVITY_PERMS = {
    "lead": ("leads.read",),
    "client": ("clients.read",),
    "invoice": ("invoices.read", "finance.read"),
    "journal_entry": ("finance.read",),
    "bank_batch": ("finance.read",),
    "loan": ("finance.read", "loans.read"),
    "vendor": ("vendors.read",),
    "holiday": ("holidays.read",),
    "employee": ("employees.update", "hr.read"),
    "attendance": ("attendance.approve", "attendance.update"),
    "attendance_correction": ("attendance.approve", "attendance.update"),
    "leave": ("attendance.approve", "leave.approve"),
    "calendar_event": ("calendar.read",),
    "policy": ("*.*",),
    "org": ("*.*",),
}


@router.get("/audit-log")
async def list_audit(request: Request, limit: int = 200,
                     action: Optional[str] = None,
                     actor_id: Optional[str] = None,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not (has_permission(user, "*.*") or is_super_admin(user)):
        raise HTTPException(403, "Admin only")
    q: dict = {}
    if action:
        q["action"] = action
    if actor_id:
        q["actor_id"] = actor_id
    # SuperAdmin uses raw db (cross-org); Company Admin uses sdb (scoped)
    if is_super_admin(user):
        cursor = db.audit_log.find(q, {"_id": 0})
    else:
        cursor = sdb.audit_log.find(q, {"_id": 0})
    limit = max(1, min(limit, 1000))
    rows = await cursor.sort("at", -1).limit(limit).to_list(limit)
    return rows


@router.get("/audit-log/verify")
async def verify_audit(request: Request, org_id: Optional[str] = None,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    """Recompute the tamper-evident hash chain for an organisation."""
    user = await require_user(request, session_token, authorization)
    if is_super_admin(user):
        chain = org_id or user_org_id(user) or "platform"
    elif has_permission(user, "*.*"):
        chain = user_org_id(user) or "org_default"
    else:
        raise HTTPException(403, "Admin only")
    return await verify_chain(chain)


@router.get("/activity/{target_type}/{target_id}")
async def record_activity(target_type: str, target_id: str, request: Request,
                          limit: int = 100,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Per-record activity timeline, shown only for records the caller can read."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        if target_type == "project":
            await get_visible_project(user, target_id)
        elif target_type == "task":
            await get_visible_task(user, target_id)
        elif target_type == "po":
            await get_visible_purchase_order(user, target_id)
        elif target_type == "grn":
            if not has_permission(user, "purchase_orders.read"):
                raise HTTPException(404, "Not found")
            grn = await sdb.goods_receipts.find_one({"id": target_id}, {"_id": 0, "po_id": 1})
            if not grn or not grn.get("po_id"):
                raise HTTPException(404, "Not found")
            await get_visible_purchase_order(user, grn["po_id"], projection={"_id": 0, "id": 1})
        elif target_type == "expense":
            if not has_any_permission(user, "finance.read", "expenses.update", "expenses.approve"):
                own = await sdb.expenses.find_one({"id": target_id, "claimant_id": user["user_id"]},
                                                  {"_id": 1})
                if not own:
                    raise HTTPException(404, "Not found")
        else:
            perms = _ACTIVITY_PERMS.get(target_type)
            if not perms or not has_any_permission(user, *perms):
                raise HTTPException(404, "Not found")
    limit = max(1, min(limit, 500))
    rows = await sdb.audit_log.find(
        {"target": target_id, "target_type": target_type}, {"_id": 0}
    ).sort("at", -1).limit(limit).to_list(limit)
    return rows
