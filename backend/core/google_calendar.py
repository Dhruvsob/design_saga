"""Tenant Google Calendar OAuth, event rendering, and retry-safe sync."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from email_validator import EmailNotValidError, validate_email

from .db import db
from .access_control import unique_legacy_assignee_user_id
from .helpers import business_today, iso_now, now_utc

log = logging.getLogger("google_calendar")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
SCOPES = f"openid email {CALENDAR_SCOPE}"
IST = timezone(timedelta(hours=5, minutes=30))


class GoogleCalendarError(RuntimeError):
    pass


def is_configured() -> bool:
    return all(os.environ.get(name) for name in (
        "GOOGLE_CALENDAR_CLIENT_ID",
        "GOOGLE_CALENDAR_CLIENT_SECRET",
        "GOOGLE_CALENDAR_ENCRYPTION_KEY",
        "GOOGLE_CALENDAR_REDIRECT_URI",
    ))


def _fernet() -> Fernet:
    secret = os.environ.get("GOOGLE_CALENDAR_ENCRYPTION_KEY", "")
    if len(secret) < 32:
        raise GoogleCalendarError("Google Calendar token encryption is not configured")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_token(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        raise GoogleCalendarError("Stored Google Calendar credential cannot be decrypted") from exc


def oauth_url(state: str, code_challenge: str) -> str:
    if not is_configured():
        raise GoogleCalendarError("Google Calendar is not configured")
    return AUTH_URL + "?" + urlencode({
        "client_id": os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
        "redirect_uri": os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })


def new_oauth_state() -> tuple[str, str, str]:
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    return state, verifier, challenge


def state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


async def exchange_code(code: str, verifier: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(TOKEN_URL, data={
            "code": code,
            "client_id": os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
            "redirect_uri": os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        })
    if response.status_code != 200:
        raise GoogleCalendarError("Google rejected the authorization code")
    token = response.json()
    if not token.get("refresh_token"):
        raise GoogleCalendarError("Google did not return offline access; reconnect and approve access")
    return token


async def google_email(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code != 200 or not response.json().get("email"):
        raise GoogleCalendarError("Could not read the connected Google account")
    return response.json()["email"].strip().lower()


async def save_connection(org_id: str, user_id: str, token: dict, email: str) -> None:
    existing = await db.google_calendar_connections.find_one(
        {"org_id": org_id, "connected_email": email, "user_id": {"$ne": user_id}},
        {"_id": 0, "user_id": 1},
    )
    if existing:
        raise GoogleCalendarError(
            "This Google account is already connected to another ERP user in this organisation")
    now = now_utc()
    expires_at = now + timedelta(seconds=max(60, int(token.get("expires_in") or 3600) - 60))
    await db.google_calendar_connections.update_one(
        {"org_id": org_id, "user_id": user_id},
        {"$set": {
            "org_id": org_id,
            "user_id": user_id,
            "connected_by": user_id,
            "connected_email": email,
            "calendar_id": "primary",
            "connection_id": secrets.token_hex(12),
            "refresh_token_enc": encrypt_token(token["refresh_token"]),
            "access_token_enc": encrypt_token(token["access_token"]),
            "access_token_expires_at": expires_at,
            "status": "connected",
            "last_error": None,
            "updated_at": iso_now(),
        }, "$setOnInsert": {"created_at": iso_now()}},
        upsert=True,
    )


async def connection_for(org_id: str, user_id: str) -> dict | None:
    return await db.google_calendar_connections.find_one(
        {"org_id": org_id, "user_id": user_id}, {"_id": 0})


async def _access_token(connection: dict) -> str:
    expires_at = connection.get("access_token_expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at > now_utc() + timedelta(seconds=30):
        return decrypt_token(connection["access_token_enc"])

    refresh_token = decrypt_token(connection["refresh_token_enc"])
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(TOKEN_URL, data={
            "client_id": os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
    if response.status_code != 200:
        await db.google_calendar_connections.update_one(
            {"org_id": connection["org_id"], "user_id": connection["user_id"]},
            {"$set": {"status": "reconnect_required", "last_error": "Google authorization expired"}},
        )
        raise GoogleCalendarError("Google Calendar must be reconnected")
    token = response.json()
    expires_at = now_utc() + timedelta(seconds=max(60, int(token.get("expires_in") or 3600) - 60))
    await db.google_calendar_connections.update_one(
        {"org_id": connection["org_id"], "user_id": connection["user_id"]},
        {"$set": {
            "access_token_enc": encrypt_token(token["access_token"]),
            "access_token_expires_at": expires_at,
            "status": "connected",
            "last_error": None,
            "updated_at": iso_now(),
        }},
    )
    return token["access_token"]


def google_event_id(org_id: str, source_type: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{org_id}:{source_type}:{source_id}".encode("utf-8")).hexdigest()
    return f"ds{digest[:40]}"


def _clean_email(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return None


async def _attendee_emails(org_id: str, doc: dict, source_type: str) -> list[str]:
    candidate_ids = set()
    if source_type == "calendar_event":
        candidate_ids.update(doc.get("attendee_ids") or [])
        candidate_ids.update(doc.get("employee_ids") or [])
    else:
        candidate_ids.update(doc.get("assignees") or [])
        if doc.get("assignee_id"):
            candidate_ids.add(doc["assignee_id"])

    emails = set()
    if candidate_ids:
        async for user in db.users.find(
            {"org_id": org_id, "user_id": {"$in": list(candidate_ids)}}, {"_id": 0, "email": 1}
        ):
            email = _clean_email(user.get("email"))
            if email:
                emails.add(email)
        async for employee in db.employees.find(
            {"org_id": org_id, "id": {"$in": list(candidate_ids)}}, {"_id": 0, "email": 1}
        ):
            email = _clean_email(employee.get("email"))
            if email:
                emails.add(email)
    if source_type == "task" and not emails and doc.get("assignee_name"):
        legacy_uid = await unique_legacy_assignee_user_id(org_id, doc["assignee_name"])
        user = await db.users.find_one(
            {"org_id": org_id, "user_id": legacy_uid}, {"_id": 0, "email": 1}) if legacy_uid else None
        email = _clean_email((user or {}).get("email"))
        if email:
            emails.add(email)
    return sorted(emails)


def _date_time_fields(day: str, start_time: str | None, end_day: str | None = None,
                      end_time: str | None = None) -> tuple[dict, dict]:
    start_date = date.fromisoformat(day[:10])
    if not start_time:
        final_day = date.fromisoformat((end_day or day)[:10]) + timedelta(days=1)
        return {"date": start_date.isoformat()}, {"date": final_day.isoformat()}
    start_clock = time.fromisoformat(start_time[:5])
    start = datetime.combine(start_date, start_clock, tzinfo=IST)
    if end_time:
        finish = datetime.combine(date.fromisoformat((end_day or day)[:10]),
                                  time.fromisoformat(end_time[:5]), tzinfo=IST)
        if finish <= start:
            finish = start + timedelta(hours=1)
    else:
        finish = start + timedelta(hours=1)
    return {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"}, {
        "dateTime": finish.isoformat(), "timeZone": "Asia/Kolkata"}


async def event_body(org_id: str, source_type: str, doc: dict,
                     owner_user_id: str | None = None) -> dict | None:
    if source_type == "task":
        day = (doc.get("reminder_date") or doc.get("due_date") or "")[:10]
        if not day or doc.get("status") == "done":
            return None
        start_time = doc.get("reminder_time")
        summary = f"Task: {doc.get('title') or 'Untitled task'}"
        description = "\n\n".join(filter(None, [
            doc.get("description"),
            f"Project: {doc.get('project_name')}" if doc.get("project_name") else None,
            f"Open in Design Saga: {os.environ.get('APP_BASE_URL', 'https://gamaa.in')}/tasks/{doc['id']}",
        ]))
        reminder = 15 if start_time else 1440
        location = None
    else:
        day = (doc.get("date") or "")[:10]
        if not day:
            return None
        start_time = doc.get("start_time")
        summary = doc.get("title") or "Design Saga event"
        description = "\n\n".join(filter(None, [
            doc.get("notes"),
            f"Open in Design Saga: {os.environ.get('APP_BASE_URL', 'https://gamaa.in')}/calendar",
        ]))
        reminder = doc.get("reminder_minutes")
        location = doc.get("location")

    start, end = _date_time_fields(day, start_time, doc.get("end_date"), doc.get("end_time"))
    # Only the creator's copy sends invitations. Copies synced to assignees or
    # invited employees must not generate duplicate Google invitations.
    attendee_emails = []
    if owner_user_id is None or doc.get("created_by") == owner_user_id:
        attendee_emails = await _attendee_emails(org_id, doc, source_type)
    attendees = [{"email": email} for email in attendee_emails]
    body = {
        "id": google_event_id(org_id, source_type, doc["id"]),
        "summary": summary[:1024],
        "description": description[:8192],
        "start": start,
        "end": end,
        "attendees": attendees,
        "guestsCanInviteOthers": False,
        "guestsCanModify": False,
        "extendedProperties": {"private": {
            "designSagaOrgId": org_id,
            "designSagaSource": source_type,
            "designSagaId": doc["id"],
        }},
    }
    if location:
        body["location"] = location[:1024]
    if reminder is None:
        body["reminders"] = {"useDefault": False, "overrides": []}
    else:
        minutes = max(0, min(40320, int(reminder)))
        body["reminders"] = {"useDefault": False, "overrides": [
            {"method": "popup", "minutes": minutes},
            {"method": "email", "minutes": minutes},
        ]}
    return body


async def enqueue_sync(org_id: str, user_id: str, source_type: str, source_id: str,
                       operation: str = "upsert") -> None:
    key = f"{org_id}:{user_id}:{source_type}:{source_id}"
    await db.google_calendar_sync_queue.update_one(
        {"sync_key": key},
        {"$set": {
            "sync_key": key,
            "org_id": org_id,
            "user_id": user_id,
            "source_type": source_type,
            "source_id": source_id,
            "operation": operation,
            "status": "pending",
            "attempts": 0,
            "next_attempt_at": now_utc(),
            "updated_at": iso_now(),
        }, "$setOnInsert": {"created_at": iso_now()}},
        upsert=True,
    )


async def _user_identity_ids(org_id: str, user: dict) -> set[str]:
    ids = {user["user_id"]}
    terms = [{"user_id": user["user_id"]}]
    if user.get("email"):
        terms.append({"email": user["email"]})
    async for employee in db.employees.find(
        {"org_id": org_id, "$or": terms}, {"_id": 0, "id": 1}
    ):
        if employee.get("id"):
            ids.add(employee["id"])
    return ids


def _source_visible_to_user(source_type: str, doc: dict, user: dict,
                            identity_ids: set[str], legacy_name_allowed: bool = False) -> bool:
    """Personal Google sync: own, explicitly assigned, or explicitly shared."""
    uid = user["user_id"]
    if doc.get("created_by") == uid:
        return True
    if source_type == "calendar_event":
        if doc.get("visibility") == "org":
            return True
        return bool(
            identity_ids.intersection(doc.get("attendee_ids") or [])
            or identity_ids.intersection(doc.get("employee_ids") or [])
        )
    return bool(
        doc.get("assignee_id") in identity_ids
        or identity_ids.intersection(doc.get("assignees") or [])
        or (legacy_name_allowed and user.get("name") and doc.get("assignee_name") == user["name"])
    )


def _active_user_filter(org_id: str, user_id: str) -> dict:
    return {
        "org_id": org_id,
        "user_id": user_id,
        "is_active": {"$ne": False},
        "approval_status": {"$nin": ["pending", "rejected"]},
    }


async def _queue_source_for_connections(org_id: str, source_type: str, source_id: str,
                                        operation: str = "upsert") -> int:
    collections = {"calendar_event": db.calendar_events, "task": db.tasks}
    doc = None if operation == "delete" else await collections[source_type].find_one(
        {"org_id": org_id, "id": source_id}, {"_id": 0})
    queued = 0
    async for connection in db.google_calendar_connections.find(
        {"org_id": org_id, "status": "connected"}, {"_id": 0, "user_id": 1}
    ):
        user_id = connection.get("user_id")
        if not user_id:
            continue
        mapping = await db.google_calendar_synced_events.find_one({
            "org_id": org_id, "user_id": user_id,
            "source_type": source_type, "source_id": source_id,
        }, {"_id": 0, "event_id": 1})
        visible = False
        if doc:
            user = await db.users.find_one(
                _active_user_filter(org_id, user_id), {"_id": 0})
            if user:
                legacy_allowed = (
                    source_type == "task"
                    and await unique_legacy_assignee_user_id(org_id, user.get("name")) == user_id
                )
                visible = _source_visible_to_user(
                    source_type, doc, user, await _user_identity_ids(org_id, user),
                    legacy_name_allowed=legacy_allowed)
        if visible:
            await enqueue_sync(org_id, user_id, source_type, source_id, "upsert")
            queued += 1
        elif mapping:
            await enqueue_sync(org_id, user_id, source_type, source_id, "delete")
            queued += 1
    return queued


async def sync_source(org_id: str, source_type: str, source_id: str,
                      operation: str = "upsert") -> None:
    """Queue visible personal copies without making ERP writes depend on Google."""
    if not is_configured():
        return
    if await _queue_source_for_connections(org_id, source_type, source_id, operation):
        await process_sync_queue(20)


async def sync_sources(org_id: str, source_type: str, source_ids: list[str],
                       operation: str = "upsert") -> None:
    """Queue a batch and make only one bounded immediate sync attempt."""
    if not source_ids or not is_configured():
        return
    for source_id in source_ids[:200]:
        await _queue_source_for_connections(org_id, source_type, source_id, operation)
    await process_sync_queue(20)


async def _google_request(connection: dict, method: str, event_id: str,
                          body: dict | None = None) -> httpx.Response:
    token = await _access_token(connection)
    calendar_id = quote(connection.get("calendar_id") or "primary", safe="")
    event_path = quote(event_id, safe="")
    url = f"{CALENDAR_API}/calendars/{calendar_id}/events"
    if method != "POST":
        url += f"/{event_path}"
    async with httpx.AsyncClient(timeout=20) as client:
        params = {"quotaUser": hashlib.sha256(
            f'{connection["org_id"]}:{connection["user_id"]}'.encode("utf-8")).hexdigest()[:40]}
        if method in ("POST", "PUT", "DELETE"):
            params["sendUpdates"] = "all"
        return await client.request(
            method, url, json=body,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _upsert_remote(connection: dict, body: dict) -> None:
    response = await _google_request(connection, "POST", body["id"], body)
    if response.status_code == 409:
        response = await _google_request(connection, "PUT", body["id"], body)
    if response.status_code not in (200, 201):
        raise GoogleCalendarError(f"Google event sync failed ({response.status_code})")


async def _delete_remote(connection: dict, event_id: str) -> None:
    response = await _google_request(connection, "DELETE", event_id)
    if response.status_code not in (200, 204, 404, 410):
        raise GoogleCalendarError(f"Google event delete failed ({response.status_code})")


async def process_sync_queue(limit: int = 50, org_id: str | None = None,
                             user_id: str | None = None) -> dict:
    now = now_utc()
    query = {"status": "pending", "next_attempt_at": {"$lte": now}}
    if org_id:
        query["org_id"] = org_id
    if user_id:
        query["user_id"] = user_id
    rows = await db.google_calendar_sync_queue.find(
        query, {"_id": 0}
    ).sort("next_attempt_at", 1).to_list(max(1, min(limit, 200)))
    result = {"processed": 0, "synced": 0, "failed": 0, "skipped": 0}
    collections = {"calendar_event": db.calendar_events, "task": db.tasks}
    for row in rows:
        result["processed"] += 1
        user_id = row.get("user_id")
        connection = await connection_for(row["org_id"], user_id) if user_id else None
        if not connection or connection.get("status") != "connected":
            await db.google_calendar_sync_queue.delete_one({"sync_key": row["sync_key"]})
            result["skipped"] += 1
            continue
        try:
            event_id = google_event_id(row["org_id"], row["source_type"], row["source_id"])
            coll = collections[row["source_type"]]
            doc = await coll.find_one(
                {"org_id": row["org_id"], "id": row["source_id"]}, {"_id": 0})
            mapping_filter = {
                "org_id": row["org_id"], "user_id": user_id,
                "source_type": row["source_type"], "source_id": row["source_id"],
            }
            mapping = await db.google_calendar_synced_events.find_one(
                mapping_filter, {"_id": 0})
            user = await db.users.find_one(
                _active_user_filter(row["org_id"], user_id), {"_id": 0})
            legacy_allowed = bool(
                user
                and row["source_type"] == "task"
                and await unique_legacy_assignee_user_id(
                    row["org_id"], user.get("name")) == user_id
            )
            visible = bool(doc and user and _source_visible_to_user(
                row["source_type"], doc, user,
                await _user_identity_ids(row["org_id"], user),
                legacy_name_allowed=legacy_allowed))
            if row["operation"] == "delete" or not visible:
                if mapping:
                    await _delete_remote(connection, mapping.get("event_id") or event_id)
                    await db.google_calendar_synced_events.delete_one(mapping_filter)
            else:
                body = await event_body(
                    row["org_id"], row["source_type"], doc, owner_user_id=user_id)
                if body is None:
                    if mapping:
                        await _delete_remote(connection, mapping.get("event_id") or event_id)
                        await db.google_calendar_synced_events.delete_one(mapping_filter)
                else:
                    sync_hash = hashlib.sha256(json.dumps(
                        body, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")).hexdigest()
                    unchanged = (
                        mapping
                        and mapping.get("sync_hash") == sync_hash
                        and mapping.get("connection_id") == connection.get("connection_id")
                        and mapping.get("event_id") == event_id
                    )
                    if not unchanged:
                        await _upsert_remote(connection, body)
                    await db.google_calendar_synced_events.update_one(
                        mapping_filter,
                        {"$set": {**mapping_filter, "event_id": event_id,
                                  "connection_id": connection.get("connection_id"),
                                  "sync_hash": sync_hash, "synced_at": iso_now()}},
                        upsert=True,
                    )
            await db.google_calendar_sync_queue.delete_one({"sync_key": row["sync_key"]})
            await db.google_calendar_connections.update_one(
                {"org_id": row["org_id"], "user_id": user_id},
                {"$set": {"last_sync_at": iso_now(), "last_error": None}},
            )
            result["synced"] += 1
        except Exception as exc:  # noqa: BLE001 - queue retains sanitized failure
            attempts = int(row.get("attempts") or 0) + 1
            message = str(exc)[:240]
            delay = min(3600, 30 * (2 ** min(attempts, 7)))
            await db.google_calendar_sync_queue.update_one(
                {"sync_key": row["sync_key"]},
                {"$set": {"attempts": attempts, "last_error": message,
                          "next_attempt_at": now_utc() + timedelta(seconds=delay),
                          "updated_at": iso_now()}},
            )
            await db.google_calendar_connections.update_one(
                {"org_id": row["org_id"], "user_id": user_id},
                {"$set": {"last_error": message}})
            result["failed"] += 1
            log.warning("Google Calendar sync failed for %s: %s", row["sync_key"], message)
    return result


async def enqueue_user_sources(org_id: str, user_id: str) -> int:
    user = await db.users.find_one(
        _active_user_filter(org_id, user_id), {"_id": 0})
    if not user:
        return 0
    identity_ids = await _user_identity_ids(org_id, user)
    legacy_allowed = (
        await unique_legacy_assignee_user_id(org_id, user.get("name")) == user_id
    )
    today = business_today().isoformat()
    count = 0
    async for event in db.calendar_events.find(
        {"org_id": org_id, "date": {"$gte": today}}, {"_id": 0}
    ).limit(1000):
        if _source_visible_to_user("calendar_event", event, user, identity_ids):
            await enqueue_sync(org_id, user_id, "calendar_event", event["id"])
            count += 1
    async for task in db.tasks.find(
        {"org_id": org_id, "status": {"$ne": "done"},
         "$or": [{"reminder_date": {"$gte": today}}, {"due_date": {"$gte": today}}]},
        {"_id": 0},
    ).limit(2000):
        if _source_visible_to_user(
                "task", task, user, identity_ids,
                legacy_name_allowed=legacy_allowed):
            await enqueue_sync(org_id, user_id, "task", task["id"])
            count += 1
    return count
