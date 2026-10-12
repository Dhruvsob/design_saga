"""Regression coverage for financial read authorization helpers."""

import pytest
from fastapi import HTTPException

from server import _can_read_invoices, _employee_for_user, _ensure_invoice_read


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
