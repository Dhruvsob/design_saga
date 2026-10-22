"""Regression coverage for RBAC overrides and account lifecycle gates."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.deps as deps
from core.rbac import has_permission, user_with_perms
from routes.auth import _ensure_assignable_role, _pack_user
from server import _employee_account_filter, _org_backfill_filter, _user_with_perms


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


def test_platform_admin_session_context_remains_global_without_impersonation():
    user = {
        "user_id": "platform", "role": "SuperAdmin",
        "email": "platform@test.invalid", "is_super_admin": True,
    }
    assert "org_id" not in deps.apply_session_context(user, {})

    query = _org_backfill_filter("users", {"platform@test.invalid"})
    assert query["$and"][1] == {
        "email": {"$nin": ["platform@test.invalid"]},
    }


def test_superadmin_impersonation_is_session_scoped_and_does_not_mutate_user():
    persisted = {
        "user_id": "platform", "role": "SuperAdmin", "is_super_admin": True,
        "org_id": "legacy_global_leak", "impersonating": True,
    }
    contextual = deps.apply_session_context(
        persisted, {"impersonated_org_id": "org_a"})

    assert contextual["org_id"] == "org_a"
    assert contextual["impersonating"] is True
    assert persisted["org_id"] == "legacy_global_leak"
    clean_session = deps.apply_session_context(persisted, {})
    assert "org_id" not in clean_session
    assert "impersonating" not in clean_session


def test_employee_auth_link_is_bound_to_employee_tenant():
    employee = {"user_id": "user_linked", "org_id": "org_a"}
    actor = {"user_id": "admin", "org_id": "org_b", "role": "Admin"}
    assert _employee_account_filter(employee, actor) == {
        "user_id": "user_linked", "org_id": "org_a",
    }


def test_superadmin_cannot_be_assigned_as_a_tenant_role():
    with pytest.raises(HTTPException) as exc:
        _ensure_assignable_role(
            {"user_id": "platform", "is_super_admin": True}, "SuperAdmin")
    assert exc.value.status_code == 403


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
