"""Password authentication + admin approval workflow.

Coexists with the existing Emergent Google OAuth flow (see /api/auth/session in
server.py). Both flows use the SAME `session_token` cookie + `user_sessions`
collection so front-end auth code stays unchanged.

Endpoints
---------
- POST /api/auth/login-password   — email OR employee_id + password → session
- POST /api/auth/change-password  — self (logged-in) — old + new
- POST /api/auth/register         — Admin-only. Create a user w/ password.
- POST /api/auth/reset-password/{user_id} — Admin-only.
- POST /api/rbac/users/{user_id}/approve — Admin-only. Approve pending user.
- POST /api/rbac/users/{user_id}/reject  — Admin-only. Reject / deactivate.
- GET  /api/rbac/pending          — list pending-approval users.

Design decisions
----------------
* bcrypt via `passlib` (already in requirements.txt).
* Brute-force: `login_attempts` collection keyed by identifier; 5 fails / 15 min
  → 429 with lockout timer.
* Session tokens are UUID hex — same shape as Google flow — stored in
  `user_sessions` with 7-day expiry. Cookie set as httpOnly + secure + SameSite=None.
* Employee ID auto-assigned on user creation: `DS0001`, `DS0002`, …
"""
from fastapi import APIRouter, HTTPException, Request, Response, Cookie, Header
from typing import Optional
from datetime import datetime, timezone, timedelta
from passlib.hash import bcrypt
import uuid
import re

from core.db import db
from core.helpers import iso_now, now_utc, new_id
from core.deps import require_user, get_current_user
from core.rbac import has_permission, ROLES, normalize_role, expand_permissions
from models.user import (
    RegisterIn, LoginPasswordIn, ChangePasswordIn,
    ResetPasswordIn, ApprovalDecisionIn,
)


router = APIRouter()

MAX_FAILED = 5
LOCKOUT_MINUTES = 15
EMPLOYEE_ID_PATTERN = re.compile(r"^DS\d{4,}$", re.IGNORECASE)


# ==================================================
# helpers
# ==================================================
def hash_password(pw: str) -> str:
    return bcrypt.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(pw, hashed)
    except Exception:
        return False


async def _next_employee_id() -> str:
    """Sequential DS0001, DS0002 …  Safe against gaps because we take max+1."""
    max_num = 0
    async for u in db.users.find({"employee_id": {"$regex": "^DS\\d+$"}},
                                 {"_id": 0, "employee_id": 1}):
        try:
            n = int(u["employee_id"][2:])
            if n > max_num:
                max_num = n
        except (ValueError, KeyError):
            pass
    return f"DS{(max_num + 1):04d}"


def _pack_user(u: dict) -> dict:
    """Public projection: strips password_hash, adds `permissions`, `org_id`."""
    out = {k: v for k, v in u.items() if k != "password_hash"}
    role = normalize_role(u.get("role"))
    out["role"] = role
    out["permissions"] = expand_permissions(role)
    # Multi-tenant fields
    from core.tenancy import DEFAULT_ORG_ID, SUPER_ADMIN_EMAILS as _SA
    if role != "SuperAdmin":
        out.setdefault("org_id", DEFAULT_ORG_ID)
    out["is_super_admin"] = (
        role == "SuperAdmin"
        or (out.get("email") or "").strip().lower() in _SA
    )
    return out


async def _set_session_cookie(response: Response, user_id: str) -> str:
    """Create a session row and set the httpOnly cookie. Returns token."""
    token = uuid.uuid4().hex
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "expires_at": now_utc() + timedelta(days=7),
        "created_at": now_utc(),
    })
    response.set_cookie(
        key="session_token", value=token,
        httponly=True, secure=True, samesite="none",
        path="/", max_age=7 * 24 * 3600,
    )
    return token


async def _register_failed_attempt(identifier: str):
    await db.login_attempts.insert_one({
        "identifier": identifier.lower(),
        "at": now_utc(),
    })


async def _check_lockout(identifier: str):
    cutoff = now_utc() - timedelta(minutes=LOCKOUT_MINUTES)
    n = await db.login_attempts.count_documents({
        "identifier": identifier.lower(),
        "at": {"$gte": cutoff},
    })
    if n >= MAX_FAILED:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again after {LOCKOUT_MINUTES} minutes.",
        )


async def _clear_attempts(identifier: str):
    await db.login_attempts.delete_many({"identifier": identifier.lower()})


# ==================================================
# LOGIN (password)
# ==================================================
@router.post("/auth/login-password")
async def login_password(payload: LoginPasswordIn, response: Response):
    ident = payload.identifier.strip()
    if not ident:
        raise HTTPException(status_code=400, detail="Identifier required")

    await _check_lockout(ident)

    # Look up by email OR employee_id.
    # IMPORTANT (multi-tenant): employee_id is per-organisation — every org's
    # first admin starts at DS0001 — so it is NOT globally unique and the same
    # id legitimately exists across tenants. Email *should* be unique but we
    # defend against duplicates too. Using find_one() here would always resolve
    # to a single fixed user, so admins of *other* tenants sharing that id would
    # be rejected with "invalid credentials" even with the correct password.
    # Fix: fetch ALL candidates for the identifier and authenticate against the
    # one whose password actually matches.
    query: dict
    if EMPLOYEE_ID_PATTERN.match(ident):
        query = {"employee_id": ident.upper()}
    else:
        query = {"email": ident.lower()}
    candidates = await db.users.find(query, {"_id": 0}).to_list(50)

    user = None
    for cand in candidates:
        if cand.get("password_hash") and verify_password(payload.password, cand["password_hash"]):
            user = cand
            break

    if user is None:
        await _register_failed_attempt(ident)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Approval / active gates
    if user.get("approval_status") == "pending":
        raise HTTPException(status_code=403,
                            detail="Your account is awaiting Admin approval.")
    if user.get("approval_status") == "rejected" or user.get("is_active") is False:
        raise HTTPException(status_code=403,
                            detail="Your account has been deactivated. Contact an Admin.")
    # Org suspension gate — block login for suspended/deactivated tenants
    if user.get("org_id") and not user.get("is_super_admin"):
        _org = await db.organizations.find_one(
            {"org_id": user["org_id"]},
            {"_id": 0, "is_suspended": 1, "is_active": 1})
        if _org and (_org.get("is_suspended") or _org.get("is_active") is False):
            raise HTTPException(status_code=403,
                                detail="Your organisation is suspended. Contact support.")

    await _clear_attempts(ident)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_login": iso_now()}},
    )
    token = await _set_session_cookie(response, user["user_id"])
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"user": _pack_user(fresh), "session_token": token}


