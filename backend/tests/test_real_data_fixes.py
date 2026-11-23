"""Problems found in the owner's live data, 2026-11-23.

* Vendor incentives saved with the client were the client's "payments" on the
  client statement, ledger, Money In list and receipt PDF.
* Milestone receipts were saved without the client.
* An equity account and Gold were flagged as banks; income was received into Gold.
* No credit card: one was created as an expense account.
* Cash went below zero (gold bought before any cash was recorded).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.accounting as acc
from core.finance import is_card_account, validate_method_account
from core.receipts import client_receipt_query, is_commission_receipt, payer

COMM = {"acc_incentive"}


def je(**kw):
    return {"source": "income", "lines": [{"account_id": "acc_fee"}], **kw}


def test_payer_is_vendor_for_any_incentive_signal():
    assert payer(je(client_id="cli_kpr"), COMM) == "client"
    assert payer(je(client_id="cli_kpr", vendor_id="ven_v"), COMM) == "vendor"     # D_1101's entries
    assert payer(je(client_id="cli_kpr", lines=[{"account_id": "acc_incentive"}]), COMM) == "vendor"
    assert payer(je(source="commission_income"), COMM) == "vendor"
    assert is_commission_receipt(je(source="commission_income_reversal"), COMM)


def test_client_receipts_include_project_receipts_saved_without_a_client():
    q = client_receipt_query("cli_r", ["prj_r"])
    assert {"client_id": "cli_r"} in q["$or"]
    assert {"project_id": {"$in": ["prj_r"]}, "client_id": {"$in": [None, ""]}} in q["$or"]
    assert "commission_income" not in q["source"]["$in"]
    assert client_receipt_query("cli_x", [])["$or"] == [{"client_id": "cli_x"}]


@pytest.mark.parametrize("doc", [
    {"name": "yash drawings", "type": "equity", "is_bank": True},
    {"name": "Investments - Gold", "type": "asset", "is_bank": True},
    {"name": "Gold", "type": "asset", "is_bank": True},
    {"name": "Advance to - Viren", "type": "asset", "is_bank": True},
    {"name": "HDFC Card", "type": "expense", "is_card": True},
    {"name": "HDFC Card", "type": "asset", "is_card": True},
    {"name": "HDFC Card", "type": "liability", "is_card": True, "is_bank": True},
])
def test_only_real_cash_bank_or_card_accounts_get_the_flags(doc):
    with pytest.raises(HTTPException) as exc:
        acc._check_account_flags(doc)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("doc", [
    {"name": "BANK_SBI", "type": "asset", "is_bank": True},
    {"name": "Cash", "type": "asset", "is_bank": True},
    {"name": "HDFC Credit Card", "type": "liability", "is_card": True},
    {"name": "Gold", "type": "asset"},
])
def test_valid_flags_pass(doc):
    acc._check_account_flags(doc)


def test_card_payments_must_use_the_card_method():
    card = {"name": "HDFC Credit Card", "type": "liability", "is_card": True}
    assert is_card_account(card)
    validate_method_account("credit_card", card)
    with pytest.raises(HTTPException):
        validate_method_account("bank_transfer", card)
    assert not is_card_account({"name": "Credit Card HDFC", "type": "expense"})   # the owner's workaround


class _Agg:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _n):
        return self.rows


def _till(monkeypatch, days, opening=0.0):
    monkeypatch.setattr(acc, "sdb", SimpleNamespace(
        journal_entries=SimpleNamespace(aggregate=lambda _p: _Agg(days))))
    return {"id": "acc_cash", "name": "Cash", "type": "asset", "opening_balance": opening}


def test_cash_available_counts_later_days(monkeypatch):
    cash = _till(monkeypatch, [{"_id": "2025-01-01", "debit": 10000, "credit": 0},
                               {"_id": "2025-01-10", "debit": 0, "credit": 9000}])
    assert asyncio.run(acc._cash_available_on(cash, "2025-01-05")) == 1000     # 10 Jan would go negative
    assert asyncio.run(acc._cash_available_on(cash, "2025-01-20")) == 1000
    assert asyncio.run(acc._cash_available_on(cash, "2024-07-22")) == 0        # nothing yet (owner's gold)


def test_cash_shortfall_refused_only_for_cash(monkeypatch):
    cash = _till(monkeypatch, [{"_id": "2025-01-01", "debit": 500, "credit": 0}])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(acc._refuse_cash_shortfall(cash, "2025-01-02", 500.01))
    assert exc.value.status_code == 409
    asyncio.run(acc._refuse_cash_shortfall(cash, "2025-01-02", 500))
    asyncio.run(acc._refuse_cash_shortfall({"id": "b", "name": "BANK_SBI", "type": "asset"}, "2025-01-02", 10**9))
