"""Regression coverage for tenant account-management and login boundaries."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from core.scoped_db import _is_super_admin_local, _merge
from core.tenancy import is_super_admin
from models.user import LoginPasswordIn
import routes.auth as auth_routes
from routes.auth import (
    _check_lockout, _ensure_assignable_role, _ensure_target_in_actor_tenant,
    _password_matches, _register_failed_attempt, _request_ip_hash,
)


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


def test_scoped_query_cannot_override_tenant_org_id():
    query = {"org_id": "org_b", "id": "record_1"}
    assert _merge({"org_id": "org_a"}, query) == {
        "org_id": "org_a", "id": "record_1",
    }
    assert query["org_id"] == "org_b"


def test_default_tenant_scope_is_anded_with_conflicting_org_query():
    scope = {"$or": [{"org_id": "org_default"},
                     {"org_id": {"$exists": False}}, {"org_id": None}]}
    merged = _merge(scope, {"org_id": "org_other", "id": "record_1"})
    assert merged["org_id"] == "org_other"
    assert merged["$or"] == scope["$or"]


def _request(forwarded_for: str) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login-password",
        "headers": [(b"x-forwarded-for", forwarded_for.encode())],
        "client": ("172.20.0.4", 12345),
    })


def test_login_source_key_is_stable_opaque_and_uses_original_client():
    first = _request_ip_hash(_request("203.0.113.9, 172.20.0.2"))
    second = _request_ip_hash(_request("203.0.113.9"))
    assert first == second
    assert "203.0.113.9" not in first
    assert len(first) == 64


def test_login_payload_rejects_oversized_inputs():
    with pytest.raises(ValidationError):
        LoginPasswordIn(identifier="a" * 255, password="valid")
    with pytest.raises(ValidationError):
        LoginPasswordIn(identifier="valid", password="a" * 129)


def test_shared_employee_id_never_selects_an_arbitrary_password_match(monkeypatch):
    monkeypatch.setattr(
        auth_routes, "verify_password", lambda password, stored: password == stored)
    candidates = [
        {"user_id": "user_a", "org_id": "org_a", "password_hash": "same"},
        {"user_id": "user_b", "org_id": "org_b", "password_hash": "same"},
    ]
    matches = _password_matches(candidates, "same")
    assert [row["user_id"] for row in matches] == ["user_a", "user_b"]


def test_failed_login_records_opaque_source(monkeypatch):
    class Attempts:
        row = None

        async def insert_one(self, row):
            self.row = row

    attempts = Attempts()
    monkeypatch.setattr(auth_routes, "db", SimpleNamespace(login_attempts=attempts))
    asyncio.run(_register_failed_attempt("USER@Example.com", "opaque-hash"))
    assert attempts.row["identifier"] == "user@example.com"
    assert attempts.row["ip_hash"] == "opaque-hash"


def test_login_source_limit_blocks_identifier_spraying(monkeypatch):
    class Attempts:
        async def count_documents(self, query):
            return auth_routes.MAX_FAILED_PER_IP if "ip_hash" in query else 0

    monkeypatch.setattr(auth_routes, "db", SimpleNamespace(login_attempts=Attempts()))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_check_lockout("new-victim@example.com", "source-hash"))
    assert exc.value.status_code == 429
