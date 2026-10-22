"""Regression coverage for RBAC overrides and account lifecycle gates."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.deps as deps
from core.rbac import has_permission, user_with_perms
from routes.auth import _pack_user
from server import _user_with_perms


def test_empty_permission_override_is_fail_closed_everywhere():
    user = {"role": "Employee", "permissions": []}

    assert has_permission(user, "projects.read") is False
    assert user_with_perms(user)["permissions"] == []
    assert _pack_user(user)["permissions"] == []
    assert _user_with_perms(user)["permissions"] == []


def test_missing_tenant_is_denied(monkeypatch):
    class Organizations:
        async def find_one(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(deps, "db", SimpleNamespace(organizations=Organizations()))
    user = {
        "user_id": "user_a", "org_id": "org_missing", "role": "Employee",
        "email": "employee@test.invalid", "approval_status": "approved", "is_active": True,
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(deps.ensure_user_access(user))
    assert exc.value.status_code == 403


def test_regular_user_without_tenant_is_denied():
    user = {
        "user_id": "orphan", "role": "Employee",
        "email": "orphan@test.invalid", "approval_status": "approved",
        "is_active": True,
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(deps.ensure_user_access(user))
    assert exc.value.status_code == 403


def test_platform_admin_without_tenant_remains_valid():
    user = {
        "user_id": "platform", "role": "SuperAdmin",
        "email": "platform@test.invalid", "approval_status": "approved",
        "is_active": True, "is_super_admin": True,
    }

    asyncio.run(deps.ensure_user_access(user))


@pytest.mark.parametrize("org", [
    {"is_suspended": True, "is_active": True},
    {"is_suspended": False, "is_active": False},
])
def test_suspended_or_inactive_tenant_is_denied(monkeypatch, org):
    class Organizations:
        async def find_one(self, *_args, **_kwargs):
            return org

    monkeypatch.setattr(deps, "db", SimpleNamespace(organizations=Organizations()))
    user = {
        "user_id": "user_a", "org_id": "org_a", "role": "Employee",
        "email": "employee@test.invalid", "approval_status": "approved", "is_active": True,
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(deps.ensure_user_access(user))
    assert exc.value.status_code == 403
