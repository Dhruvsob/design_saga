"""Regression coverage for accounting integrity helpers."""

from datetime import date

import pytest
from fastapi import HTTPException

from routes.accounting import (
    _cash_collection_source,
    _linked_journal_key,
    _milestone_due_bucket,
    _require_full_linked_payment,
)
from routes.finance_extras import _bank_match_error
from core.finance import resolve_period


def test_all_time_period_is_explicit_and_unbounded():
    assert resolve_period(fy="all") == (None, None, "All time")
    assert resolve_period(fy="ALL_TIME") == (None, None, "All time")


def test_linked_journal_keys_are_stable_and_manual_entries_are_unkeyed():
    assert _linked_journal_key("org_a", "invoice_payment", "inv_1") == "org_a:invoice_payment:inv_1"
    assert _linked_journal_key("org_a", "milestone_payment", "ms_1") == "org_a:milestone_payment:ms_1"
    assert _linked_journal_key("org_a", "invoice_payment_reversal", "je_1") == \
        "org_a:invoice_payment_reversal:je_1"
    assert _linked_journal_key("org_a", "manual", "source_1") is None
    assert _linked_journal_key("org_a", "income", None) is None
    assert _linked_journal_key("org_a", "invoice_payment", "inv_1") != \
        _linked_journal_key("org_b", "invoice_payment", "inv_1")


def test_linked_payments_must_settle_the_full_source_amount():
    _require_full_linked_payment("invoice", 1180, 1180.004)
    with pytest.raises(HTTPException) as exc:
        _require_full_linked_payment("invoice", 100, 1180)
    assert exc.value.status_code == 400
    assert "1180.00" in exc.value.detail


def test_collection_sources_include_reversals_for_net_reporting():
    assert _cash_collection_source("income") is True
    assert _cash_collection_source("invoice_payment") is True
    assert _cash_collection_source("invoice_payment_reversal") is True
    assert _cash_collection_source("milestone_payment_reversal") is True
    assert _cash_collection_source("payroll") is False


def test_milestone_due_buckets_cover_collection_workflow():
    today = date(2026, 10, 20)
    horizon = date(2026, 11, 19)
    assert _milestone_due_bucket("2026-10-19", today, horizon) == "overdue"
    assert _milestone_due_bucket("2026-10-20", today, horizon) == "due_30"
    assert _milestone_due_bucket("2026-11-19", today, horizon) == "due_30"
    assert _milestone_due_bucket("2026-11-20", today, horizon) == "later"
    assert _milestone_due_bucket(None, today, horizon) == "no_due_date"
    assert _milestone_due_bucket("not-a-date", today, horizon) == "no_due_date"


def test_bank_match_requires_same_account_direction_amount_and_nearby_date():
    row = {"date": "2026-10-20", "amount": 1250, "account_id": "bank_1"}
    valid = {
        "date": "2026-10-22",
        "lines": [
            {"account_id": "bank_1", "debit": 1250, "credit": 0},
            {"account_id": "income_1", "debit": 0, "credit": 1250},
        ],
    }
    assert _bank_match_error(row, valid) is None

    wrong_direction = {**valid, "lines": [{"account_id": "bank_1", "debit": 0, "credit": 1250}]}
    assert "matching debit" in _bank_match_error(row, wrong_direction)
    assert "within 3 days" in _bank_match_error(row, {**valid, "date": "2026-10-30"})
    assert "cannot be matched" in _bank_match_error(row, {**valid, "reversed": True})
