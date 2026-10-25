"""Regression coverage for accounting integrity helpers."""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routes.accounting as accounting
from models.accounting import (
    DEFAULT_COA, IncomeIn, JournalLine, MilestoneIn, NonOperatingTransactionIn,
)
from routes.accounting import (
    _cash_flow_bucket,
    _cash_collection_source,
    _can_void_from_journal,
    _invoice_accrual_amounts,
    _linked_journal_key,
    _milestone_due_bucket,
    _party_ledger_name,
    _require_full_linked_payment,
)
from routes.finance_extras import _bank_match_error
from routes.finance_extras import RecurringIn
from core.finance import resolve_period


def test_all_time_period_is_explicit_and_unbounded():
    assert resolve_period(fy="all") == (None, None, "All time")
    assert resolve_period(fy="ALL_TIME") == (None, None, "All time")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_money_is_rejected_before_persistence(bad):
    with pytest.raises(ValidationError):
        IncomeIn(date="2026-10-22", amount=bad, income_account_id="income",
                 bank_account_id="bank")
    with pytest.raises(ValidationError):
        JournalLine(account_id="bank", debit=bad)
    with pytest.raises(ValidationError):
        MilestoneIn(project_id="project", name="Advance", amount=bad)
    with pytest.raises(ValidationError):
        RecurringIn(name="Rent", amount=bad, expense_account_id="rent",
                    paid_from_account_id="bank")


def test_milestones_require_a_positive_amount_or_valid_percent():
    with pytest.raises(ValidationError):
        MilestoneIn(project_id="project", name="Empty")
    with pytest.raises(ValidationError):
        MilestoneIn(project_id="project", name="Negative", amount=-1)
    with pytest.raises(ValidationError):
        MilestoneIn(project_id="project", name="Zero percent", percent=0)
    assert MilestoneIn(project_id="project", name="Half", percent=50).percent == 50


def test_linked_journal_keys_are_stable_and_manual_entries_are_unkeyed():
    assert _linked_journal_key("org_a", "invoice_payment", "inv_1") == "org_a:invoice_payment:inv_1"
    assert _linked_journal_key("org_a", "milestone_payment", "ms_1") == "org_a:milestone_payment:ms_1"
    assert _linked_journal_key("org_a", "invoice_payment_reversal", "je_1") == \
        "org_a:invoice_payment_reversal:je_1"
    assert _linked_journal_key("org_a", "manual", "source_1") is None
    assert _linked_journal_key("org_a", "income", None) is None
    assert _linked_journal_key("org_a", "invoice_payment", "inv_1") != \
        _linked_journal_key("org_b", "invoice_payment", "inv_1")


def test_default_account_ids_are_stable_and_tenant_scoped():
    assert accounting._default_account_id("org_a", "Owner Drawings") == \
        accounting._default_account_id("org_a", "owner drawings")
    assert accounting._default_account_id("org_a", "Owner Drawings") != \
        accounting._default_account_id("org_b", "Owner Drawings")


def test_default_account_names_and_codes_are_unique():
    names = [row[0].casefold() for row in DEFAULT_COA]
    codes = [row[2] for row in DEFAULT_COA]
    assert len(names) == len(set(names))
    assert len(codes) == len(set(codes))
    assert ("Investments - Gold", "asset", "1601") in DEFAULT_COA


def test_invoice_accrual_splits_receivable_revenue_and_tax():
    assert _invoice_accrual_amounts({
        "subtotal": 1000, "tax": 180, "total": 1180,
    }) == (1000.0, 180.0, 1180.0)
    with pytest.raises(HTTPException):
        _invoice_accrual_amounts({"subtotal": 1000, "tax": 180, "total": 1000})


@pytest.mark.parametrize(("source", "counter", "net", "expected"), [
    ("invoice_payment", {"account_type": "asset", "account_name": "Accounts Receivable"},
     1180, ("operating", "Client invoice collections")),
    ("expense", {"account_type": "expense", "account_name": "Site Expense"},
     -500, ("operating", "Operating expenses")),
    ("loan_disbursement", {"account_type": "liability", "account_name": "Bank Loan"},
     10000, ("financing", "Loan proceeds")),
    ("non_operating", {"account_type": "equity", "account_name": "Owner Drawings"},
     -2000, ("financing", "Owner drawings")),
    ("non_operating", {"account_type": "asset", "account_name": "Investments - Gold"},
     -3000, ("investing", "Gold investments")),
    ("non_operating_reversal", {"account_type": "asset", "account_name": "Advance to - Person"},
     1000, ("investing", "Advance repayments received")),
])
def test_cash_flow_activity_classification(source, counter, net, expected):
    entry = {
        "source": source,
        "lines": [
            {"account_id": "bank", "account_type": "asset", "account_name": "Bank"},
            {"account_id": "counter", **counter},
        ],
    }
    assert _cash_flow_bucket(entry, {"bank"}, net) == expected


