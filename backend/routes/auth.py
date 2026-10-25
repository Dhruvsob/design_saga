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
* bcrypt password hashes compatible with existing stored credentials.
* Brute-force: `login_attempts` collection keyed by identifier; 5 fails / 15 min
  → 429 with lockout timer.
* Session tokens are UUID hex — same shape as Google flow — stored in
  `user_sessions` with 7-day expiry. Cookie set as httpOnly + secure + SameSite=None.
* Employee ID auto-assigned on user creation: `DS0001`, `DS0002`, …
"""
from fastapi import APIRouter, HTTPException, Request, Response, Cookie, Header
from typing import Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
import bcrypt
import hashlib
import uuid
import os

from core.db import db
from core.helpers import iso_now, now_utc, new_id
from core.audit import audit
from core.deps import ensure_user_access, require_user, get_current_user
from core.rbac import has_permission, ROLES, normalize_role, expand_permissions
from models.user import (
    RegisterIn, LoginPasswordIn, ChangePasswordIn,
    ResetPasswordIn, ApprovalDecisionIn,
)


router = APIRouter()

MAX_FAILED = 5
MAX_FAILED_PER_IP = 30
LOCKOUT_MINUTES = 15
PIN_MAX_FAILED = 5
PIN_LOCKOUT_MINUTES = 15


class AppPinIn(BaseModel):
    pin: str


class AppPinSetupIn(BaseModel):
    pin: str
    current_pin: Optional[str] = None


# ==================================================
# helpers
# ==================================================
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("ascii"))
    except (TypeError, ValueError):
        return False


def _password_matches(candidates: list[dict], password: str) -> list[dict]:
    """Verify every candidate so a shared tenant-local ID is never chosen arbitrarily."""
    return [
        candidate for candidate in candidates
        if candidate.get("password_hash")
        and verify_password(password, candidate["password_hash"])
    ]


async def _next_employee_id(org_id: str) -> str:
    """Return a concurrency-safe, tenant-local DS0001-style login ID."""
    from pymongo import ReturnDocument
    max_num = 0
    async for u in db.users.find({"org_id": org_id, "employee_id": {"$regex": "^DS\\d+$"}},
                                 {"_id": 0, "employee_id": 1}):
        try:
            n = int(u["employee_id"][2:])
            if n > max_num:
                max_num = n
        except (ValueError, KeyError):
            pass
    key = {"org_id": org_id, "kind": "user_employee_id"}
    if not await db.counters.find_one(key):
        try:
            await db.counters.insert_one({**key, "seq": max_num})
        except Exception:
            pass  # A concurrent creator won the unique counter insert.
    counter = await db.counters.find_one_and_update(
        key, {"$inc": {"seq": 1}}, return_document=ReturnDocument.AFTER)
    return f"DS{int(counter['seq']):04d}"


def _pack_user(u: dict) -> dict:
    """Public projection: strips password_hash, adds `permissions`, `org_id`."""
    out = {k: v for k, v in u.items() if k not in {"password_hash", "app_pin_hash"}}
    role = normalize_role(u.get("role"))
    out["role"] = role
    if isinstance(u.get("permissions"), list):
        out["permissions"] = list(u["permissions"])
    else:
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
    import secrets
    from core.helpers import session_digest
    token = secrets.token_hex(32)
    pin_required = bool(await db.user_app_locks.find_one(
        {"user_id": user_id, "enabled": True}, {"_id": 1}))
    session = {
        "user_id": user_id,
        "session_token": session_digest(token),
        "expires_at": now_utc() + timedelta(days=7),
        "created_at": now_utc(),
    }
    if pin_required:
        session["pin_required"] = True
    await db.user_sessions.insert_one(session)
    cookie_secure = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    response.set_cookie(
        key="session_token", value=token,
        httponly=True, secure=cookie_secure,
        samesite="lax",
        path="/", max_age=7 * 24 * 3600,
    )
    return token


def _request_ip_hash(request: Request) -> str:
    """Return an opaque source key; Caddy sanitizes X-Forwarded-For by default."""
    forwarded = request.headers.get("x-forwarded-for", "")
    address = forwarded.split(",", 1)[0].strip()
    if not address and request.client:
        address = request.client.host
    return hashlib.sha256((address or "unknown").encode("utf-8")).hexdigest()


async def _register_failed_attempt(identifier: str, ip_hash: str):
    await db.login_attempts.insert_one({
        "identifier": identifier.lower(),
        "ip_hash": ip_hash,
        "at": now_utc(),
    })


async def _check_lockout(identifier: str, ip_hash: str):
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
    source_failures = await db.login_attempts.count_documents({
        "ip_hash": ip_hash,
        "at": {"$gte": cutoff},
    })
    if source_failures >= MAX_FAILED_PER_IP:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again after {LOCKOUT_MINUTES} minutes.",
        )


async def _clear_attempts(identifier: str):
    await db.login_attempts.delete_many({"identifier": identifier.lower()})


async def _clear_lockout_for_user(user: dict):
    """Remove any brute-force lockout for a user, keyed by BOTH their email and
    employee_id (either could have been used as the login identifier). Called
    when an Admin resets a password / approves / explicitly unlocks, so the user
    can sign in immediately instead of waiting out the 15-minute window."""
    idents = []
    if user.get("email"):
        idents.append(str(user["email"]).lower())
    if user.get("employee_id"):
        idents.append(str(user["employee_id"]).lower())
    if idents:
        await db.login_attempts.delete_many({"identifier": {"$in": idents}})


def _validate_app_pin(pin: str) -> str:
    value = str(pin or "").strip()
    if len(value) != 6 or not value.isdigit():
        raise HTTPException(status_code=400, detail="App PIN must contain exactly 6 digits")
    return value


def _current_auth_session(request: Request) -> dict:
    session = getattr(request.state, "auth_session", None)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


def _utc_datetime(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _verify_app_pin(user: dict, pin: str) -> dict:
    doc = await db.user_app_locks.find_one(
        {"user_id": user["user_id"], "enabled": True}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=409, detail="App PIN is not configured")
    locked_until = _utc_datetime(doc.get("locked_until"))
    if locked_until and locked_until > now_utc():
        seconds = max(1, int((locked_until - now_utc()).total_seconds()))
        raise HTTPException(status_code=429, detail=f"Too many incorrect PIN attempts. Try again in {seconds} seconds")
    if verify_password(str(pin or ""), doc.get("pin_hash") or ""):
        await db.user_app_locks.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"failed_attempts": 0, "last_unlocked_at": now_utc()},
             "$unset": {"locked_until": ""}},
        )
        return doc

    # Increment atomically so parallel guesses cannot overwrite one another and
    # evade the attempt limit.
    await db.user_app_locks.update_one(
        {"user_id": user["user_id"], "enabled": True},
        {"$inc": {"failed_attempts": 1}, "$set": {"last_failed_at": now_utc()}},
    )
    current = await db.user_app_locks.find_one(
        {"user_id": user["user_id"], "enabled": True},
        {"_id": 0, "failed_attempts": 1},
    )
    failures = int((current or {}).get("failed_attempts") or 0)
    if failures >= PIN_MAX_FAILED:
        await db.user_app_locks.update_one(
            {"user_id": user["user_id"], "enabled": True},
            {"$set": {
                "locked_until": now_utc() + timedelta(minutes=PIN_LOCKOUT_MINUTES),
            }},
        )
        raise HTTPException(status_code=429, detail="Too many incorrect PIN attempts. Try again in 15 minutes")
    raise HTTPException(
        status_code=401,
        detail=f"Incorrect PIN. {PIN_MAX_FAILED - failures} attempt(s) remaining",
    )


def _identifier_query(identifier: str) -> dict:
    """Match every supported login identifier without assuming an ID format.

    Employee IDs are tenant-configurable (for example DS0001 or
    EMP-2026-0001), so classifying an identifier by a hard-coded prefix makes
    valid accounts unreachable. Candidate password verification below safely
    disambiguates tenant-local IDs that are reused by multiple organisations.
    """
    ident = identifier.strip()
    variants = list(dict.fromkeys((ident, ident.upper(), ident.lower())))
    return {"$or": [
        {"email": ident.lower()},
        {"employee_id": {"$in": variants}},
        {"user_id": ident},
    ]}


def _ensure_target_in_actor_tenant(actor: dict, target: dict) -> None:
    from core.tenancy import user_org_id, is_super_admin, DEFAULT_ORG_ID
    if not is_super_admin(actor) and (target.get("org_id") or DEFAULT_ORG_ID) != user_org_id(actor):
        raise HTTPException(status_code=404, detail="User not found")


def _ensure_assignable_role(actor: dict, role: str) -> None:
    if normalize_role(role) == "SuperAdmin":
        raise HTTPException(
            status_code=403,
            detail="SuperAdmin is a platform identity and cannot be assigned to a tenant user",
        )


# ==================================================
# LOGIN (password)
# ==================================================
@router.post("/auth/login-password")
async def login_password(payload: LoginPasswordIn, response: Response, request: Request):
    ident = payload.identifier.strip()
    if not ident:
        raise HTTPException(status_code=400, detail="Identifier required")

    ip_hash = _request_ip_hash(request)
    await _check_lockout(ident, ip_hash)

    # Look up by email OR employee_id.
    # IMPORTANT (multi-tenant): employee_id is per-organisation — every org's
    # first admin starts at DS0001 — so it is NOT globally unique and the same
    # id legitimately exists across tenants. Email *should* be unique but we
    # defend against duplicates too. Using find_one() here would always resolve
    # to a single fixed user, so admins of *other* tenants sharing that id would
    # be rejected with "invalid credentials" even with the correct password.
    # Fix: fetch ALL candidates for the identifier and authenticate against the
    # one whose password actually matches.
    candidates = await db.users.find(_identifier_query(ident), {"_id": 0}).to_list(50)

    matches = _password_matches(candidates, payload.password)
    if len(matches) > 1:
        await _register_failed_attempt(ident, ip_hash)
        await audit(None, "auth.login_ambiguous", target_type="auth",
                    meta={"identifier_hash": hashlib.sha256(ident.lower().encode()).hexdigest()[:16],
                          "matches": len(matches), "src": ip_hash[:12]})
        raise HTTPException(
            status_code=409,
            detail="This User ID exists in more than one workspace. Sign in with your email address.",
        )
    user = matches[0] if matches else None

    if user is None:
        await _register_failed_attempt(ident, ip_hash)
        await audit(None, "auth.login_failed", target_type="auth",
                    meta={"identifier_hash": hashlib.sha256(ident.lower().encode()).hexdigest()[:16],
                          "src": ip_hash[:12]},
                    org_id=(candidates[0].get("org_id") if len(candidates) == 1 else None))
        raise HTTPException(status_code=401, detail="Invalid credentials")

    await ensure_user_access(user)

    await _clear_attempts(ident)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_login": iso_now()}},
    )
    token = await _set_session_cookie(response, user["user_id"])
    await audit(user, "auth.login", target=user["user_id"], target_type="user",
                meta={"method": "password", "src": ip_hash[:12]})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    try:
        from core.deps import resolve_permissions
        from core.tenancy import user_org_id
        fresh["permissions"] = await resolve_permissions(fresh.get("role"), user_org_id(fresh))
    except Exception:
        pass
    packed = _pack_user(fresh)
    pin_required = bool(await db.user_app_locks.find_one(
        {"user_id": user["user_id"], "enabled": True}, {"_id": 1}))
    packed["app_pin_enabled"] = pin_required
    packed["app_pin_locked"] = pin_required
    return {"user": packed, "session_token": token}


# ==================================================
# PERSONAL APP PIN / ONE-MINUTE INACTIVITY LOCK
# ==================================================
@router.get("/auth/pin/status")
async def app_pin_status(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await ensure_user_access(user)
    from core.session_lock import PIN_TIMEOUT_SECONDS, session_pin_locked
    session = _current_auth_session(request)
    return {
        "enabled": bool(session.get("pin_required")),
        "locked": session_pin_locked(session),
        "timeout_seconds": PIN_TIMEOUT_SECONDS,
    }


@router.post("/auth/pin/setup")
async def setup_app_pin(payload: AppPinSetupIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await ensure_user_access(user)
    session = _current_auth_session(request)
    pin = _validate_app_pin(payload.pin)
    existing = await db.user_app_locks.find_one(
        {"user_id": user["user_id"], "enabled": True}, {"_id": 0})
    if existing:
        await _verify_app_pin(user, payload.current_pin or "")
    else:
        from core.session_lock import session_is_recent
        if not session_is_recent(session):
            raise HTTPException(
                status_code=401,
                detail="For security, sign out and sign in again before setting your App PIN",
            )

    now = now_utc()
    await db.user_app_locks.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "user_id": user["user_id"],
            "org_id": user.get("org_id"),
            "enabled": True,
            "pin_hash": hash_password(pin),
            "failed_attempts": 0,
            "updated_at": now,
            "updated_by": user["user_id"],
        }, "$setOnInsert": {"created_at": now},
         "$unset": {"locked_until": ""}},
        upsert=True,
    )
    await db.user_sessions.update_many(
        {"user_id": user["user_id"]},
        {"$set": {"pin_required": True}, "$unset": {"pin_unlocked_until": ""}},
    )
    from core.session_lock import PIN_TIMEOUT_SECONDS
    unlocked_until = now_utc() + timedelta(seconds=PIN_TIMEOUT_SECONDS)
    await db.user_sessions.update_one(
        {"session_token": session["session_token"]},
        {"$set": {"pin_required": True, "pin_unlocked_until": unlocked_until}},
    )
    await audit(user, "auth.app_pin.setup", target=user["user_id"], target_type="user",
                meta={"changed": bool(existing), "timeout_seconds": PIN_TIMEOUT_SECONDS})
    return {"ok": True, "enabled": True, "locked": False,
            "timeout_seconds": PIN_TIMEOUT_SECONDS}


@router.post("/auth/pin/unlock")
async def unlock_app_pin(payload: AppPinIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await ensure_user_access(user)
    session = _current_auth_session(request)
    await _verify_app_pin(user, _validate_app_pin(payload.pin))
    from core.session_lock import PIN_TIMEOUT_SECONDS
    unlocked_until = now_utc() + timedelta(seconds=PIN_TIMEOUT_SECONDS)
    await db.user_sessions.update_one(
        {"session_token": session["session_token"]},
        {"$set": {"pin_required": True, "pin_unlocked_until": unlocked_until}},
    )
    await audit(user, "auth.app_pin.unlock", target=user["user_id"], target_type="user")
    return {"ok": True, "locked": False, "timeout_seconds": PIN_TIMEOUT_SECONDS}


@router.post("/auth/pin/touch")
async def touch_app_pin(request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await ensure_user_access(user)
    session = _current_auth_session(request)
    if not session.get("pin_required"):
        return {"ok": True, "enabled": False}
    from core.session_lock import PIN_TIMEOUT_SECONDS, session_pin_locked
    if session_pin_locked(session):
        raise HTTPException(status_code=423, detail="App PIN required")
    await db.user_sessions.update_one(
        {"session_token": session["session_token"]},
        {"$set": {"pin_unlocked_until": now_utc() + timedelta(seconds=PIN_TIMEOUT_SECONDS)}},
    )
    return {"ok": True, "locked": False}


@router.post("/auth/pin/lock")
async def lock_app_pin(request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await ensure_user_access(user)
    session = _current_auth_session(request)
    if session.get("pin_required"):
        await db.user_sessions.update_one(
            {"session_token": session["session_token"]},
            {"$unset": {"pin_unlocked_until": ""}},
        )
    return {"ok": True, "locked": bool(session.get("pin_required"))}


@router.post("/auth/pin/disable")
async def disable_app_pin(payload: AppPinIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await ensure_user_access(user)
    await _verify_app_pin(user, _validate_app_pin(payload.pin))
    await db.user_app_locks.delete_one({"user_id": user["user_id"]})
    await db.user_sessions.update_many(
        {"user_id": user["user_id"]},
        {"$unset": {"pin_required": "", "pin_unlocked_until": ""}},
    )
    await audit(user, "auth.app_pin.disable", target=user["user_id"], target_type="user")
    return {"ok": True, "enabled": False, "locked": False}


# ==================================================
# CHANGE PASSWORD (self)
# ==================================================
@router.post("/auth/change-password")
async def change_password(payload: ChangePasswordIn, request: Request, response: Response,
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
    await db.user_sessions.delete_many({"user_id": user["user_id"]})
    await audit(user, "auth.password_change", target=user["user_id"], target_type="user",
                meta={"sessions_revoked": True})
    response.delete_cookie("session_token", path="/")
    return {"ok": True, "reauthenticate": True}


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
    from core.tenancy import user_org_id, is_super_admin
    _org_id = admin.get("org_id") if is_super_admin(admin) else user_org_id(admin)
    if not _org_id:
        raise HTTPException(status_code=400, detail="Select a tenant before creating a tenant user")
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
    _ensure_assignable_role(admin, role)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    employee_id = await _next_employee_id(_org_id)
    # Multi-tenant: new users inherit the admin's org
    from core.tenancy import user_org_id
    doc = {
        "user_id": user_id,
        "org_id": _org_id,
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
    await audit(admin, "user.create", target=user_id, target_type="user",
                meta={"role": role, "approval_status": doc["approval_status"]},
                org_id=_org_id)
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
    _ensure_target_in_actor_tenant(admin, target)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "password_updated_at": iso_now(),
                  "password_reset_by": admin["user_id"]}}
    )
    # Invalidate every active session of the target so they must re-login.
    await db.user_sessions.delete_many({"user_id": user_id})
    # Clear any brute-force lockout so the NEW password works immediately
    # (otherwise a previously locked user stays blocked for 15 min after reset).
    await _clear_lockout_for_user(target)
    await audit(admin, "user.password_reset", target=user_id, target_type="user",
                meta={"sessions_revoked": True}, org_id=target.get("org_id"))
    return {"ok": True, "unlocked": True}


# ==================================================
# UNLOCK (Admin clears a brute-force lockout)
# ==================================================
@router.post("/rbac/users/{user_id}/unlock")
async def unlock_user(user_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    admin = await require_user(request, session_token, authorization)
    if not has_permission(admin, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    from core.tenancy import user_org_id as _uoid, is_super_admin as _is_sa, DEFAULT_ORG_ID as _DEF
    if not _is_sa(admin) and (target.get("org_id") or _DEF) != _uoid(admin):
        raise HTTPException(status_code=404, detail="User not found")
    await _clear_lockout_for_user(target)
    await audit(admin, "user.unlock", target=user_id, target_type="user",
                org_id=target.get("org_id"))
    return {"ok": True, "unlocked": True}


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
    from core.tenancy import tenant_filter as _tfilter
    rows = await db.users.find({**_tfilter(admin), "approval_status": "pending"}, {"_id": 0}) \
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
    # Tenant isolation: non-super Admins can only approve users in their own org.
    from core.tenancy import user_org_id as _uoid, is_super_admin as _is_sa, DEFAULT_ORG_ID as _DEF
    if not _is_sa(admin) and (target.get("org_id") or _DEF) != _uoid(admin):
        raise HTTPException(status_code=404, detail="User not found")

    if payload.decision == "approve":
        role = normalize_role(payload.role or target.get("role") or "Employee")
        _ensure_assignable_role(admin, role)
        # Assign employee_id if missing
        emp_id = target.get("employee_id") or await _next_employee_id(target.get("org_id") or "org_default")
        await db.users.update_one({"user_id": user_id}, {"$set": {
            "approval_status": "approved",
            "is_active": True,
            "role": role,
            "employee_id": emp_id,
            "approved_at": iso_now(),
            "approved_by": admin["user_id"],
        }})
        # Clear any lockout so a freshly-approved user can sign in right away.
        fresh_target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if fresh_target:
            await _clear_lockout_for_user(fresh_target)
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
    await audit(admin, f"user.{payload.decision}", target=user_id, target_type="user",
                meta={"role": fresh.get("role"), "reason": payload.reason or None},
                org_id=target.get("org_id"))
    return _pack_user(fresh)
