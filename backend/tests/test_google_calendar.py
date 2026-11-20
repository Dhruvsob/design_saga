import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx

import pytest

from core import google_calendar as gc
from core import access_control
from routes.calendar import _validate_event_timing
from routes.google_calendar import RETRY_MESSAGE, _status_error


def test_token_encryption_round_trip(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_ENCRYPTION_KEY", "a" * 64)
    encrypted = gc.encrypt_token("refresh-secret")
    assert encrypted != "refresh-secret"
    assert gc.decrypt_token(encrypted) == "refresh-secret"


def test_token_encryption_requires_real_secret(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_ENCRYPTION_KEY", "short")
    with pytest.raises(gc.GoogleCalendarError):
        gc.encrypt_token("refresh-secret")


def test_google_email_cannot_be_reused_by_another_erp_identity(monkeypatch):
    connections = SimpleNamespace(
        find_one=AsyncMock(return_value={"org_id": "org_b", "user_id": "user_b"}),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(gc, "db", SimpleNamespace(google_calendar_connections=connections))

    with pytest.raises(gc.GoogleCalendarError, match="Each employee must connect their own"):
        asyncio.run(gc.save_connection(
            "org_a", "user_a",
            {"refresh_token": "refresh", "access_token": "access", "expires_in": 3600},
            "shared@example.com",
        ))

    connections.update_one.assert_not_awaited()


def test_same_erp_identity_can_reconnect_its_google_account(monkeypatch):
    connections = SimpleNamespace(
        find_one=AsyncMock(return_value={"org_id": "org_a", "user_id": "user_a"}),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(gc, "db", SimpleNamespace(google_calendar_connections=connections))
    monkeypatch.setattr(gc, "encrypt_token", lambda value: f"encrypted:{value}")

    asyncio.run(gc.save_connection(
        "org_a", "user_a",
        {"refresh_token": "refresh", "access_token": "access", "expires_in": 3600},
        "person@example.com",
    ))

    connections.update_one.assert_awaited_once()


def test_sync_error_summary_never_persists_provider_url_or_token():
    request = httpx.Request("POST", "https://oauth.example/token?code=secret-code")
    response = httpx.Response(401, request=request, text='{"access_token":"secret-token"}')
    error = httpx.HTTPStatusError(
        "401 from https://oauth.example/token?code=secret-code access_token=secret-token",
        request=request, response=response,
    )
    summary = gc._safe_sync_error(error)
    assert summary == "HTTPStatusError (HTTP 401)"
    assert "secret" not in summary
    assert "oauth.example" not in summary


def test_reconnect_failure_keeps_actionable_safe_message():
    message, reconnect = gc._sync_failure(
        gc.GoogleCalendarError(gc.RECONNECT_REQUIRED_MESSAGE))
    assert reconnect is True
    assert message == gc.RECONNECT_REQUIRED_MESSAGE
    assert "token" not in message.lower()


def test_other_google_failure_stays_generic():
    message, reconnect = gc._sync_failure(gc.GoogleCalendarError("provider secret"))
    assert reconnect is False
    assert message == "GoogleCalendarError"
    assert "secret" not in message


def test_status_normalizes_old_reconnect_error_for_existing_connections():
    assert _status_error({
        "status": "reconnect_required",
        "last_error": "GoogleCalendarError",
    }) == gc.RECONNECT_REQUIRED_MESSAGE
    # Old rows hold exception class names; people see a sentence instead.
    assert _status_error({
        "status": "connected",
        "last_error": "HTTPStatusError (HTTP 503)",
    }) == RETRY_MESSAGE
    assert _status_error({
        "status": "connected",
        "last_error": gc.TEMPORARY_UNAVAILABLE_MESSAGE,
    }) == gc.TEMPORARY_UNAVAILABLE_MESSAGE
    assert _status_error({"status": "connected", "last_error": None}) is None


def test_google_event_id_is_stable_and_google_safe():
    first = gc.google_event_id("org_a", "task", "tsk_123")
    assert first == gc.google_event_id("org_a", "task", "tsk_123")
    assert first != gc.google_event_id("org_b", "task", "tsk_123")
    assert first.isalnum() and first == first.lower()


def test_personal_sync_visibility_is_owner_or_explicit_share_only():
    user = {"user_id": "user_a", "name": "A Person"}
    ids = {"user_a", "emp_a"}

    assert gc._source_visible_to_user(
        "task", {"created_by": "user_a"}, user, ids)
    assert gc._source_visible_to_user(
        "task", {"assignee_id": "emp_a"}, user, ids)
    assert not gc._source_visible_to_user(
        "task", {"created_by": "user_b", "assignee_id": "emp_b"}, user, ids)
    assert gc._source_visible_to_user(
        "calendar_event", {"visibility": "org"}, user, ids)
    assert gc._source_visible_to_user(
        "calendar_event", {"visibility": "private", "employee_ids": ["emp_a"]}, user, ids)
    assert not gc._source_visible_to_user(
        "calendar_event", {"visibility": "private", "created_by": "user_b"}, user, ids)
    assert not gc._source_visible_to_user(
        "task", {"assignee_name": "A Person"}, user, ids)
    assert gc._source_visible_to_user(
        "task", {"assignee_name": "A Person"}, user, ids,
        legacy_name_allowed=True)


def test_legacy_name_assignment_requires_one_active_user(monkeypatch):
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def limit(self, _count):
            return self

        async def to_list(self, _count):
            return self.rows

    class Users:
        def __init__(self, rows):
            self.rows = rows

        def find(self, query, projection):
            assert query["org_id"] == "org_a"
            assert query["name"] == "Same Name"
            assert projection == {"_id": 0, "user_id": 1}
            return Cursor(self.rows)

    monkeypatch.setattr(access_control.db, "users", Users([{"user_id": "user_a"}]))
    assert asyncio.run(access_control.unique_legacy_assignee_user_id(
        "org_a", "Same Name")) == "user_a"

    monkeypatch.setattr(access_control.db, "users", Users([
        {"user_id": "user_a"}, {"user_id": "user_b"},
    ]))
    assert asyncio.run(access_control.unique_legacy_assignee_user_id(
        "org_a", "Same Name")) is None


def test_calendar_sync_excludes_inactive_and_unapproved_users():
    assert gc._active_user_filter("org_a", "user_a") == {
        "org_id": "org_a",
        "user_id": "user_a",
        "is_active": {"$ne": False},
        "approval_status": {"$nin": ["pending", "rejected"]},
    }


def test_default_org_calendar_sync_includes_legacy_unstamped_users():
    query = gc._active_user_filter("org_default", "legacy_user")
    assert query["$and"][1]["user_id"] == "legacy_user"
    scope = query["$and"][0]["$or"]
    assert {"org_id": "org_default"} in scope
    assert {"org_id": {"$exists": False}} in scope
    assert {"org_id": None} in scope


def test_assignee_copy_does_not_send_duplicate_google_invites(monkeypatch):
    attendee_lookup = AsyncMock(return_value=["person@example.com"])
    monkeypatch.setattr(gc, "_attendee_emails", attendee_lookup)
    body = asyncio.run(gc.event_body("org_a", "calendar_event", {
        "id": "evt_123", "title": "Private review", "date": "2026-10-20",
        "created_by": "user_a", "attendee_ids": ["user_b"],
    }, owner_user_id="user_b"))
    assert body["attendees"] == []
    attendee_lookup.assert_not_awaited()


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


def test_batch_sync_queues_all_sources_but_processes_once(monkeypatch):
    monkeypatch.setattr(gc, "is_configured", lambda: True)
    enqueue = AsyncMock(return_value=1)
    process = AsyncMock()
    monkeypatch.setattr(gc, "_queue_source_for_connections", enqueue)
    monkeypatch.setattr(gc, "process_sync_queue", process)

    asyncio.run(gc.sync_sources("org_a", "task", ["tsk_1", "tsk_2", "tsk_3"]))

    assert enqueue.await_count == 3
    enqueue.assert_any_await("org_a", "task", "tsk_1", "upsert")
    process.assert_awaited_once_with(20)


# --- Expired authorization, provider outage and reconnect catch-up -----------

class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_refresh_rejection_separates_expiry_outage_and_server_config():
    assert gc._refresh_rejection(_Resp(400, {"error": "invalid_grant"})) == "reconnect"
    assert gc._refresh_rejection(_Resp(400)) == "reconnect"
    assert gc._refresh_rejection(_Resp(401, {"error": "invalid_client"})) == "config"
    assert gc._refresh_rejection(_Resp(400, {"error": "unauthorized_client"})) == "config"
    assert gc._refresh_rejection(_Resp(503, {"error": "backendError"})) == "temporary"
    assert gc._refresh_rejection(_Resp(500)) == "temporary"
    assert gc._refresh_rejection(_Resp(429, ["not", "a", "dict"])) == "temporary"
    assert gc._refresh_rejection(_Resp(400, ["not", "a", "dict"])) == "reconnect"


def _token_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(gc, "decrypt_token", lambda value: "refresh-secret")
    monkeypatch.setattr(gc, "encrypt_token", lambda value: f"encrypted:{value}")


def _fake_token_client(monkeypatch, response=None, error=None):
    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            if error:
                raise error
            return response

    monkeypatch.setattr(gc.httpx, "AsyncClient", Client)


CONNECTION = {"org_id": "org_a", "user_id": "user_a", "connection_id": "c1",
              "connected_email": "person@example.com",
              "refresh_token_enc": "x", "access_token_expires_at": None}


def test_google_outage_during_refresh_keeps_the_connection(monkeypatch):
    _token_env(monkeypatch)
    mark = AsyncMock()
    monkeypatch.setattr(gc, "mark_reconnect_required", mark)
    _fake_token_client(monkeypatch, response=_Resp(503, {"error": "backendError"}))
    with pytest.raises(gc.GoogleUnavailable):
        asyncio.run(gc._access_token(dict(CONNECTION)))
    _fake_token_client(monkeypatch, error=httpx.ConnectTimeout("timed out"))
    with pytest.raises(gc.GoogleUnavailable):
        asyncio.run(gc._access_token(dict(CONNECTION)))
    mark.assert_not_awaited()
    message, reconnect = gc._sync_failure(gc.GoogleUnavailable(gc.TEMPORARY_UNAVAILABLE_MESSAGE))
    assert (message, reconnect) == (gc.TEMPORARY_UNAVAILABLE_MESSAGE, False)
    assert gc._sync_failure(httpx.ReadTimeout("slow"))[0] == gc.TEMPORARY_UNAVAILABLE_MESSAGE


def test_bad_oauth_client_is_a_server_problem_not_a_reconnect(monkeypatch):
    _token_env(monkeypatch)
    mark = AsyncMock()
    monkeypatch.setattr(gc, "mark_reconnect_required", mark)
    _fake_token_client(monkeypatch, response=_Resp(401, {"error": "invalid_client"}))
    with pytest.raises(gc.SafeSyncError) as raised:
        asyncio.run(gc._access_token(dict(CONNECTION)))
    assert str(raised.value) == gc.SERVER_CONFIG_MESSAGE
    mark.assert_not_awaited()


def test_expired_grant_pauses_once_and_tells_the_person(monkeypatch):
    _token_env(monkeypatch)
    updates = []

    class Connections:
        async def update_one(self, query, update):
            updates.append((query, update))
            # first call pauses, second claims the notice, later ones no-op
            return SimpleNamespace(modified_count=1 if len(updates) <= 2 else 0)

    monkeypatch.setattr(gc, "db", SimpleNamespace(google_calendar_connections=Connections()))
    emitted = AsyncMock(return_value=1)
    import core.notifications as notifications
    monkeypatch.setattr(notifications, "emit", emitted)
    _fake_token_client(monkeypatch, response=_Resp(400, {"error": "invalid_grant"}))

    with pytest.raises(gc.GoogleCalendarError) as raised:
        asyncio.run(gc._access_token(dict(CONNECTION)))
    assert str(raised.value) == gc.RECONNECT_REQUIRED_MESSAGE
    pause_query, pause = updates[0]
    assert pause_query["status"] == {"$ne": "reconnect_required"}
    assert pause["$set"]["status"] == "reconnect_required"
    assert pause["$set"]["reconnect_required_at"]
    claim_query, _claim = updates[1]
    assert claim_query["status"] == "reconnect_required"
    assert {"reconnect_notified_at": {"$exists": False}} in claim_query["$or"]
    emitted.assert_awaited_once()
    args, kwargs = emitted.await_args
    assert args[0] == ["user_a"] and args[1] == "calendar_sync"
    assert kwargs["link"] == "/calendar"
    assert kwargs["dedup_key"] == "gcal-reconnect:c1"
    assert "refresh-secret" not in str(args) + str(kwargs)

    # A second failing worker finds the notice already claimed: no repeat.
    with pytest.raises(gc.GoogleCalendarError):
        asyncio.run(gc._access_token(dict(CONNECTION)))
    emitted.assert_awaited_once()


def test_cached_token_rejected_by_google_refreshes_once(monkeypatch):
    seen = []

    async def access_token(connection):
        seen.append(connection.get("access_token_expires_at"))
        return "token"

    responses = iter([_Resp(401), _Resp(200), _Resp(401), _Resp(401)])

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def request(self, *a, **k):
            return next(responses)

    monkeypatch.setattr(gc, "_access_token", access_token)
    monkeypatch.setattr(gc.httpx, "AsyncClient", Client)
    cached = {**CONNECTION, "access_token_expires_at": "2099-01-01T00:00:00+00:00"}
    response = asyncio.run(gc._google_request(cached, "PUT", "ds1", {"id": "ds1"}))
    assert response.status_code == 200
    assert seen == ["2099-01-01T00:00:00+00:00", None]
    # A second 401 after the refresh is returned, not retried forever.
    response = asyncio.run(gc._google_request(cached, "PUT", "ds1", {"id": "ds1"}))
    assert response.status_code == 401


def test_remote_failures_store_readable_retry_messages():
    assert isinstance(gc._remote_failure("update", 503), gc.GoogleUnavailable)
    refused = gc._remote_failure("delete", 403)
    assert str(refused) == "Google refused a calendar delete (HTTP 403). Sync will retry."
    assert gc._sync_failure(refused) == (str(refused), False)


def test_authorization_summary_spots_the_seven_day_testing_limit():
    week = gc.authorization_summary({
        "authorized_at": "2026-10-16T16:20:23+00:00",
        "reconnect_required_at": "2026-10-23T17:05:00+00:00",
    })
    assert week["authorization_days"] == 7.0
    assert week["testing_limit_likely"] is True
    early = gc.authorization_summary({
        "authorized_at": "2026-10-16T16:20:23+00:00",
        "reconnect_required_at": "2026-10-19T10:00:00+00:00",
    })
    assert early["testing_limit_likely"] is False
    legacy = gc.authorization_summary({"created_at": "2026-10-16T16:20:23+00:00"})
    assert legacy["authorized_at"].startswith("2026-10-16")
    assert legacy["paused_since"] is None and legacy["testing_limit_likely"] is False
    assert gc.authorization_summary(None)["authorized_at"] is None


def test_reconnect_removes_copies_of_items_that_changed_during_the_pause(monkeypatch):
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def limit(self, _n):
            return self

        def __aiter__(self):
            self._it = iter(self.rows)
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration

    tasks = {
        "tsk_done": {"id": "tsk_done", "status": "done", "created_by": "user_a"},
        "tsk_moved": {"id": "tsk_moved", "status": "todo", "created_by": "user_b",
                      "assignee_id": "emp_other"},
        "tsk_queued": {"id": "tsk_queued", "status": "todo", "created_by": "user_a"},
    }
    events = {"evt_past": {"id": "evt_past", "date": "2026-10-01", "created_by": "user_a"}}

    def find_id(query):
        if "id" in query:
            return query["id"]
        for part in query.get("$and", []):
            if "id" in part:
                return part["id"]
        return None

    def coll(rows):
        async def find_one(query, projection):
            return rows.get(find_id(query))
        return SimpleNamespace(find_one=find_one)

    mappings = [
        {"source_type": "task", "source_id": "tsk_deleted"},
        {"source_type": "task", "source_id": "tsk_done"},
        {"source_type": "task", "source_id": "tsk_moved"},
        {"source_type": "task", "source_id": "tsk_queued"},
        {"source_type": "calendar_event", "source_id": "evt_past"},
    ]
    monkeypatch.setattr(gc, "db", SimpleNamespace(
        tasks=coll(tasks), calendar_events=coll(events),
        google_calendar_synced_events=SimpleNamespace(find=lambda q, p: Cursor(mappings)),
    ))
    queued = []

    async def enqueue(org_id, user_id, source_type, source_id, operation="upsert"):
        queued.append((source_type, source_id, operation))

    monkeypatch.setattr(gc, "enqueue_sync", enqueue)
    count = asyncio.run(gc._enqueue_stale_copies(
        "org_a", {"user_id": "user_a", "name": "A"}, {"user_a", "emp_a"}, False,
        {("task", "tsk_queued")}))
    # Deleted, completed and reassigned items lose their Google copy; the
    # still-visible past event is left alone (no Google call at all).
    assert count == 3
    assert sorted(queued) == [
        ("task", "tsk_deleted", "delete"),
        ("task", "tsk_done", "delete"),
        ("task", "tsk_moved", "delete"),
    ]
