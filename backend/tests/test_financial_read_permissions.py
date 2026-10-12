"""Regression coverage for financial read authorization helpers."""

import pytest
from fastapi import HTTPException

from server import _can_read_invoices, _ensure_invoice_read


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
