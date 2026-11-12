"""Super Admin support access is scoped, time-limited, read-only by default
and visible to the customer (P0.5)."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import core.deps as deps
import routes.platform as platform
from core.scoped_db import _scope, current_org_id, set_scope_from_user
from core.session_lock import enforce_support_access, support_access

SA = {"user_id": "platform", "role": "SuperAdmin", "is_super_admin": True, "email": "owner@gamaa.test"}
SOON = datetime.now(timezone.utc) + timedelta(minutes=30)


def _session(**extra):
    return {"impersonated_org_id": "org_a", "impersonation_expires_at": SOON,
            "impersonation_mode": "read", **extra}


def _request(method, path, session):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path),
                           state=SimpleNamespace(auth_session=session))


def test_super_admin_inside_a_workspace_is_scoped_to_that_tenant():
    contextual = deps.apply_session_context(SA, _session())
    set_scope_from_user(contextual)
    assert _scope.get() == {"org_id": "org_a"}
    assert current_org_id() == "org_a"            # records created there belong to the tenant
    set_scope_from_user(deps.apply_session_context(SA, {}))
    assert _scope.get() is None                  # outside a workspace: platform-wide


def test_expired_or_undated_grants_give_no_workspace_access():
    expired = _session(impersonation_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert support_access(expired) is None
    assert support_access({"impersonated_org_id": "org_a"}) is None
    assert "org_id" not in deps.apply_session_context(SA, expired)


def test_read_only_support_access_blocks_changes_but_not_viewing_or_exit():
    session = _session()
    enforce_support_access(_request("GET", "/api/projects", session))
    enforce_support_access(_request("POST", "/api/platform/exit-impersonation", session))
    with pytest.raises(HTTPException) as exc:
        enforce_support_access(_request("POST", "/api/projects", session))
    assert exc.value.status_code == 403 and "read-only" in exc.value.detail
    enforce_support_access(_request("POST", "/api/projects", _session(impersonation_mode="write")))


def test_support_access_needs_a_reason_and_a_bounded_duration():
    with pytest.raises(ValidationError):
        platform.SupportAccessIn(reason="short")
    with pytest.raises(ValidationError):
        platform.SupportAccessIn(reason="Ticket 42: invoice PDF wrong", minutes=600)
    with pytest.raises(ValidationError):
        platform.SupportAccessIn(reason="Ticket 42: invoice PDF wrong", mode="admin")
    assert platform.SupportAccessIn(reason="Ticket 42: invoice PDF wrong").mode == "read"


def test_grant_is_recorded_in_the_customer_audit_log(monkeypatch):
    audits, updates = [], []

    async def super_admin(*_a, **_k):
        return dict(SA)

    async def get_org(org_id):
        return {"org_id": org_id, "name": "Studio A"}

    async def audit(actor, action, **kwargs):
        audits.append((action, kwargs.get("org_id")))

    class _Coll:
        async def update_one(self, query, update):
            updates.append(update)

    monkeypatch.setattr(platform, "require_super_admin", super_admin)
    monkeypatch.setattr(platform, "get_org", get_org)
    monkeypatch.setattr(platform, "audit", audit)
    monkeypatch.setattr(platform, "db", SimpleNamespace(user_sessions=_Coll(), users=_Coll()))
    payload = platform.SupportAccessIn(reason="Ticket 42: invoice PDF wrong", minutes=30)
    result = asyncio.run(platform.impersonate_org("org_a", payload, None, session_token="tok"))

    assert result["mode"] == "read"
    session_set = updates[0]["$set"]
    assert session_set["impersonation_mode"] == "read" and session_set["impersonation_expires_at"] > datetime.now(timezone.utc)
    assert ("support.access_granted", "org_a") in audits
