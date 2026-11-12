"""One-time set-password links, so platform staff never choose or know a
customer's password. Only a SHA-256 of the token is stored; links expire after
72 hours and are single use. The API returns a path (`/invite/<token>`); the
browser that shows it builds the full link from its own origin."""
import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from .db import db
from .helpers import now_utc

INVITE_HOURS = 72


def _hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


async def issue_set_password_link(user: dict, purpose: str, created_by: Optional[str]) -> str:
    """Create a new link for `user` (replacing any unused one) and return its path."""
    token = secrets.token_urlsafe(32)
    await db.user_invites.delete_many({"user_id": user["user_id"], "used_at": None})
    await db.user_invites.insert_one({
        "token_hash": _hash(token),
        "user_id": user["user_id"],
        "org_id": user.get("org_id"),
        "purpose": purpose,                      # invite | reset
        "created_by": created_by,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(hours=INVITE_HOURS),
        "used_at": None,
    })
    return f"/invite/{token}"


async def find_valid_invite(token: str) -> Optional[dict]:
    if not token or len(token) > 200:
        return None
    return await db.user_invites.find_one(
        {"token_hash": _hash(token), "used_at": None, "expires_at": {"$gt": now_utc()}},
        {"_id": 0})


async def mark_used(invite: dict) -> bool:
    """Claim the link atomically; False if another request already used it."""
    result = await db.user_invites.update_one(
        {"token_hash": invite["token_hash"], "used_at": None},
        {"$set": {"used_at": now_utc()}})
    return bool(getattr(result, "modified_count", 0))
