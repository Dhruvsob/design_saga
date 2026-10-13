"""Regression coverage for tenant account-management boundaries."""
import pytest
from fastapi import HTTPException

from core.scoped_db import _is_super_admin_local
from core.tenancy import is_super_admin
from routes.auth import _ensure_assignable_role, _ensure_target_in_actor_tenant


TENANT_ADMIN = {
    "user_id": "admin_a", "org_id": "org_a", "email": "admin-a@test.invalid",
    "role": "Admin",
}


def test_tenant_admin_cannot_manage_another_tenants_user():
    with pytest.raises(HTTPException) as exc:
        _ensure_target_in_actor_tenant(TENANT_ADMIN, {"user_id": "user_b", "org_id": "org_b"})
    assert exc.value.status_code == 404


def test_tenant_admin_can_manage_own_tenant_user():
    _ensure_target_in_actor_tenant(TENANT_ADMIN, {"user_id": "user_a", "org_id": "org_a"})


def test_tenant_admin_cannot_assign_superadmin():
    with pytest.raises(HTTPException) as exc:
        _ensure_assignable_role(TENANT_ADMIN, "SuperAdmin")
    assert exc.value.status_code == 403


def test_role_string_alone_never_bypasses_tenant_scope():
    forged = {"user_id": "forged", "org_id": "org_a", "role": "SuperAdmin",
              "email": "forged@test.invalid"}
    assert is_super_admin(forged) is False
    assert _is_super_admin_local(forged) is False