def test_invoice_issue_posts_to_receivable_revenue_and_gst(monkeypatch):
    class Journals:
        async def find_one(self, *_args, **_kwargs):
            return None

    posted = []

    async def accounts():
        return (
            {"id": "ar", "name": "Accounts Receivable", "type": "asset"},
            {"id": "income", "name": "Consultancy Income", "type": "income"},
            {"id": "gst", "name": "GST Payable", "type": "liability"},
        )

    async def post(_user, date, narration, lines, **kwargs):
        posted.append({"date": date, "narration": narration, "lines": lines, **kwargs})
        return {"id": "je_issue", "lines": lines}

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(journal_entries=Journals()))
    monkeypatch.setattr(accounting, "_invoice_accrual_accounts", accounts)
    monkeypatch.setattr(accounting, "_post_journal", post)

    invoice = {
        "id": "inv_1", "number": "INV-1", "issue_date": "2026-10-23",
        "subtotal": 1000, "tax": 180, "total": 1180,
    }
    result = asyncio.run(accounting.post_invoice_accrual_je({"user_id": "admin"}, invoice))
    assert result["id"] == "je_issue"
    assert posted[0]["source"] == "invoice_issue"
    assert posted[0]["source_id"] == "inv_1"
    assert [(line["account_id"], line["debit"], line["credit"])
            for line in posted[0]["lines"]] == [
        ("ar", 1180.0, 0), ("income", 0, 1000.0), ("gst", 0, 180.0),
    ]


def test_non_operating_transactions_require_positive_finite_money():
    valid = {
        "kind": "money_given", "date": "2026-10-23", "amount": 100,
        "bank_account_id": "bank", "party_name": "Ritesh Soni",
    }
    assert NonOperatingTransactionIn(**valid).amount == 100
    for amount in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            NonOperatingTransactionIn(**{**valid, "amount": amount})


def test_party_ledger_names_are_stable_and_require_a_name():
    assert _party_ledger_name("Advance to", "  Ritesh   Soni ") == "Advance to - Ritesh Soni"
    with pytest.raises(HTTPException) as exc:
        _party_ledger_name("Loan from", " ")
    assert exc.value.status_code == 400


def test_non_operating_workflows_post_expected_debit_and_credit(monkeypatch):
    posted = []

    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "org_id": "org_a", "permissions": ["finance.create"]}

    async def bank(*_args, **_kwargs):
        return {"id": "bank", "name": "Cash", "type": "asset", "is_bank": True}

    async def account(name, account_type, **_kwargs):
        return {"id": name, "name": name, "type": account_type, "active": True}

    async def post(_user, _date, narration, lines, **_kwargs):
        posted.append({"narration": narration, "lines": lines})
        return {"id": f"je_{len(posted)}", "lines": lines}

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(accounting, "require_user", user)
    monkeypatch.setattr(accounting, "has_permission", lambda *_args: True)
    monkeypatch.setattr(accounting, "require_asset_account", bank)
    monkeypatch.setattr(accounting, "_ensure_named_account", account)
    monkeypatch.setattr(accounting, "_seed_coa_if_empty", noop)
    monkeypatch.setattr(accounting, "_post_journal", post)
    monkeypatch.setattr(accounting, "audit", noop)

    cases = [
        ("owner_investment", None, "bank", "Owner Capital"),
        ("owner_withdrawal", None, "Owner Drawings", "bank"),
        ("gold_purchase", None, "Investments - Gold", "bank"),
        ("money_given", "Ritesh Soni", "Advance to - Ritesh Soni", "bank"),
        ("money_received", "Ritesh Soni", "bank", "Loan from - Ritesh Soni"),
    ]
    for kind, party_name, debit_id, credit_id in cases:
        payload = NonOperatingTransactionIn(
            kind=kind, date="2026-10-23", amount=100,
            bank_account_id="bank", party_name=party_name,
        )
        asyncio.run(accounting.create_non_operating_transaction(payload, None))
        assert posted[-1]["lines"][0]["account_id"] == debit_id
        assert posted[-1]["lines"][0]["debit"] == 100
        assert posted[-1]["lines"][1]["account_id"] == credit_id
        assert posted[-1]["lines"][1]["credit"] == 100


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


def test_journal_delete_uses_a_balancing_void(monkeypatch):
    class JournalEntries:
        async def find_one(self, *_args, **_kwargs):
            return {
                "id": "je_1", "source": "non_operating", "date": "2026-10-20",
                "org_id": "org_a", "total": 100,
            }

    async def user(*_args, **_kwargs):
        return {"user_id": "admin_a", "org_id": "org_a", "permissions": ["finance.delete"]}

    called = {}

    async def reverse(_user, je, **kwargs):
        called.update({"je": je, **kwargs})
        return {"id": "je_reverse"}

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(journal_entries=JournalEntries()))
    monkeypatch.setattr(accounting, "require_user", user)
    monkeypatch.setattr(accounting, "_reverse_journal_entry", reverse)

    result = asyncio.run(accounting.delete_journal("je_1", None))
    assert result["deleted"] is True
    assert result["reversal_je_id"] == "je_reverse"
    assert called["action"] == "delete"
    assert called["reversal_date"] == "2026-10-20"
    assert called["hide_from_books"] is True


