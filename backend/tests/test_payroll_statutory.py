"""CA review 2026-11-24: salary cost and statutory dues.

Before: only net pay (plus advance recovered) was booked, so PF/ESI/PT/TDS
withheld from salary vanished: cost understated, nothing owed to the
government. A salary correction also dropped the advance recovery.
"""
import asyncio

import routes.accounting as accounting
import routes.employee_advances as advances
from routes import payroll


def _fake_accounts(monkeypatch):
    async def named(name, account_type, **_kw):
        return {"id": f"acc_{name.replace(' ', '_').lower()}", "name": name, "type": account_type}

    async def advances_account():
        return {"id": "acc_employee_advances", "name": "Employee Advances", "type": "asset"}

    monkeypatch.setattr(accounting, "_ensure_named_account", named)
    monkeypatch.setattr(advances, "advances_account", advances_account)


def test_withheld_amounts_are_cost_and_owed_to_government(monkeypatch):
    _fake_accounts(monkeypatch)
    breakdown = {"gross": 30000, "pf": 1800, "esi": 0, "pt": 200, "tds": 1000, "net": 25000}
    lines = asyncio.run(payroll._salary_lines(breakdown, {"advances_recovered": 2000}, 25000,
                                              "acc_salary", "acc_bank", "Asha"))
    by = {line["account_id"]: line for line in lines}
    assert by["acc_salary"]["debit"] == 30000            # 25,000 paid + 2,000 advance + 3,000 withheld
    assert by["acc_bank"]["credit"] == 25000
    assert by["acc_employee_advances"]["credit"] == 2000
    assert by["acc_pf_payable"]["credit"] == 1800
    assert by["acc_professional_tax_payable"]["credit"] == 200
    assert by["acc_tds_payable"]["credit"] == 1000
    assert "acc_esi_payable" not in by
    assert round(sum(l["debit"] for l in lines), 2) == round(sum(l["credit"] for l in lines), 2)


def test_no_deductions_books_net_only(monkeypatch):
    _fake_accounts(monkeypatch)
    lines = asyncio.run(payroll._salary_lines({"net": 15000}, {}, 15000, "acc_salary", "acc_bank", "Meet"))
    assert [(l["account_id"], l["debit"], l["credit"]) for l in lines] == [
        ("acc_salary", 15000, 0), ("acc_bank", 0, 15000)]
