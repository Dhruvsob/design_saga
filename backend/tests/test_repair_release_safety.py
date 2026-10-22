"""Release-blocker regression tests for the repair branch."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from starlette.requests import Request

import core.audit as audit_module
import core.helpers as helpers_module
import core.jobs as jobs_module
from core.audit import audit_digest, verify_chain
from core.http_security import rate_limit_decision, reset_rate_limits
from core.indexes import _INDEXES
from core.helpers import business_today
from server import _demo_seeding_enabled


def _request(path: str) -> Request:
    return Request({
        "type": "http", "method": "POST", "path": path,
        "headers": [], "client": ("203.0.113.10", 1234),
        "scheme": "https", "server": ("gamaa.in", 443),
    })


@pytest.mark.parametrize("path", [
    "/api/auth/reset-password/user_1",
    "/api/platform/orgs/org_1/users/user_1/reset-password",
    "/api/employees/emp_1/account/reset-password",
])
def test_every_password_reset_route_is_rate_limited(path):
    reset_rate_limits()
    for _ in range(10):
        assert rate_limit_decision(_request(path)) is None
    assert rate_limit_decision(_request(path))[0] == "password_reset"


def test_integrity_indexes_are_unique():
    required = {
        "job_lock_name_unique", "job_status_name_unique",
        "expense_request_unique", "vendor_payment_request_unique",
        "vendor_bill_number_unique", "vendor_bill_request_unique", "vendor_gstin_unique",
        "invoice_number_unique",
        "employees_org_employee_unique", "counter_org_kind_unique",
    }
    found = {opts.get("name") for _, _, opts in _INDEXES if opts.get("unique")}
    assert required <= found


def test_optional_unique_indexes_use_single_sparse_keys():
    keys_by_name = {
        opts.get("name"): keys for _, keys, opts in _INDEXES if opts.get("unique")
    }
    assert keys_by_name["expense_request_unique"] == [("request_key", 1)]
    assert keys_by_name["vendor_payment_request_unique"] == [("request_key", 1)]
    assert keys_by_name["vendor_bill_number_unique"] == [("bill_key", 1)]
    assert keys_by_name["vendor_bill_request_unique"] == [("request_key", 1)]
    assert keys_by_name["vendor_gstin_unique"] == [("gstin_key", 1)]


def test_business_date_uses_configured_timezone(monkeypatch):
    monkeypatch.setenv("BUSINESS_TIMEZONE", "Asia/Kolkata")
    monkeypatch.setattr(
        helpers_module, "now_utc",
        lambda: datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc),
    )
    assert business_today().isoformat() == "2026-10-15"


def test_demo_seeding_is_impossible_in_production(monkeypatch):
    monkeypatch.setenv("ENABLE_SEED_DEMO", "true")
    monkeypatch.setenv("ENV", "production")
    assert _demo_seeding_enabled() is False

    monkeypatch.setenv("ENV", "development")
    assert _demo_seeding_enabled() is True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        self.rows.sort(key=lambda row: row.get("seq") or 0)
        return self

    async def to_list(self, limit):
        return self.rows[:limit]


class _AuditLog:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *_args, **_kwargs):
        return _Cursor([dict(row) for row in self.rows if row.get("seq") is not None])

    async def count_documents(self, query):
        if query.get("seq") is None:
            return sum(row.get("seq") is None for row in self.rows)
        if query.get("seq") == {"$ne": None}:
            return sum(row.get("seq") is not None for row in self.rows)
        if query.get("seq") == {"$exists": False}:
            return sum("seq" not in row for row in self.rows)
        return 0


class _AuditChain:
    def __init__(self, head):
        self.head = head

    async def find_one(self, *_args, **_kwargs):
        return self.head


def _row(seq, prev_hash, action):
    row = {
        "id": f"aud_{seq}", "at": "2026-10-15T00:00:00+00:00",
        "action": action, "target": "", "target_type": "",
        "actor_id": "qa", "actor_email": "qa@test.invalid",
        "actor_role": "Admin", "org_id": "org_qa", "meta": {},
        "chain": "org_qa", "seq": seq, "prev_hash": prev_hash,
    }
    row["hash"] = audit_digest(row)
    return row


def test_audit_digest_uses_hmac_key(monkeypatch):
    monkeypatch.setenv("AUDIT_HMAC_KEY", "a" * 64)
    assert audit_digest(_row(1, "genesis", "signed"))[0:8] == "hmac256:"


def test_audit_verifier_detects_deleted_tail(monkeypatch):
    first = _row(1, "genesis", "one")
    second = _row(2, first["hash"], "two")
    fake_db = SimpleNamespace(
        audit_log=_AuditLog([first]),
        audit_chain=_AuditChain({"chain": "org_qa", "seq": 2, "head": second["hash"]}),
    )
    monkeypatch.setattr(audit_module, "db", fake_db)
    result = asyncio.run(verify_chain("org_qa"))
    assert result["ok"] is False
    assert any("head mismatch" in item["issue"] for item in result["problems"])


class _JobRows:
    def find(self, *_args, **_kwargs):
        return _Cursor([])


def test_job_health_reports_jobs_that_never_ran(monkeypatch):
    monkeypatch.setattr(jobs_module, "db", SimpleNamespace(job_status=_JobRows()))
    result = asyncio.run(jobs_module.job_health())
    assert result["ok"] is False
    assert result["unhealthy"] == sorted(jobs_module.EXPECTED_JOBS)
