"""Cash/Bank method-account consistency across every money path (ACC-08)."""
import inspect

import pytest
from fastapi import HTTPException

from core.finance import is_bank_account, is_cash_account, validate_method_account
from routes import accounting, payroll, vendors

CASH = {"name": "Cash", "is_bank": True}          # default chart flags Cash as is_bank
PETTY = {"name": "Petty Cash", "is_bank": True}
BANK = {"name": "Bank - Primary", "is_bank": True}
OTHER_ASSET = {"name": "Security Deposits", "is_bank": False}


def test_cash_accounts_are_never_treated_as_banks_despite_flag():
    assert is_cash_account(CASH) and is_cash_account(PETTY)
    assert not is_bank_account(CASH) and not is_bank_account(PETTY)
    assert is_bank_account(BANK)


@pytest.mark.parametrize("method,account", [
    ("bank_transfer", CASH), ("upi", PETTY), ("cheque", CASH),
    ("cash", BANK), ("bank_transfer", OTHER_ASSET), ("wire", BANK),
])
def test_mismatched_method_and_account_is_rejected(method, account):
    with pytest.raises(HTTPException) as exc:
        validate_method_account(method, account)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("method,account", [
    ("cash", CASH), ("cash", PETTY), ("bank_transfer", BANK), ("upi", BANK), ("cheque", BANK),
])
def test_matching_method_and_account_is_accepted(method, account):
    validate_method_account(method, account)


def test_every_money_path_uses_the_shared_rule():
    for fn in (accounting._validate_received_into_account, accounting._validate_paid_from_account,
               vendors._validate_commission_receipt_account, payroll.pay_salary,
               vendors.create_vendor_payment):
        assert "validate_method_account" in inspect.getsource(fn), fn.__name__
