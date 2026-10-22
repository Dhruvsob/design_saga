"""Notification privacy and idempotency regression tests."""
import asyncio
from types import SimpleNamespace

from core import notifications as notifications_module


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


async def _zero():
    return 0
