"""Owner corrections, 2026-11-23.

1. Vendor commission never reduces a client's outstanding fee.
   Rs 3 crore x 6% = Rs 18,00,000 fee; Rs 2,00,000 received from the client;
   vendor incentives are reported separately -> Rs 16,00,000 still to receive.
2. Loans and advances post to the person's existing ledger by account ID.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import server
import routes.accounting as acc

BANK = {"account_type": "asset", "account_name": "Bank - Primary"}
COMM = "acc_incentive"


def receipt(amount, income="acc_consultancy", source="income", vendor_id=None):
    return {"source": source, "vendor_id": vendor_id, "lines": [
        {**BANK, "account_id": "acc_bank", "debit": amount, "credit": 0},
        {"account_type": "income", "account_id": income, "debit": 0, "credit": amount}]}


def reversal(of):
    return {"source": f"{of['source']}_reversal", "lines": [
        {**l, "debit": l["credit"], "credit": l["debit"]} for l in of["lines"]]}


def test_commission_is_kept_out_of_client_fee_received():
    client = receipt(200000)
    by_vendor = receipt(100000, income=COMM, vendor_id="ven_1")
    by_account = receipt(50000, income=COMM)                     # no vendor on the entry
    from_vendor_module = receipt(25000, income=COMM, source="commission_income")
    received, commission = server.split_project_receipts(
        [client, by_vendor, by_account, from_vendor_module], {COMM})
    assert received == 200000
    assert commission == 175000


def test_reversals_only_undo_their_own_kind():
    client = receipt(200000)
    refund = reversal(receipt(20000))                            # client receipt reversed
    incentive = receipt(50000, income=COMM)
    incentive_reversed = reversal(incentive)                     # reversal copies the accounts
    received, commission = server.split_project_receipts(
        [client, refund, incentive, incentive_reversed], {COMM})
    assert received == 180000
    assert commission == 0


def test_owner_example_still_to_receive_is_fee_minus_client_payments():
    project = {"budget": 30000000, "fee_structure_type": "percentage_consultancy",
               "fee_project_value": 30000000, "fee_percentage": 6}
    received, commission = server.split_project_receipts(
        [receipt(200000), receipt(352500, income=COMM, vendor_id="ven_1")], {COMM})
    money = server._project_money(project, [], [], received)
    assert money["basis"] == 1800000
    assert money["received"] == 200000
    assert money["still_to_receive"] == 1600000
    assert commission == 352500


@pytest.mark.parametrize("project,client_paid,still", [
    ({"budget": 6000000, "fee_structure_type": "lump_sum", "fee_lump_sum_amount": 600000}, 100000, 500000),
    ({"budget": 6000000, "fee_structure_type": "per_sqft", "site_area_sqft": 2400, "fee_rate_per_sqft": 250}, 600000, 0),
    ({"budget": 6000000, "fee_structure_type": "turnkey", "fee_contract_value": 6000000}, 1000000, 5000000),
])
def test_commission_never_changes_any_fee_type(project, client_paid, still):
    received, _ = server.split_project_receipts(
        [receipt(client_paid), receipt(75000, income=COMM, vendor_id="ven_9")], {COMM})
    assert server._project_money(project, [], [], received)["still_to_receive"] == still


# ---------------------------------------------------------------- party ledgers
def test_party_side_is_read_from_type_and_name():
    assert acc._party_side_of({"name": "Loan from - KPR", "type": "liability"}) == "loan"
    assert acc._party_side_of({"name": "Advance to - Ritesh", "type": "asset"}) == "advance"
    assert acc._party_side_of({"name": "Loan from - KPR", "type": "asset"}) is None
    assert acc._party_side_of({"name": "Bank - Primary", "type": "asset"}) is None
    assert acc._party_display({"name": "Loan from - KPR"}) == "KPR"


def _payload(**kw):
    return SimpleNamespace(party_account_id=kw.get("party_account_id"), party_name=kw.get("party_name"))


def test_repayment_must_choose_an_existing_ledger(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(acc._party_ledger(_payload(party_name="KPR"), "loan", create=False))
    assert exc.value.status_code == 400 and "Choose the person" in exc.value.detail


def test_chosen_ledger_must_match_the_transaction(monkeypatch):
    rows = {"acc_adv": {"id": "acc_adv", "name": "Advance to - KPR", "type": "asset"},
            "acc_loan": {"id": "acc_loan", "name": "Loan from - KPR", "type": "liability"}}

    async def find_one(q, p=None):
        return rows.get(q.get("id"))

    monkeypatch.setattr(acc, "sdb", SimpleNamespace(accounts=SimpleNamespace(find_one=find_one)))
    account, person = asyncio.run(acc._party_ledger(_payload(party_account_id="acc_loan"), "loan", create=False))
    assert account["id"] == "acc_loan" and person == "KPR"
    with pytest.raises(HTTPException) as wrong:
        asyncio.run(acc._party_ledger(_payload(party_account_id="acc_adv"), "loan", create=False))
    assert wrong.value.status_code == 400
    with pytest.raises(HTTPException) as foreign:     # unknown here (e.g. another workspace's id)
        asyncio.run(acc._party_ledger(_payload(party_account_id="acc_other_tenant"), "loan", create=False))
    assert foreign.value.status_code == 400
