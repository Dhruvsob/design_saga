"""Read-only accounting source-integrity report regressions."""
import asyncio

import pytest
from fastapi import HTTPException

import routes.accounting as accounting
from routes.accounting import _evaluate_source_integrity


def _je(jid, source="manual", source_id=None, debit=100.0, credit=100.0, **extra):
    return {"id": jid, "date": "2026-10-01", "source": source, "source_id": source_id,
            "total": debit, "lines": [{"debit": debit, "credit": 0},
                                      {"debit": 0, "credit": credit}], **extra}


def test_clean_ledger_reports_ok():
    journals = [_je("je1", "vendor_payment", "pmt1"), _je("je2", "payroll", "run1")]
    report = _evaluate_source_integrity(
        journals, {"vendor_payments": {"pmt1"}, "payroll_runs": {"run1"}},
        [{"id": "run1", "journal_id": "je2", "status": "paid"}],
        [{"id": "pmt1", "journal_entry_id": "je1"}])
    assert report["ok"] is True
    assert all(v == 0 for v in report["counts"].values())


def test_detects_unbalanced_and_single_line_journals():
    single = {"id": "je3", "source": "manual", "lines": [{"debit": 5, "credit": 0}]}
    report = _evaluate_source_integrity([_je("je1", debit=100, credit=90), single], {}, [], [])
    assert report["counts"]["unbalanced_journals"] == 2


def test_orphaned_active_source_journal_is_flagged_but_reversed_is_not():
    journals = [
        _je("je1", "vendor_bill", "bill_gone"),
        _je("je2", "vendor_bill", "bill_gone_too", reversed=True, reversal_je_id="je3"),
        _je("je3", "vendor_bill_reversal", "je2"),
        _je("je4", "expense", None),  # generic Money Out has no source record
    ]
    report = _evaluate_source_integrity(journals, {"vendor_bills": set()}, [], [])
    assert report["counts"]["orphaned_source_journals"] == 1
    assert report["samples"]["orphaned_source_journals"][0]["id"] == "je1"
    assert report["counts"]["broken_reversal_links"] == 0


def test_broken_reversal_link_detected():
    journals = [_je("je1", "payroll", "run1", reversed=True, reversal_je_id="missing")]
    report = _evaluate_source_integrity(journals, {"payroll_runs": {"run1"}}, [], [])
    assert report["counts"]["broken_reversal_links"] == 1


def test_paid_sources_pointing_to_missing_or_reversed_journals():
    journals = [_je("je1", "payroll", "run1", reversed=True, reversal_je_id="je2"),
                _je("je2", "payroll_reversal", "je1")]
    report = _evaluate_source_integrity(
        journals, {"payroll_runs": {"run1"}},
        [{"id": "run1", "journal_id": "je1", "month": 10, "year": 2026}],
        [{"id": "pmt9", "journal_entry_id": None}])
    kinds = sorted(r["kind"] for r in report["samples"]["paid_sources_without_active_journal"])
    assert kinds == ["payroll_run", "vendor_payment"]


def test_integrity_route_rejects_non_admin_before_reading(monkeypatch):
    async def fake_user(*_args, **_kwargs):
        return {"user_id": "u1", "org_id": "org_a", "role": "Accountant"}

    class Exploding:
        def __getattr__(self, _name):
            raise AssertionError("database must not be read for unauthorized callers")

        def __getitem__(self, _name):
            raise AssertionError("database must not be read for unauthorized callers")

    monkeypatch.setattr(accounting, "require_user", fake_user)
    monkeypatch.setattr(accounting, "has_permission", lambda _u, perm: perm == "finance.read")
    monkeypatch.setattr(accounting, "sdb", Exploding())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(accounting.accounting_source_integrity(request=None))
    assert exc.value.status_code == 403


# --- ACC-09: historical Cash/Bank method vs ledger mismatches ---------------
from routes.accounting import _journal_method_record, _method_account_mismatches

ACCOUNTS = {
    "cash": {"id": "cash", "name": "Cash", "is_bank": True},   # default chart flag
    "bank": {"id": "bank", "name": "Bank - Primary", "is_bank": True},
}


def _rec(kind, method, account_id, **extra):
    return {"kind": kind, "id": f"{kind}_1", "date": "2026-10-31", "amount": 20000,
            "method": method, "account_id": account_id, "party": "Rahul", **extra}


def test_bank_transfer_booked_to_cash_is_listed_for_every_record_type():
    kinds = ["payroll_run", "vendor_payment", "commission_receipt", "collection_receipt"]
    rows = _method_account_mismatches([_rec(k, "bank_transfer", "cash") for k in kinds], ACCOUNTS)
    assert sorted(r["kind"] for r in rows) == sorted(kinds)
    assert all(r["account_name"] == "Cash" and "bank transfer" in r["problem"] for r in rows)
    assert all(r["fix"] and r["confidence"] == "recorded" for r in rows)


def test_cash_method_booked_to_bank_is_listed():
    rows = _method_account_mismatches([_rec("payroll_run", "cash", "bank")], ACCOUNTS)
    assert len(rows) == 1 and "non-cash account" in rows[0]["problem"]


def test_consistent_or_unknown_account_records_are_not_listed():
    rows = _method_account_mismatches([
        _rec("payroll_run", "cash", "cash"), _rec("vendor_payment", "upi", "bank"),
        _rec("vendor_payment", None, "cash"), _rec("payroll_run", "bank_transfer", "deleted_acc"),
    ], ACCOUNTS)
    assert rows == []


def test_generic_money_in_and_out_method_is_inferred_from_default_narration():
    money_in = {"id": "je1", "date": "2026-10-01", "total": 500, "source": "income",
                "narration": "Payment received via bank_transfer",
                "lines": [{"account_id": "cash", "account_type": "asset", "debit": 500, "credit": 0},
                          {"account_id": "inc", "account_type": "income", "debit": 0, "credit": 500}]}
    money_out = {"id": "je2", "date": "2026-10-02", "total": 300, "source": "expense",
                 "narration": "Expense — upi",
                 "lines": [{"account_id": "rent", "account_type": "expense", "debit": 300, "credit": 0},
                           {"account_id": "cash", "account_type": "asset", "debit": 0, "credit": 300}]}
    records = [_journal_method_record(money_in), _journal_method_record(money_out)]
    assert [r["method"] for r in records] == ["bank_transfer", "upi"]
    rows = _method_account_mismatches(records, ACCOUNTS)
    assert {r["kind"] for r in rows} == {"money_in", "money_out"}
    assert all(r["confidence"] == "inferred" for r in rows)


def test_custom_narration_is_not_guessed():
    je = {"id": "je3", "source": "income", "narration": "Advance from Mehta for site work",
          "lines": [{"account_id": "cash", "account_type": "asset", "debit": 10, "credit": 0}]}
    assert _journal_method_record(je) is None
