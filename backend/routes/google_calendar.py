"""OAuth and management endpoints for the tenant Google Calendar connection."""
from datetime import timedelta
import logging
import os
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from typing import Optional

from core.audit import audit
from core.db import db
from core.deps import require_user
from core.google_calendar import (
    connection_for, enqueue_org_sources, exchange_code,
    google_email, is_configured, new_oauth_state, oauth_url, process_sync_queue,
    save_connection, state_hash,
)
from core.helpers import iso_now, now_utc
from core.rbac import has_permission
from core.tenancy import is_super_admin, user_org_id

router = APIRouter()
log = logging.getLogger("google_calendar_routes")


def _frontend_url(**params) -> str:
    base = os.environ.get("APP_BASE_URL", "https://gamaa.in").rstrip("/")
    return f"{base}/calendar?{urlencode(params)}"


def _require_org_manager(user: dict) -> str:
    if is_super_admin(user) and not user.get("org_id"):
        raise HTTPException(400, "Switch into an organisation first")
    if not has_permission(user, "calendar.manage"):
        raise HTTPException(403, "Missing permission: calendar.manage")
    return user_org_id(user)


@router.get("/calendar/google/status")
async def google_calendar_status(request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    org_id = user_org_id(user)
    connection = await connection_for(org_id) if org_id else None
    pending = await db.google_calendar_sync_queue.count_documents(
        {"org_id": org_id, "status": "pending"}) if org_id else 0
    return {
        "configured": is_configured(),
        "connected": bool(connection and connection.get("status") == "connected"),
        "status": (connection or {}).get("status", "disconnected"),
        "email": (connection or {}).get("connected_email"),
        "last_sync_at": (connection or {}).get("last_sync_at"),
        "last_error": (connection or {}).get("last_error"),
        "pending": pending,
        "can_manage": bool(has_permission(user, "calendar.manage")),
    }


@router.post("/calendar/google/connect")
async def connect_google_calendar(request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    org_id = _require_org_manager(user)
    if not is_configured():
        raise HTTPException(503, "Google Calendar OAuth is not configured on the server")
    state, verifier, challenge = new_oauth_state()
    await db.google_oauth_states.insert_one({
        "state_hash": state_hash(state),
        "org_id": org_id,
        "user_id": user["user_id"],
        "verifier": verifier,
        "created_at": iso_now(),
        "expires_at": now_utc() + timedelta(minutes=10),
    })
    return {"authorization_url": oauth_url(state, challenge)}


@router.get("/calendar/google/callback")
async def google_calendar_callback(code: Optional[str] = None, state: Optional[str] = None,
                                   error: Optional[str] = None):
    if error or not code or not state:
        return RedirectResponse(_frontend_url(google="error"), status_code=303)
    oauth_state = await db.google_oauth_states.find_one_and_delete({
        "state_hash": state_hash(state),
        "expires_at": {"$gt": now_utc()},
    })
    if not oauth_state:
        return RedirectResponse(_frontend_url(google="invalid_state"), status_code=303)
    try:
        token = await exchange_code(code, oauth_state["verifier"])
        email = await google_email(token["access_token"])
        await save_connection(oauth_state["org_id"], oauth_state["user_id"], token, email)
        await enqueue_org_sources(oauth_state["org_id"])
        await process_sync_queue(100)
        await audit(
            {"user_id": oauth_state["user_id"], "org_id": oauth_state["org_id"]},
            "google_calendar.connect", target=oauth_state["org_id"],
            target_type="google_calendar", meta={"email": email},
        )
        return RedirectResponse(_frontend_url(google="connected"), status_code=303)
    except Exception as exc:  # noqa: BLE001 - OAuth errors return a safe UI status
        log.warning("Google Calendar OAuth callback failed: %s", type(exc).__name__)
        return RedirectResponse(_frontend_url(google="error"), status_code=303)


@router.post("/calendar/google/sync")
async def sync_google_calendar(request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    org_id = _require_org_manager(user)
    connection = await connection_for(org_id)
    if not connection or connection.get("status") != "connected":
        raise HTTPException(409, "Connect Google Calendar first")
    queued = await enqueue_org_sources(org_id)
    result = await process_sync_queue(200)
    await audit(user, "google_calendar.sync", target=org_id,
                target_type="google_calendar", meta={"queued": queued, **result})
    return {"queued": queued, **result}


@router.delete("/calendar/google/connection")
async def disconnect_google_calendar(request: Request,
                                     session_token: Optional[str] = Cookie(default=None),
                                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    org_id = _require_org_manager(user)
    await db.google_calendar_connections.delete_one({"org_id": org_id})
    await db.google_calendar_sync_queue.delete_many({"org_id": org_id})
    await audit(user, "google_calendar.disconnect", target=org_id,
                target_type="google_calendar")
    return {"ok": True}
