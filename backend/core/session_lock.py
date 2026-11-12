"""Server-enforced per-session PIN lock helpers."""
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .helpers import now_utc


PIN_TIMEOUT_SECONDS = 5 * 60


def _as_utc(value):
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


def session_pin_locked(session: dict, at=None) -> bool:
    if not session or not session.get("pin_required"):
        return False
    unlocked_until = _as_utc(session.get("pin_unlocked_until"))
    return not unlocked_until or unlocked_until <= (at or now_utc())


async def ensure_session_pin_policy(session: dict, user_id: str) -> dict:
    """Retrofit mandatory personal-PIN policy onto old and new sessions.

    Existing sessions predate the mandatory policy, so relying only on login
    would leave them usable until expiry. This one-time upgrade closes that
    gap without assigning a shared or predictable PIN to any account.
    """
    if session.get("pin_required"):
        return session

    from .db import db
    configured = bool(await db.user_app_locks.find_one(
        {"user_id": user_id, "enabled": True}, {"_id": 1},
    ))
    update = {"$set": {"pin_required": True}, "$unset": {"pin_unlocked_until": ""}}
    if configured:
        update["$unset"]["pin_setup_required"] = ""
    else:
        update["$set"]["pin_setup_required"] = True
    await db.user_sessions.update_one(
        {"session_token": session["session_token"]}, update,
    )
    session["pin_required"] = True
    session.pop("pin_unlocked_until", None)
    if configured:
        session.pop("pin_setup_required", None)
    else:
        session["pin_setup_required"] = True
    return session


def session_is_recent(session: dict, max_age_seconds: int = 600, at=None) -> bool:
    created_at = _as_utc((session or {}).get("created_at"))
    if not created_at:
        return False
    age = ((at or now_utc()) - created_at).total_seconds()
    return 0 <= age <= max_age_seconds


def support_access(session: dict, at=None) -> dict | None:
    """The live Super Admin support grant on this session, or None once it expired.
    Grants without an expiry (from before time limits) count as expired."""
    org_id = (session or {}).get("impersonated_org_id")
    expires = _as_utc((session or {}).get("impersonation_expires_at"))
    if not org_id or not expires or expires <= (at or now_utc()):
        return None
    return {"org_id": org_id, "mode": session.get("impersonation_mode") or "read",
            "expires_at": expires.isoformat(), "reason": session.get("impersonation_reason")}


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SUPPORT_EXEMPT = ("/api/platform/", "/api/auth/")


def enforce_support_access(request: Request) -> None:
    """Read-only support access may look but not change a customer's records."""
    grant = support_access(getattr(request.state, "auth_session", None))
    if not grant or grant["mode"] == "write":
        return
    if request.method.upper() in _SAFE_METHODS or request.url.path.startswith(_SUPPORT_EXEMPT):
        return
    raise HTTPException(status_code=403,
                        detail="Support access is read-only. Start write access with a reason to change records.")


async def enforce_session_pin(request: Request) -> None:
    session = getattr(request.state, "auth_session", None)
    if session and session.get("pin_setup_required"):
        raise HTTPException(status_code=428, detail="Set your personal App PIN to continue")
    if session_pin_locked(session):
        raise HTTPException(status_code=423, detail="App PIN required")
