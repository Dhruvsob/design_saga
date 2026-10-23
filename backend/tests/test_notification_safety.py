"""Notification privacy and idempotency regression tests."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import notifications as notifications_module
from routes import notifications as notification_routes


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self._iterator = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Users:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, *_args):
        self.queries.append(query)
        rows = [row for row in self.rows if row.get("is_active") is not False]
        return _Cursor(rows)


class _Notifications:
    def __init__(self):
        self.rows = {}

    async def update_one(self, query, update, upsert=False):
        key = query["dedup_id"]
        if key in self.rows:
            return SimpleNamespace(upserted_id=None)
        self.rows[key] = update["$setOnInsert"]
        return SimpleNamespace(upserted_id=key)


class _Preferences:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, *_args):
        self.queries.append(query)
        return _Cursor(self.rows)


def test_emit_dedup_is_atomic_and_excludes_inactive_users(monkeypatch):
    users = _Users([
        {"user_id": "active", "org_id": "org_a", "is_active": True},
        {"user_id": "inactive", "org_id": "org_a", "is_active": False},
    ])
    notifications = _Notifications()
    monkeypatch.setattr(
        notifications_module, "db",
        SimpleNamespace(users=users, notifications=notifications),
    )

    first = asyncio.run(notifications_module.emit(
        ["active", "inactive"], "info", "Status", dedup_key="daily:1"))
    second = asyncio.run(notifications_module.emit(
        ["active", "inactive"], "info", "Status", dedup_key="daily:1"))

    assert first == 1
    assert second == 0
    assert list(notifications.rows) == ["active:daily:1"]
    assert users.queries[0]["is_active"] == {"$ne": False}


def test_emit_hr_uses_current_tenant_scope(monkeypatch):
    from core import scoped_db

    users = _Users([])
    monkeypatch.setattr(
        notifications_module, "db", SimpleNamespace(users=users))
    monkeypatch.setattr(scoped_db, "current_org_id", lambda: "org_a")
    monkeypatch.setattr(notifications_module, "emit", lambda *_args, **_kwargs: _zero())

    asyncio.run(notifications_module.emit_hr("info", "Status"))

    assert users.queries[0]["org_id"] == "org_a"


def test_emit_honours_tenant_scoped_user_preferences(monkeypatch):
    users = _Users([
        {"user_id": "quiet", "org_id": "org_a", "is_active": True},
        {"user_id": "enabled", "org_id": "org_a", "is_active": True},
    ])
    preferences = _Preferences([
        {"user_id": "quiet", "org_id": "org_a", "tasks": False},
    ])
    notifications = _Notifications()
    monkeypatch.setattr(
        notifications_module, "db",
        SimpleNamespace(users=users, notification_preferences=preferences,
                        notifications=notifications),
    )
    from core import scoped_db
    monkeypatch.setattr(scoped_db, "current_org_id", lambda: "org_a")

    inserted = asyncio.run(notifications_module.emit(
        ["quiet", "enabled"], "task_due", "Task due", dedup_key="task:1"))

    assert inserted == 1
    assert list(notifications.rows) == ["enabled:task:1"]
    assert preferences.queries[0]["$or"] == [
        {"user_id": "quiet", "org_id": "org_a"},
        {"user_id": "enabled", "org_id": "org_a"},
    ]


def test_mandatory_account_notices_ignore_optional_preferences(monkeypatch):
    users = _Users([{"user_id": "quiet", "org_id": "org_a", "is_active": True}])
    notifications = _Notifications()
    monkeypatch.setattr(
        notifications_module, "db",
        SimpleNamespace(users=users, notifications=notifications),
    )
    from core import scoped_db
    monkeypatch.setattr(scoped_db, "current_org_id", lambda: "org_a")

    inserted = asyncio.run(notifications_module.emit(
        ["quiet"], "account_rejected", "Account update", dedup_key="account:1"))

    assert inserted == 1


async def _zero():
    return 0


def test_manual_tenant_scan_requires_finance_or_admin_permission():
    notification_routes._require_scan_permission({"permissions": ["finance.read"]})
    notification_routes._require_scan_permission({"permissions": ["*.*"]})
    with pytest.raises(HTTPException) as exc:
        notification_routes._require_scan_permission({"permissions": ["tasks.read"]})
    assert exc.value.status_code == 403