# ==================================================
# CHANGE PASSWORD (self)
# ==================================================
@router.post("/auth/change-password")
async def change_password(payload: ChangePasswordIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not user.get("password_hash"):
        raise HTTPException(status_code=400,
                            detail="This account has no password (Google-only). "
                                   "Ask an Admin to set one.")
    if not verify_password(payload.old_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Old password is incorrect")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "password_updated_at": iso_now()}}
    )
    return {"ok": True}


# ==================================================
# REGISTER (Admin creates a user)
# ==================================================
@router.post("/auth/register")
async def admin_register(payload: RegisterIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    admin = await require_user(request, session_token, authorization)
    if not has_permission(admin, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")

    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")

    # Plan limit — max users per tenant
    from core.tenancy import user_org_id
    _org_id = user_org_id(admin)
    if _org_id:
        _org = await db.organizations.find_one({"org_id": _org_id}, {"_id": 0, "features": 1})
        _max = ((_org or {}).get("features") or {}).get("limits", {}).get("max_users")
        if _max:
            _current = await db.users.count_documents(
                {"org_id": _org_id, "is_active": {"$ne": False}})
            if _current >= _max:
                raise HTTPException(status_code=402,
                                    detail=f"User limit reached ({_current}/{_max}). Upgrade your plan.")

    role = normalize_role(payload.role)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    employee_id = await _next_employee_id()
    # Multi-tenant: new users inherit the admin's org
    from core.tenancy import user_org_id
    doc = {
        "user_id": user_id,
        "org_id": user_org_id(admin),
        "employee_id": employee_id,
        "email": email,
        "name": payload.name.strip(),
        "phone": payload.phone,
        "role": role,
        "password_hash": hash_password(payload.password),
        "is_active": True,
        "approval_status": "approved" if payload.approve_immediately else "pending",
        "auth_type": "password",
        "created_at": iso_now(),
        "created_by": admin["user_id"],
    }
    await db.users.insert_one(dict(doc))
    return _pack_user(doc)


# ==================================================
# RESET PASSWORD (Admin)
# ==================================================
@router.post("/auth/reset-password/{user_id}")
async def admin_reset_password(user_id: str, payload: ResetPasswordIn, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    admin = await require_user(request, session_token, authorization)
    if not has_permission(admin, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "password_updated_at": iso_now(),
                  "password_reset_by": admin["user_id"]}}
    )
    # Invalidate every active session of the target so they must re-login.
    await db.user_sessions.delete_many({"user_id": user_id})
    return {"ok": True}


# ==================================================
# APPROVAL WORKFLOW
# ==================================================
@router.get("/rbac/pending")
async def list_pending(request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    admin = await require_user(request, session_token, authorization)
    if not has_permission(admin, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")
    rows = await db.users.find({"approval_status": "pending"}, {"_id": 0}) \
                         .sort("created_at", 1).to_list(200)
    return [_pack_user(u) for u in rows]


@router.post("/rbac/users/{user_id}/approve")
async def approve_user(user_id: str, payload: ApprovalDecisionIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    admin = await require_user(request, session_token, authorization)
    if not has_permission(admin, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.decision == "approve":
        role = normalize_role(payload.role or target.get("role") or "Employee")
        # Assign employee_id if missing
        emp_id = target.get("employee_id") or await _next_employee_id()
        await db.users.update_one({"user_id": user_id}, {"$set": {
            "approval_status": "approved",
            "is_active": True,
            "role": role,
            "employee_id": emp_id,
            "approved_at": iso_now(),
            "approved_by": admin["user_id"],
        }})
        # Notify the newly approved user
        try:
            from core.notifications import emit as _notify
            await _notify(
                [user_id], "account_approved",
                "Your account is approved.",
                body=f"Welcome aboard. You've been assigned the role of {role} (ID {emp_id}).",
                link="/dashboard",
                priority="high",
                meta={"role": role, "employee_id": emp_id},
            )
        except Exception:
            pass
    elif payload.decision == "reject":
        await db.users.update_one({"user_id": user_id}, {"$set": {
            "approval_status": "rejected",
            "is_active": False,
            "rejected_at": iso_now(),
            "rejected_by": admin["user_id"],
            "rejection_reason": payload.reason,
        }})
        # Kill any active sessions
        await db.user_sessions.delete_many({"user_id": user_id})
    else:
        raise HTTPException(status_code=400, detail="decision must be approve|reject")

    fresh = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return _pack_user(fresh)
