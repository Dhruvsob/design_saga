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


def session_is_recent(session: dict, max_age_seconds: int = 600, at=None) -> bool:
    created_at = _as_utc((session or {}).get("created_at"))
    if not created_at:
        return False
    age = ((at or now_utc()) - created_at).total_seconds()
    return 0 <= age <= max_age_seconds


async def enforce_session_pin(request: Request) -> None:
    session = getattr(request.state, "auth_session", None)
    if session_pin_locked(session):
        raise HTTPException(status_code=423, detail="App PIN required")
