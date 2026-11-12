"""A workspace Admin must never manage a platform (Super Admin) account, even
one whose user record lives in the same workspace (Design Saga hosts the
platform owner). Otherwise an Admin could reset the owner's password and take
over every tenant."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.tenancy as tenancy
import routes.auth as auth

ADMIN = {"user_id": "u_admin", "org_id": "org_default", "role": "Admin", "email": "admin@studio.test"}
OWNER = {"user_id": "u_owner", "org_id": "org_default", "role": "SuperAdmin", "email": "owner@platform.test"}
STAFF = {"user_id": "u_staff", "org_id": "org_default", "role": "Employee", "email": "staff@studio.test"}
OTHER = {"user_id": "u_other", "org_id": "org_b", "role": "Employee", "email": "x@b.test"}


@pytest.fixture(autouse=True)
def _platform_owner(monkeypatch):
    monkeypatch.setattr(tenancy, "SUPER_ADMIN_EMAILS", {"owner@platform.test"})


def test_guard_blocks_platform_accounts_and_other_tenants():
    auth._ensure_target_in_actor_tenant(ADMIN, STAFF)                     # same studio: allowed
    with pytest.raises(HTTPException) as exc:
        auth._ensure_target_in_actor_tenant(ADMIN, OWNER)
    assert exc.value.status_code == 403
    # Listed in SUPER_ADMIN_EMAILS even without the role on the record.
    with pytest.raises(HTTPException):
        auth._ensure_target_in_actor_tenant(ADMIN, {**OWNER, "role": "Admin"})
    with pytest.raises(HTTPException) as exc:
        auth._ensure_target_in_actor_tenant(ADMIN, OTHER)
    assert exc.value.status_code == 404
    auth._ensure_target_in_actor_tenant(OWNER, OTHER)                     # platform staff: allowed


def _wire(monkeypatch, target):
    async def require_user(*_a, **_k):
        return ADMIN

    async def find_one(query, _p=None):
        return dict(target) if query.get("user_id") == target["user_id"] else None

    issued = []

    async def issue(user, purpose, created_by):
        issued.append((user["user_id"], purpose, created_by))
        return "/invite/tok"

    async def audit(*_a, **_k):
        return None

    import core.invites as invites
    monkeypatch.setattr(auth, "require_user", require_user)
    monkeypatch.setattr(auth, "db", SimpleNamespace(users=SimpleNamespace(find_one=find_one)))
    monkeypatch.setattr(auth, "audit", audit)
    monkeypatch.setattr(invites, "issue_set_password_link", issue)
    return issued


def test_admin_can_issue_a_link_for_studio_staff(monkeypatch):
    issued = _wire(monkeypatch, STAFF)
    out = asyncio.run(auth.admin_reset_link("u_staff", request=None))
    assert out == {"invite_path": "/invite/tok"}
    assert issued == [("u_staff", "reset", "u_admin")]


def test_admin_cannot_issue_a_link_for_the_platform_owner(monkeypatch):
    issued = _wire(monkeypatch, OWNER)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.admin_reset_link("u_owner", request=None))
    assert exc.value.status_code == 403 and issued == []