def test_source_controlled_journal_cannot_be_deleted_directly(monkeypatch):
    class JournalEntries:
        async def find_one(self, *_args, **_kwargs):
            return {"id": "je_1", "source": "payroll", "source_id": "run_1"}

    async def user(*_args, **_kwargs):
        return {"user_id": "admin_a", "org_id": "org_a", "permissions": ["finance.delete"]}

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(journal_entries=JournalEntries()))
    monkeypatch.setattr(accounting, "require_user", user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(accounting.delete_journal("je_1", None))
    assert exc.value.status_code == 409
    assert "source record" in exc.value.detail


def test_only_safe_or_synchronised_journals_can_be_voided():
    assert _can_void_from_journal({"source": "non_operating"}) is True
    assert _can_void_from_journal({"source": "manual"}) is True
    assert _can_void_from_journal({"source": "invoice_payment", "source_id": "inv_1"}) is True
    assert _can_void_from_journal({"source": "payroll", "source_id": "run_1"}) is False
    assert _can_void_from_journal({"source": "invoice_issue", "source_id": "inv_1"}) is False


def test_balancing_void_marks_both_entries_hidden(monkeypatch):
    class JournalEntries:
        def __init__(self):
            self.updates = []

        async def update_one(self, query, update):
            self.updates.append((query, update))

    entries = JournalEntries()

    async def post(*_args, **_kwargs):
        return {"id": "je_reverse"}

    async def no_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(journal_entries=entries))
    monkeypatch.setattr(accounting, "_post_journal", post)
    monkeypatch.setattr(accounting, "audit", no_audit)
    original = {
        "id": "je_owner", "source": "non_operating", "date": "2026-10-20",
        "total": 10000, "narration": "Owner withdrawal",
        "lines": [
            {"account_id": "drawings", "debit": 10000, "credit": 0},
            {"account_id": "bank", "debit": 0, "credit": 10000},
        ],
    }
    result = asyncio.run(accounting._reverse_journal_entry(
        {"user_id": "admin_a", "org_id": "org_a"}, original,
        action="delete", reversal_date=original["date"], hide_from_books=True,
    ))
    assert result["id"] == "je_reverse"
    updates = {query["id"]: update for query, update in entries.updates}
    assert updates["je_owner"]["$set"]["voided_from_view"] is True
    assert updates["je_reverse"]["$set"]["voided_from_view"] is True
    assert updates["je_owner"]["$set"]["reversal_je_id"] == "je_reverse"


def test_owner_withdrawal_correction_reverses_and_reposts(monkeypatch):
    original = {
        "id": "je_owner", "source": "non_operating", "date": "2026-10-20",
        "total": 10000, "narration": "Personal withdrawal by owner",
        "lines": [
            {"account_id": "drawings", "debit": 10000, "credit": 0},
            {"account_id": "bank", "debit": 0, "credit": 10000},
        ],
    }

    class JournalEntries:
        def __init__(self):
            self.updates = []

        async def find_one(self, *_args, **_kwargs):
            return original

        async def update_one(self, query, update):
            self.updates.append((query, update))

    entries = JournalEntries()
    posted = {}

    async def user(*_args, **_kwargs):
        return {"user_id": "admin_a", "org_id": "org_a", "permissions": ["finance.update"]}

    async def reverse(_user, je, **kwargs):
        assert je is original
        assert kwargs["action"] == "correction"
        assert kwargs["hide_from_books"] is True
        return {"id": "je_reverse"}

    async def post(_user, date_value, narration, lines, **kwargs):
        posted.update({"date": date_value, "narration": narration, "lines": lines, **kwargs})
        return {"id": "je_corrected", "total": 12000}

    async def no_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(journal_entries=entries))
    monkeypatch.setattr(accounting, "require_user", user)
    monkeypatch.setattr(accounting, "_reverse_journal_entry", reverse)
    monkeypatch.setattr(accounting, "_post_journal", post)
    monkeypatch.setattr(accounting, "audit", no_audit)

    payload = accounting.JournalCorrectionIn(
        date="2026-10-21", narration="Corrected owner withdrawal",
        reference="OWNER-1", amount=12000,
    )
    result = asyncio.run(accounting.correct_journal("je_owner", payload, None))
    assert result["replacement"]["id"] == "je_corrected"
    assert posted["date"] == "2026-10-21"
    assert posted["source"] == "non_operating"
    assert posted["lines"][0]["debit"] == 12000
    assert posted["lines"][1]["credit"] == 12000
    assert any(update[1]["$set"].get("corrected_je_id") == "je_corrected"
               for update in entries.updates)


def test_invoice_issue_must_be_reversed_through_invoice_workflow(monkeypatch):
    class JournalEntries:
        async def find_one(self, *_args, **_kwargs):
            return {"id": "je_issue", "source": "invoice_issue", "source_id": "inv_1"}

    async def user(*_args, **_kwargs):
        return {"user_id": "admin_a", "org_id": "org_a", "permissions": ["finance.update"]}

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(journal_entries=JournalEntries()))
    monkeypatch.setattr(accounting, "require_user", user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(accounting.reverse_journal("je_issue", None))
    assert exc.value.status_code == 409
    assert "invoice" in exc.value.detail.lower()
