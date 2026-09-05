"""FastAPI dependencies for authentication + permission checks."""
from typing import Optional
from datetime import datetime, timezone
from fastapi import HTTPException, Request, Cookie, Header

from .db import db
from .helpers import now_utc
from .rbac import has_permission, normalize_role, expand_permissions, PROTECTED_ROLES
from .scoped_db import set_scope_from_user, clear_scope


async def resolve_permissions(role, org_id):
    """Effective permissions for a role in a tenant.

    Returns the tenant's saved override for the role if one exists, otherwise
    the static role default. Protected roles (SuperAdmin/Admin) and SuperAdmins
    with no tenant always get the static defaults (never editable)."""
    role = normalize_role(role)
    if role in PROTECTED_ROLES or not org_id:
        return expand_permissions(role)
    try:
        doc = await db.role_permissions.find_one(
            {"org_id": org_id, "role": role}, {"_id": 0, "permissions": 1})
    except Exception:
        doc = None
    if doc and isinstance(doc.get("permissions"), list):
        return list(doc["permissions"])
    return expand_permissions(role)


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        clear_scope()
        return None

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        clear_scope()
        return None

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < now_utc():
        clear_scope()
        return None

    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if user:
        # Attach effective (override-aware) permissions so has_permission and
        # the frontend both honour any per-tenant role customisation.
        try:
            from .tenancy import user_org_id
            user["permissions"] = await resolve_permissions(user.get("role"), user_org_id(user))
        except Exception:
            pass
    set_scope_from_user(user)
    return user


async def require_user(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Approval / active gates — pending or rejected users cannot use protected routes.
    status = user.get("approval_status")
    if status == "pending":
        raise HTTPException(status_code=403,
                            detail="Your account is awaiting Admin approval.")
    if status == "rejected" or user.get("is_active") is False:
        raise HTTPException(status_code=403,
                            detail="Your account has been deactivated. Contact an Admin.")
    # Org suspension gate — suspended/deactivated tenants are locked out
    # (SuperAdmins are exempt so they can administer the platform).
    if user.get("org_id") and not user.get("is_super_admin"):
        org = await db.organizations.find_one(
            {"org_id": user["org_id"]},
            {"_id": 0, "is_suspended": 1, "is_active": 1})
        if org and (org.get("is_suspended") or org.get("is_active") is False):
            raise HTTPException(status_code=403,
                                detail="Your organisation is suspended. Contact support.")
    # Tenant scope re-affirmed (get_current_user already set it)
    set_scope_from_user(user)
    return user


def require_permission(perm: str):
    async def _dep(
        request: Request,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        user = await require_user(request, session_token, authorization)
        if not has_permission(user, perm):
            raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")
        return user
    return _dep
