"""Opening balance for an account that already has entries posts an adjustment journal."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.accounting as accounting
from routes.accounting import OpeningAdjustmentIn, _can_void_from_journal


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a):
        return self

    def limit(self, *_a):
        return self

    async def to_list(self, _n):
        return self.rows


def _setup(monkeypatch, account, first_dates):
    posted = {}

    class Accounts:
        async def find_one(self, query, _proj=None):
            return account if query.get("id") == account["id"] else None

    class Journals:
        def find(self, *_a, **_k):
            return _Cursor([{"date": d} for d in sorted(first_dates)[:1]])

    async def user(*_a, **_k):
        return {"user_id": "u1", "org_id": "org_a"}

    async def offset(name, kind):
        assert (name, kind) == ("Opening Balance Adjustment", "equity")
        return {"id": "acc_obadj"}

    async def post(_user, date, narration, lines, **kwargs):
        posted.update(date=date, narration=narration, lines=lines, **kwargs)
        return {"id": "je_1"}

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(accounts=Accounts(), journal_entries=Journals()))
    monkeypatch.setattr(accounting, "require_user", user)
    monkeypatch.setattr(accounting, "has_permission", lambda *_a: True)
    monkeypatch.setattr(accounting, "_ensure_named_account", offset)
    monkeypatch.setattr(accounting, "_post_journal", post)
    monkeypatch.setattr(accounting, "audit", noop)
    return posted


def _call(acc_id, **body):
    return asyncio.run(accounting.add_opening_adjustment(
        acc_id, OpeningAdjustmentIn(**body), request=None))


def test_bank_opening_is_debited_the_day_before_its_first_entry(monkeypatch):
    bank = {"id": "acc_hdfc", "name": "Bank_HDFC", "type": "asset", "active": True}
    posted = _setup(monkeypatch, bank, ["2026-06-02", "2026-11-03"])
    _call("acc_hdfc", amount=10336)
    assert posted["date"] == "2026-06-01"
    assert posted["source"] == "opening_balance" and posted["source_id"] == "acc_hdfc"
    bank_line, offset_line = posted["lines"]
    assert (bank_line["account_id"], bank_line["debit"], bank_line["credit"]) == ("acc_hdfc", 10336, 0)
    assert (offset_line["account_id"], offset_line["debit"], offset_line["credit"]) == ("acc_obadj", 0, 10336)


def test_liability_opening_is_credited_and_date_can_be_chosen(monkeypatch):
    loan = {"id": "acc_loan", "name": "Car loan", "type": "liability", "active": True}
    posted = _setup(monkeypatch, loan, [])
    _call("acc_loan", amount=5000, date="2026-04-01", note="per statement")
    assert posted["date"] == "2026-04-01"
    assert posted["lines"][0]["credit"] == 5000 and posted["lines"][1]["debit"] == 5000
    assert "per statement" in posted["narration"]


def test_negative_amount_reduces_the_account(monkeypatch):
    bank = {"id": "acc_hdfc", "name": "Bank_HDFC", "type": "asset", "active": True}
    posted = _setup(monkeypatch, bank, ["2026-06-02"])
    _call("acc_hdfc", amount=-200)
    assert posted["lines"][0]["credit"] == 200 and posted["lines"][1]["debit"] == 200


def test_zero_and_unknown_accounts_are_rejected(monkeypatch):
    bank = {"id": "acc_hdfc", "name": "Bank_HDFC", "type": "asset", "active": True}
    _setup(monkeypatch, bank, [])
    with pytest.raises(HTTPException) as zero:
        _call("acc_hdfc", amount=0)
    assert zero.value.status_code == 400
    with pytest.raises(HTTPException) as missing:
        _call("acc_nope", amount=10)
    assert missing.value.status_code == 404


def test_opening_adjustments_can_be_reversed_from_the_ledger():
    assert _can_void_from_journal({"source": "opening_balance", "source_id": "acc_hdfc"})
