"""FastAPI dependencies for authentication + permission checks."""
from typing import Optional
from datetime import datetime, timezone
from fastapi import HTTPException, Request, Cookie, Header

from .db import db
from .helpers import now_utc
from .rbac import has_permission


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        return None

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        return None

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < now_utc():
        return None

    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    return user


async def require_user(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
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
