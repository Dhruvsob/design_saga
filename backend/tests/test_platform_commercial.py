"""Platform (GAMAA) figures come from commercial metadata, never from a
customer's own accounting (P0.2 of docs/GAMAA_SAAS_PRODUCT_GAP_ANALYSIS.md)."""
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

from starlette.requests import Request

import routes.platform as platform

TENANT_FINANCIAL = {"journal_entries", "invoices", "collection_receivables", "collection_receipts",
                    "vendor_bills", "vendor_payments", "payroll_runs", "accounts", "expenses", "loans"}


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        async def it():
            for r in self.rows:
                yield dict(r)
        return it()


class _Coll:
    def __init__(self, rows=()):
        self.rows = list(rows)

    async def count_documents(self, query):
        return len(self.rows)

    def find(self, *_a, **_k):
        return _Cursor(self.rows)


class _GuardedDb:
    def __init__(self, orgs):
        self._colls = {"organizations": _Coll(orgs), "users": _Coll([{}, {}]),
                       "projects": _Coll([{}]), "tasks": _Coll([]),
                       "contact_requests": _Coll([{}])}

    def __getattr__(self, name):
        assert name not in TENANT_FINANCIAL, f"platform analytics read tenant financial data: {name}"
        return self._colls.setdefault(name, _Coll())

    def __getitem__(self, name):
        return getattr(self, name)


def _request():
    return Request({"type": "http", "method": "GET", "path": "/api/platform/analytics", "headers": [],
                    "client": ("203.0.113.10", 1), "scheme": "https", "server": ("gamaa.in", 443)})


def test_platform_analytics_uses_commercial_metadata_only(monkeypatch):
    today = date(2026, 11, 12)
    orgs = [
        {"org_id": "a", "name": "Studio A", "plan": "pro", "is_active": True,
         "billing": {"renewal_date": (today + timedelta(days=5)).isoformat()}},
        {"org_id": "b", "name": "Studio B", "plan": "starter", "is_active": True,
         "subscription": {"status": "trial", "trial_ends_on": (today + timedelta(days=3)).isoformat()}},
        {"org_id": "c", "name": "Closed", "plan": "pro", "is_active": False},
    ]

    async def super_admin(*_a, **_k):
        return {"user_id": "sa", "role": "SuperAdmin"}

    monkeypatch.setattr(platform, "db", _GuardedDb(orgs))
    monkeypatch.setattr(platform, "require_super_admin", super_admin)
    monkeypatch.setattr(platform, "business_today", lambda: today)

    data = asyncio.run(platform.platform_analytics(_request()))

    assert "revenue_total" not in data and "leaderboard" not in data
    assert data["plans"] == {"pro": 1, "starter": 1}           # inactive workspace excluded
    assert [r["name"] for r in data["renewals_due"]] == ["Studio A"]
    assert [r["name"] for r in data["trials_ending"]] == ["Studio B"]
    assert data["trials_ending"][0]["days_left"] == 3
