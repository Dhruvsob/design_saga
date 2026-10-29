"""Regression coverage for secondary visibility surfaces."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes.calendar import _date_window
from routes.comments import CommentIn, _require_entity_access
from routes import comments as comments_routes
from routes import search as search_routes


class _SearchCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    async def to_list(self, limit):
        return self.rows[:limit]


class _SearchCollection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []

    def find(self, query, *_args):
        self.queries.append(query)
        return _SearchCursor(self.rows)


def test_calendar_window_is_validated_and_bounded():
    assert _date_window("2026-01-01", "2026-12-31") == ("2026-01-01", "2026-12-31")

    with pytest.raises(HTTPException) as reversed_range:
        _date_window("2026-02-01", "2026-01-01")
    assert reversed_range.value.status_code == 400

    with pytest.raises(HTTPException) as oversized_range:
        _date_window("2025-01-01", "2026-12-31")
    assert oversized_range.value.status_code == 400


def test_comment_payload_limits_are_enforced():
    with pytest.raises(ValidationError):
        CommentIn(entity_type="project", entity_id="", body="valid")
    with pytest.raises(ValidationError):
        CommentIn(entity_type="project", entity_id="project_1", body="x" * 5001)


def test_comment_entity_permission_is_required_before_lookup():
    user = {"user_id": "user_1", "role": "Client", "permissions": []}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require_entity_access(user, "vendor", "vendor_1"))
    assert exc.value.status_code == 403


def test_comment_delete_is_soft_and_audited(monkeypatch):
    class Comments:
        def __init__(self):
            self.row = {
                "id": "comment_1", "entity_type": "project", "entity_id": "project_1",
                "author_id": "user_1", "body": "Keep history",
            }

        async def find_one(self, *_args, **_kwargs):
            return dict(self.row)

        async def update_one(self, query, update):
            assert query["deleted"] == {"$ne": True}
            self.row.update(update["$set"])
            return SimpleNamespace(matched_count=1)

    comments = Comments()

    async def user(*_args, **_kwargs):
        return {"user_id": "user_1", "org_id": "org_a", "permissions": []}

    async def allow(*_args, **_kwargs):
        return None

    audited = []

    async def record_audit(*args, **kwargs):
        audited.append((args, kwargs))

    monkeypatch.setattr(comments_routes, "sdb", SimpleNamespace(comments=comments))
    monkeypatch.setattr(comments_routes, "require_user", user)
    monkeypatch.setattr(comments_routes, "_require_entity_access", allow)
    monkeypatch.setattr(comments_routes, "audit", record_audit)

    result = asyncio.run(comments_routes.delete_comment("comment_1", None))

    assert result == {"ok": True}
    assert comments.row["deleted"] is True
    assert comments.row["deleted_by"] == "user_1"
    assert audited and audited[0][0][1] == "comment.delete"


def test_global_search_includes_advanced_quotes_and_only_visible_events(monkeypatch):
    async def require_user(*_args, **_kwargs):
        return {"user_id": "user_1", "permissions": ["quotations.read", "calendar.read"]}

    async def no_visibility(_user):
        return {}

    async def private_event_visibility(_user):
        return {"created_by": "user_1"}

    quote = _SearchCollection([{
        "id": "quo_1", "project_title": "Alpha House", "number": "Q-101",
        "client_name": "Alpha Client", "status": "draft",
    }])
    event = _SearchCollection([{
        "id": "evt_1", "title": "Alpha review", "date": "2026-10-24",
        "start_time": "10:00", "location": "Site",
    }])
    empty = _SearchCollection()
    fake_sdb = type("SearchDB", (), {
        "projects": empty, "clients": empty, "leads": empty, "tasks": empty,
        "vendors_acc": empty, "invoices": empty, "quotations_adv": quote,
        "calendar_events": event, "employees": empty, "purchase_orders": empty,
        "journal_entries": empty,
    })()
    monkeypatch.setattr(search_routes, "require_user", require_user)
    monkeypatch.setattr(search_routes, "project_visibility_query", no_visibility)
    monkeypatch.setattr(search_routes, "task_visibility_query", no_visibility)
    monkeypatch.setattr(search_routes, "event_visibility_query", private_event_visibility)
    monkeypatch.setattr(search_routes, "sdb", fake_sdb)

    result = asyncio.run(search_routes.global_search(None, q="Alpha", limit=5))

    assert {(row["type"], row["id"]) for row in result["results"]} == {
        ("quotation", "quo_1"), ("calendar_event", "evt_1")}
    assert event.queries[0]["$and"][0]["$and"][1] == {"created_by": "user_1"}
