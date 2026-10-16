import asyncio
from unittest.mock import AsyncMock

import pytest

from core import google_calendar as gc
from routes.calendar import _validate_event_timing


def test_token_encryption_round_trip(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_ENCRYPTION_KEY", "a" * 64)
    encrypted = gc.encrypt_token("refresh-secret")
    assert encrypted != "refresh-secret"
    assert gc.decrypt_token(encrypted) == "refresh-secret"


def test_token_encryption_requires_real_secret(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_ENCRYPTION_KEY", "short")
    with pytest.raises(gc.GoogleCalendarError):
        gc.encrypt_token("refresh-secret")


def test_google_event_id_is_stable_and_google_safe():
    first = gc.google_event_id("org_a", "task", "tsk_123")
    assert first == gc.google_event_id("org_a", "task", "tsk_123")
    assert first != gc.google_event_id("org_b", "task", "tsk_123")
    assert first.isalnum() and first == first.lower()


def test_oauth_url_uses_pkce_and_offline_access(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_CALENDAR_ENCRYPTION_KEY", "b" * 64)
    monkeypatch.setenv("GOOGLE_CALENDAR_REDIRECT_URI", "https://example.test/callback")
    url = gc.oauth_url("csrf-state", "pkce-challenge")
    assert "access_type=offline" in url
    assert "code_challenge=pkce-challenge" in url
    assert "state=csrf-state" in url
    assert "calendar.events" in url


def test_calendar_timing_validation_rejects_bad_ranges():
    with pytest.raises(Exception):
        _validate_event_timing("2026-10-20", "2026-10-19", "10:00", "11:00")
    with pytest.raises(Exception):
        _validate_event_timing("2026-10-20", None, None, "11:00")
    _validate_event_timing("2026-10-20", None, "10:00", "11:00")


def test_manual_event_renders_attendees_and_reminders(monkeypatch):
    monkeypatch.setattr(gc, "_attendee_emails", AsyncMock(return_value=["person@example.com"]))
    body = asyncio.run(gc.event_body("org_a", "calendar_event", {
        "id": "evt_123",
        "title": "Site review",
        "date": "2026-10-20",
        "start_time": "10:30",
        "end_time": "11:15",
        "reminder_minutes": 15,
        "employee_ids": ["emp_1"],
        "location": "Site A",
    }))
    assert body["start"]["dateTime"] == "2026-10-20T10:30:00+05:30"
    assert body["end"]["dateTime"] == "2026-10-20T11:15:00+05:30"
    assert body["attendees"] == [{"email": "person@example.com"}]
    assert {r["method"] for r in body["reminders"]["overrides"]} == {"popup", "email"}


def test_completed_task_is_removed_from_google(monkeypatch):
    monkeypatch.setattr(gc, "_attendee_emails", AsyncMock(return_value=[]))
    body = asyncio.run(gc.event_body("org_a", "task", {
        "id": "tsk_123", "title": "Done", "status": "done", "due_date": "2026-10-20",
    }))
    assert body is None


def test_all_day_event_uses_exclusive_end_date(monkeypatch):
    monkeypatch.setattr(gc, "_attendee_emails", AsyncMock(return_value=[]))
    body = asyncio.run(gc.event_body("org_a", "calendar_event", {
        "id": "evt_123", "title": "Two days", "date": "2026-10-20", "end_date": "2026-10-21",
    }))
    assert body["start"] == {"date": "2026-10-20"}
    assert body["end"] == {"date": "2026-10-22"}
    assert body["reminders"] == {"useDefault": False, "overrides": []}


def test_all_day_task_gets_a_one_day_google_reminder(monkeypatch):
    monkeypatch.setattr(gc, "_attendee_emails", AsyncMock(return_value=[]))
    body = asyncio.run(gc.event_body("org_a", "task", {
        "id": "tsk_123", "title": "Submit drawing", "status": "todo",
        "due_date": "2026-10-20",
    }))
    assert {item["minutes"] for item in body["reminders"]["overrides"]} == {1440}


def test_remote_upsert_updates_deterministic_duplicate(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

    async def fake_request(connection, method, event_id, body=None):
        calls.append(method)
        return Response(409 if method == "POST" else 200)

    monkeypatch.setattr(gc, "_google_request", fake_request)
    asyncio.run(gc._upsert_remote({"org_id": "org_a"}, {"id": "ds123"}))
    assert calls == ["POST", "PUT"]


def test_remote_delete_treats_missing_event_as_success(monkeypatch):
    class Response:
        status_code = 404

    monkeypatch.setattr(gc, "_google_request", AsyncMock(return_value=Response()))
    asyncio.run(gc._delete_remote({"org_id": "org_a"}, "ds123"))
