"""What the ERP loads right after the App PIN unlock must stay cheap (10/11/2026).

Prod runs on FerretDB, where every database round trip is expensive, so the
post-unlock dashboard must not loop a query per row, must not download whole
lists to count them, and the PIN check must not freeze other requests.
"""
import asyncio
import time
from types import SimpleNamespace

from starlette.requests import Request

import routes.auth as auth
import server
from routes import vendors


def _request(path):
    return Request({
        "type": "http", "method": "GET", "path": path, "headers": [],
        "client": ("203.0.113.10", 1234), "scheme": "https", "server": ("gamaa.in", 443),
    })


def _matches(row, query):
    for key, expected in query.items():
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
        elif actual != expected:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a):
        return self

    async def to_list(self, _limit):
        return [dict(r) for r in self.rows]

    def __aiter__(self):
        async def iterate():
            for r in self.rows:
                yield dict(r)
        return iterate()


class _Collection:
    def __init__(self, rows=()):
        self.rows = [dict(r) for r in rows]
        self.find_calls = 0

    def find(self, query, *_a, **_k):
        self.find_calls += 1
        return _Cursor([r for r in self.rows if _matches(r, query)])

    async def find_one(self, query, *_a, **_k):
        return next((dict(r) for r in self.rows if _matches(r, query)), None)


def test_vendor_list_totals_outstanding_bills_in_one_query(monkeypatch):
    bills = _Collection([
        {"vendor_id": "v1", "status": "received", "outstanding": 1500},
        {"vendor_id": "v1", "status": "partially_paid", "outstanding": 0, "total": 900, "paid_amount": 400},
        {"vendor_id": "v1", "status": "paid", "outstanding": 7000},          # settled: excluded
        {"vendor_id": "v2", "status": "overdue", "outstanding": 250.25},
    ])
    fake = SimpleNamespace(
        vendors_acc=_Collection([{"id": f"v{i}", "name": f"Vendor {i}"} for i in range(1, 51)]),
        vendor_bills=bills,
    )

    async def user(*_a, **_k):
        return {"user_id": "admin", "org_id": "org_a", "role": "Admin", "permissions": ["*.*"]}

    monkeypatch.setattr(vendors, "sdb", fake)
    monkeypatch.setattr(vendors, "require_user", user)
    monkeypatch.setattr(vendors, "_require", lambda *_a: None)
    monkeypatch.setattr(vendors, "_can_read_vendor_financials", lambda _u: True)
    monkeypatch.setattr(vendors, "_vendor_for_user", lambda v, _u: v)

    rows = asyncio.run(vendors.list_vendors(_request("/api/vendors")))

    by_id = {r["id"]: r["outstanding"] for r in rows}
    assert by_id["v1"] == 2000          # 1500 + (900 - 400) when outstanding is 0
    assert by_id["v2"] == 250.25
    assert by_id["v3"] == 0
    assert bills.find_calls == 1        # not one query per vendor (50 here)


def test_setup_checklist_checks_existence_and_skips_switched_off_modules(monkeypatch):
    fake = SimpleNamespace(
        employees=_Collection([{"id": "e1"}]),
        clients=_Collection([{"id": "c1", "archived": True}]),    # only an archived client
        projects=_Collection([{"id": "p1"}]),
        vendors_acc=_Collection([{"id": "v1"}]),
    )

    async def user(*_a, **_k):
        return {"user_id": "admin", "org_id": "org_a", "role": "Admin", "permissions": ["*.*"]}

    import core.entitlements as entitlements

    async def ent(_org_id):
        return entitlements.effective({"org_id": "org_a", "features": {"modules": {"vendors": False}}},
                                      entitlements.DEFAULT_PLANS)

    async def visibility(_u):
        return {}

    monkeypatch.setattr(server, "sdb", fake)
    monkeypatch.setattr(server, "require_user", user)
    monkeypatch.setattr(server, "project_visibility_query", visibility)
    monkeypatch.setattr(entitlements, "for_org_id", ent)

    status = asyncio.run(server.dashboard_setup_status(_request("/api/dashboard/setup-status")))

    assert status == {"employees": True, "clients": False, "projects": True, "vendors": None}


def test_pin_check_does_not_freeze_other_requests(monkeypatch):
    class Locks:
        async def find_one(self, *_a, **_k):
            return {"user_id": "user_a", "enabled": True, "pin_hash": "stored"}

        async def update_one(self, *_a, **_k):
            return None

    def slow_bcrypt(_pin, _hashed):
        time.sleep(0.4)                 # stands in for bcrypt's CPU time
        return True

    monkeypatch.setattr(auth, "db", SimpleNamespace(user_app_locks=Locks()))
    monkeypatch.setattr(auth, "verify_password", slow_bcrypt)

    async def scenario():
        started = time.perf_counter()
        served_after = None

        async def other_request():
            nonlocal served_after
            await asyncio.sleep(0.01)
            served_after = time.perf_counter() - started

        await asyncio.gather(auth._verify_app_pin({"user_id": "user_a"}, "482615"), other_request())
        return served_after

    # Served during the 0.4 s check, not after it (on the event loop it was >= 0.4 s).
    assert asyncio.run(scenario()) < 0.2
