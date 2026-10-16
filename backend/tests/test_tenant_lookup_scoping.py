"""Regression coverage for tenant-scoped helper lookups and public assets."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.attendance as attendance
import routes.organization as organization
import routes.tasks as tasks


class _Cursor:
    def __init__(self, rows):
        self._rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._rows)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Collection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.find_queries = []
        self.find_one_queries = []

    def find(self, query, *_args, **_kwargs):
        self.find_queries.append(query)
        return _Cursor([dict(row) for row in self.rows])

    async def find_one(self, query, *_args, **_kwargs):
        self.find_one_queries.append(query)
        return dict(self.rows[0]) if self.rows else None


def test_task_assignee_user_lookup_is_limited_to_callers_tenant(monkeypatch):
    users = _Collection([{"user_id": "user_a"}])
    employees = _Collection([])
    monkeypatch.setattr(tasks, "db", SimpleNamespace(users=users))
    monkeypatch.setattr(tasks, "sdb", SimpleNamespace(employees=employees))

    result = asyncio.run(tasks._assignee_user_ids(
        {"org_id": "org_a"}, "user_a", [], None,
    ))

    assert result == ["user_a"]
    assert users.find_queries == [{
        "user_id": {"$in": ["user_a"]}, "org_id": "org_a",
    }]


def test_attendance_name_fallback_uses_scoped_users_collection(monkeypatch):
    employees = _Collection([])
    users = _Collection([{"user_id": "user_a", "name": "User A"}])

    class _UnscopedUsers:
        def find(self, *_args, **_kwargs):
            raise AssertionError("attendance lookup bypassed the scoped database")

    monkeypatch.setattr(
        attendance, "sdb", SimpleNamespace(employees=employees, users=users),
    )
    monkeypatch.setattr(attendance, "db", SimpleNamespace(users=_UnscopedUsers()))

    result = asyncio.run(attendance._employee_name_map(["user_a"]))

    assert result == {"user_a": "User A"}
    assert users.find_queries == [{"user_id": {"$in": ["user_a"]}}]


def test_logo_for_missing_or_inactive_org_is_not_fetched(monkeypatch):
    organizations = _Collection([])
    monkeypatch.setattr(
        organization, "db", SimpleNamespace(organizations=organizations),
    )

    def unexpected_fetch(_path):
        raise AssertionError("orphaned organization logo was fetched")

    monkeypatch.setattr(organization._storage, "get_object", unexpected_fetch)
    path = (
        "designsaga-erp/org-logos/org_a/"
        "00000000000000000000000000000000.png"
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(organization.download_logo(path))

    assert exc.value.status_code == 404
    assert organizations.find_one_queries == [{
        "org_id": "org_a", "is_active": {"$ne": False},
    }]
