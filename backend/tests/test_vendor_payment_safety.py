"""Regression coverage for vendor-payment reversal integrity."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from routes import accounting, vendors


class _Cursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield dict(row)
        return iterate()


def _matches(row, query):
    for key, expected in query.items():
        actual = row.get(key)
        if isinstance(expected, dict) and "$ne" in expected:
            if actual == expected["$ne"]:
                return False
        elif isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


class _Collection:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    async def find_one(self, query, *_args, **_kwargs):
        return next((dict(row) for row in self.rows if _matches(row, query)), None)

    def find(self, query, *_args, **_kwargs):
        return _Cursor(row for row in self.rows if _matches(row, query))

    async def update_one(self, query, update):
        for row in self.rows:
            if _matches(row, query):
                row.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


def _request():
    return Request({
        "type": "http", "method": "GET", "path": "/api/vendors/vendor_1/ledger",
        "headers": [], "client": ("203.0.113.10", 1234),
        "scheme": "https", "server": ("gamaa.in", 443),
    })


def test_reversal_retry_reuses_existing_journal_and_preserves_payment(monkeypatch):
    payment = {
        "id": "pmt_1", "vendor_id": "vendor_1", "vendor_name": "Vendor",
        "journal_entry_id": "je_original", "bill_ids": ["bill_1"],
        "amount": 500, "status": "posted",
    }
    original = {
        "id": "je_original", "lines": [], "vendor_id": "vendor_1",
    }
    reversal = {
        "id": "je_reversal",
        "idempotency_key": "org_a:vendor_payment_reversal:pmt_1",
    }
    fake = SimpleNamespace(
        vendor_payments=_Collection([payment]),
        journal_entries=_Collection([original, reversal]),
    )
    monkeypatch.setattr(vendors, "sdb", fake)

    refreshed = []

    async def refresh(bill_id):
        refreshed.append(bill_id)

    async def unexpected_post(*_args, **_kwargs):
        raise AssertionError("Retry posted a duplicate reversal journal")

    monkeypatch.setattr(vendors, "_refresh_bill_status", refresh)
    monkeypatch.setattr(accounting, "_post_journal", unexpected_post)
    user = {"user_id": "admin", "name": "Admin", "org_id": "org_a"}

    first = asyncio.run(vendors._reverse_vendor_payment_locked(user, "pmt_1"))
    second = asyncio.run(vendors._reverse_vendor_payment_locked(user, "pmt_1"))

    stored_payment = fake.vendor_payments.rows[0]
    stored_original = fake.journal_entries.rows[0]
    assert first == {"ok": True, "reversed": True, "reversal_je_id": "je_reversal"}
    assert second == {"ok": True, "already_reversed": True,
                      "reversal_je_id": "je_reversal"}
    assert stored_payment["status"] == "reversed"
    assert stored_payment["reversal_je_id"] == "je_reversal"
    assert stored_original["reversed"] is True
    assert refreshed == ["bill_1"]


def test_reversed_payments_do_not_reduce_bill_outstanding(monkeypatch):
    payments = _Collection([
        {"id": "active", "bill_ids": ["bill_1"], "bill_splits": {"bill_1": 300}},
        {"id": "reversed", "bill_ids": ["bill_1"], "bill_splits": {"bill_1": 500},
         "status": "reversed"},
    ])
    monkeypatch.setattr(vendors, "sdb", SimpleNamespace(vendor_payments=payments))

    assert asyncio.run(vendors._paid_against_bill("bill_1")) == 300


def test_payment_without_linked_journal_fails_closed(monkeypatch):
    payments = _Collection([{
        "id": "pmt_1", "vendor_id": "vendor_1", "amount": 500, "status": "posted",
    }])
    monkeypatch.setattr(vendors, "sdb", SimpleNamespace(
        vendor_payments=payments,
        journal_entries=_Collection([]),
    ))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vendors._reverse_vendor_payment_locked(
            {"user_id": "admin", "org_id": "org_a"}, "pmt_1"
        ))

    assert exc.value.status_code == 409
    assert payments.rows[0]["status"] == "posted"


def test_vendor_ledger_nets_a_reversed_payment_to_zero(monkeypatch):
    fake = SimpleNamespace(
        vendors_acc=_Collection([{"id": "vendor_1", "name": "Vendor"}]),
        vendor_bills=_Collection([{
            "id": "bill_1", "vendor_id": "vendor_1", "bill_date": "2026-10-01",
            "bill_number": "VB-1", "total": 500, "status": "received",
        }]),
        vendor_payments=_Collection([{
            "id": "pmt_1", "vendor_id": "vendor_1", "payment_date": "2026-10-02",
            "amount": 500, "status": "reversed", "reversed_at": "2026-10-03T10:00:00Z",
        }]),
    )
    monkeypatch.setattr(vendors, "sdb", fake)

    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "org_id": "org_a"}

    monkeypatch.setattr(vendors, "require_user", user)
    monkeypatch.setattr(vendors, "_require", lambda *_args: None)

    result = asyncio.run(vendors.vendor_full_ledger("vendor_1", _request()))

    assert [entry["type"] for entry in result["entries"]] == [
        "bill", "payment", "payment_reversal",
    ]
    assert result["total_billed"] == 500
    assert result["total_paid"] == 0
    assert result["outstanding"] == 500
