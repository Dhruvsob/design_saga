"""Read-only mode after a trial/subscription ends (DS-093)."""
import asyncio
from datetime import date

import pytest
from fastapi import HTTPException

from core import subscription as sub

TODAY = date(2026, 11, 6)


@pytest.mark.parametrize("org,read_only,status", [
    ({}, False, None),                                                       # never configured
    ({"subscription": {"status": "active"}}, False, "active"),
    ({"subscription": {"status": "trial", "trial_ends_on": "2026-11-20"}}, False, "trial"),
    ({"subscription": {"status": "trial", "trial_ends_on": "2026-11-06"}}, False, "trial"),  # last day
    ({"subscription": {"status": "trial", "trial_ends_on": "2026-10-29"}}, True, "expired"),
    ({"subscription": {"status": "expired"}}, True, "expired"),
    ({"subscription": {"status": "bogus"}}, False, None),
])
def test_state(org, read_only, status):
    s = sub.subscription_state(org, today=TODAY)
    assert s["read_only"] is read_only and s["status"] == status
    assert (s["message"] is not None) is read_only


def test_trial_days_left():
    s = sub.subscription_state({"subscription": {"status": "trial", "trial_ends_on": "2026-11-20"}}, today=TODAY)
    assert s["days_left"] == 14


class _Req:
    def __init__(self, method, path):
        self.method = method

        class U:
            pass
        self.url = U()
        self.url.path = path


def _run(monkeypatch, org, method, path, user=None):
    import core.tenancy as tenancy

    async def get_org(_):
        return org
    monkeypatch.setattr(tenancy, "get_org", get_org)
    monkeypatch.setattr(tenancy, "is_super_admin", lambda u: bool(u.get("sa")))
    return asyncio.run(sub.enforce_writable(_Req(method, path), user or {"org_id": "org_a"}))


EXPIRED = {"subscription": {"status": "expired"}}


def test_expired_tenant_cannot_change_anything(monkeypatch):
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        with pytest.raises(HTTPException) as exc:
            _run(monkeypatch, EXPIRED, method, "/api/projects")
        assert exc.value.status_code == 403 and "Read-only" in exc.value.detail


def test_expired_tenant_can_still_view_and_sign_in(monkeypatch):
    _run(monkeypatch, EXPIRED, "GET", "/api/projects")
    _run(monkeypatch, EXPIRED, "POST", "/api/auth/logout")
    _run(monkeypatch, EXPIRED, "POST", "/api/auth/pin/unlock")
    _run(monkeypatch, EXPIRED, "POST", "/api/notifications/read-all")


def test_super_admin_and_unconfigured_tenants_are_never_blocked(monkeypatch):
    _run(monkeypatch, EXPIRED, "POST", "/api/projects", user={"org_id": "org_a", "sa": True})
    _run(monkeypatch, {}, "POST", "/api/projects")
    _run(monkeypatch, {"subscription": {"status": "active"}}, "DELETE", "/api/projects/p1")
