"""Server-enforced per-session PIN lock helpers."""
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .helpers import now_utc


PIN_TIMEOUT_SECONDS = 60


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


async def enforce_session_pin(request: Request) -> None:
    session = getattr(request.state, "auth_session", None)
    if session and session.get("pin_setup_required"):
        raise HTTPException(status_code=428, detail="Set your personal App PIN to continue")
    if session_pin_locked(session):
        raise HTTPException(status_code=423, detail="App PIN required")
