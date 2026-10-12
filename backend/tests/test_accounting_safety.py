"""Regression coverage for accounting integrity helpers."""

import pytest
from fastapi import HTTPException

from routes.accounting import (
    _cash_collection_source,
    _linked_journal_key,
    _require_full_linked_payment,
)


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
