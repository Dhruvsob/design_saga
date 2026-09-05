"""Audit log read endpoint.

- Company Admins see the audit for their own org only (scoped via sdb).
- SuperAdmin sees all rows across the platform (scope-free).
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional

from core.db import db
from core.scoped_db import sdb
from core.deps import require_user
from core.rbac import has_permission
from core.tenancy import is_super_admin


router = APIRouter()


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
    rows = await cursor.sort("at", -1).limit(max(1, min(limit, 1000))).to_list(limit)
    return rows


@router.get("/activity/{target_type}/{target_id}")
async def record_activity(target_type: str, target_id: str, request: Request,
                          limit: int = 100,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Per-record activity timeline — any authenticated org member can see
    the who-did-what history for records they can access."""
    await require_user(request, session_token, authorization)
    rows = await sdb.audit_log.find(
        {"target": target_id, "target_type": target_type}, {"_id": 0}
    ).sort("at", -1).limit(max(1, min(limit, 500))).to_list(limit)
    return rows
