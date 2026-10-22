"""Regression coverage for financial read authorization helpers."""

import asyncio
import pytest
from fastapi import HTTPException

import server
from server import _can_read_invoices, _employee_for_user, _ensure_invoice_read
from routes.vendors import _vendor_for_user


def test_invoice_read_allows_invoice_or_finance_permission():
    assert _can_read_invoices({"role": "ProjectManager"}) is True
    assert _can_read_invoices({"role": "Accountant"}) is True


def test_invoice_read_rejects_regular_employee():
    user = {"role": "Employee"}
    assert _can_read_invoices(user) is False
    with pytest.raises(HTTPException) as exc:
        _ensure_invoice_read(user)
    assert exc.value.status_code == 403


def test_invoice_read_honours_tenant_permission_overrides():
    assert _can_read_invoices({"role": "Employee", "permissions": ["invoices.read"]}) is True
    assert _can_read_invoices({"role": "Employee", "permissions": ["finance.read"]}) is True


def test_employee_projection_hides_compensation_and_private_hr_data():
    employee = {
        "id": "emp_1",
        "first_name": "Test",
        "salary": {"net_monthly": 50000},
        "salary_history": [{"net_monthly": 45000}],
        "bank": {"account_number": "1234"},
        "aadhaar": "111122223333",
        "gender": "Female",
        "documents": [{"label": "PAN"}],
        "performance": {"current_kpi_score": 9},
    }

    visible = _employee_for_user(employee, {"role": "ProjectManager"})

    assert visible["id"] == "emp_1"
    assert visible["first_name"] == "Test"
    for key in ("salary", "salary_history", "bank", "aadhaar", "gender", "documents", "performance"):
        assert key not in visible


def test_employee_projection_separates_payroll_and_hr_permissions():
    employee = {
        "salary": {"net_monthly": 50000},
        "bank": {"account_number": "1234"},
        "aadhaar": "111122223333",
    }

    accountant = _employee_for_user(employee, {"role": "Accountant"})
    assert accountant["salary"]["net_monthly"] == 50000
    assert accountant["bank"]["account_number"] == "1234"
    assert "aadhaar" not in accountant

    hr_only = _employee_for_user(
        employee,
        {"role": "Employee", "permissions": ["employees.update"]},
    )
    assert hr_only["aadhaar"] == "111122223333"
    assert "salary" not in hr_only


def test_vendor_projection_hides_financial_identity_from_operational_users():
    vendor = {
        "id": "vendor_1", "name": "Site supplier", "phone": "123",
        "pan": "ABCDE1234F", "bank_account_number": "123456",
        "bank_ifsc": "BANK0001", "upi_id": "private@bank",
        "commission": {"applicable": True, "percentage": 5},
    }
    visible = _vendor_for_user(vendor, {"role": "Employee"})
    assert visible["name"] == "Site supplier"
    for key in ("pan", "bank_account_number", "bank_ifsc", "upi_id", "commission"):
        assert key not in visible

    accountant = _vendor_for_user(vendor, {"role": "Accountant"})
    assert accountant["bank_account_number"] == "123456"


def test_quotation_actuals_require_invoice_or_finance_read(monkeypatch):
    async def regular_quotation_reader(*_args, **_kwargs):
        return {"role": "Employee", "permissions": ["quotations.read"]}

    monkeypatch.setattr(server, "require_user", regular_quotation_reader)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.adv_cost_vs_actual("quote_1", None))
    assert exc.value.status_code == 403
