"""Tenant cleanup and scoped-query regression coverage."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.platform as platform


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, limit):
        return self._rows[:limit]


class _Collection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.delete_many_queries = []
        self.delete_one_queries = []

    def find(self, *_args, **_kwargs):
        return _Cursor([dict(row) for row in self.rows])

    async def delete_many(self, query):
        self.delete_many_queries.append(query)
        return SimpleNamespace(deleted_count=1)

    async def delete_one(self, query):
        self.delete_one_queries.append(query)
        return SimpleNamespace(deleted_count=1)


class _Database:
    def __init__(self):
        self.collections = {
            name: _Collection() for name in platform.TENANT_PURGE_COLLECTIONS
        }
        self.collections.update({
            "users": _Collection([
                {"user_id": "user_a", "email": "A@Example.com", "employee_id": "DS0007"},
                {"user_id": "user_b", "email": "b@example.com", "employee_id": "EMP-B"},
            ]),
            "user_sessions": _Collection(),
            "login_attempts": _Collection(),
            "audit_chain": _Collection(),
            "organizations": _Collection(),
        })

    def __getattr__(self, name):
        return self.collections[name]

    def __getitem__(self, name):
        return self.collections[name]


def _setup(monkeypatch, tmp_path, org_overrides=None):
    fake_db = _Database()
    org = {"org_id": "org_a", "name": "Tenant A", "slug": "tenant-a",
           "is_active": False, "exported_at": "2026-11-12T10:00:00+00:00", **(org_overrides or {})}

    async def allow(*_args, **_kwargs):
        return {"user_id": "superadmin"}

    async def get_org(org_id):
        return {**org, "org_id": org_id}

    async def audit(*_args, **_kwargs):
        return None

    from services import local_files
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(platform, "db", fake_db)
    monkeypatch.setattr(platform, "require_super_admin", allow)
    monkeypatch.setattr(platform, "get_org", get_org)
    monkeypatch.setattr(platform, "audit", audit)
    return fake_db


def test_tenant_purge_removes_every_registered_collection_and_login_identity(monkeypatch, tmp_path):
    fake_db = _setup(monkeypatch, tmp_path)
    upload = tmp_path / "org_a" / "plan.pdf"
    logo = tmp_path / "branding" / "designsaga-erp" / "org-logos" / "org_a" / "logo.png"
    keep = tmp_path / "org_b" / "other.pdf"
    for path in (upload, logo, keep):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    result = asyncio.run(platform.delete_org("org_a", None, purge=True, confirm="Tenant-A"))

    assert result == {"ok": True, "purged": True}
    assert not upload.exists() and not logo.exists()
    assert keep.exists()                              # another tenant's files untouched
    assert {"user_id": {"$in": ["user_a", "user_b"]}} in fake_db.user_app_locks.delete_many_queries
    assert fake_db.user_sessions.delete_many_queries == [
        {"user_id": {"$in": ["user_a", "user_b"]}},
    ]
    identifiers = fake_db.login_attempts.delete_many_queries[0]["identifier"]["$in"]
    assert identifiers == [
        "a@example.com", "b@example.com", "ds0007", "emp-b", "user_a", "user_b",
    ]
    for name in platform.TENANT_PURGE_COLLECTIONS:
        assert {"org_id": "org_a"} in fake_db[name].delete_many_queries
    assert fake_db.audit_chain.delete_one_queries == [{"chain": "org_a"}]
    assert fake_db.organizations.delete_one_queries == [{"org_id": "org_a"}]


@pytest.mark.parametrize("overrides, confirm, status, message", [
    ({"is_active": True}, "tenant-a", 409, "Deactivate"),
    ({"exported_at": None}, "tenant-a", 409, "export"),
    ({}, "wrong-name", 400, "short name"),
    ({}, None, 400, "short name"),
])
def test_purge_requires_deactivation_export_and_typed_confirmation(
        monkeypatch, tmp_path, overrides, confirm, status, message):
    fake_db = _setup(monkeypatch, tmp_path, overrides)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(platform.delete_org("org_a", None, purge=True, confirm=confirm))
    assert exc.value.status_code == status and message in exc.value.detail
    assert fake_db.organizations.delete_one_queries == []
    assert all(not fake_db[name].delete_many_queries for name in platform.TENANT_PURGE_COLLECTIONS)


def test_default_tenant_can_never_be_purged(monkeypatch):
    async def allow(*_args, **_kwargs):
        return {"user_id": "superadmin"}

    monkeypatch.setattr(platform, "require_super_admin", allow)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(platform.delete_org(platform.DEFAULT_ORG_ID, None, purge=True))
    assert exc.value.status_code == 400
