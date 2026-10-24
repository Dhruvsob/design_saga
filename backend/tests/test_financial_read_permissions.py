"""Regression coverage for financial read authorization helpers."""

import asyncio
import math
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import server
from server import _can_read_invoices, _employee_for_user, _ensure_invoice_read
from routes.vendors import _vendor_for_user


class _Cursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def sort(self, *_args):
        return self

    async def to_list(self, limit):
        return self.rows[:limit]


class _Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.find_calls = 0

    def find(self, *_args, **_kwargs):
        self.find_calls += 1
        return _Cursor(self.rows)


def test_invoice_models_reject_invalid_status_and_non_finite_money():
    with pytest.raises(ValidationError):
        server.InvoiceIn(status="unexpected")
    with pytest.raises(ValidationError):
        server.InvoiceIn(items=[{"description": "Design", "quantity": 1,
                                 "rate": math.inf}])
    with pytest.raises(ValidationError):
        server.InvoiceIn(items=[{"description": "Design", "quantity": 0,
                                 "rate": 1000}])
    with pytest.raises(ValidationError):
        server.InvoiceIn(tax_rate=101)


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


def test_project_detail_separates_invoice_procurement_and_vendor_cost_access(monkeypatch):
    collections = SimpleNamespace(
        tasks=_Collection(), files=_Collection(), employees=_Collection(),
        invoices=_Collection([{"id": "invoice_1", "total": 1000, "status": "sent"}]),
        payment_milestones=_Collection([{"id": "milestone_1", "amount": 500}]),
        purchase_orders=_Collection([{"id": "po_1", "grand_total": 600}]),
        vendor_bills=_Collection([{"id": "bill_1", "total": 400, "status": "received"}]),
    )

    async def visible_project(_user, _project_id):
        return {"id": "project_1", "name": "Residence", "budget": 2000, "team_ids": []}

    monkeypatch.setattr(server, "sdb", collections)
    monkeypatch.setattr(server, "get_visible_project", visible_project)

    async def load(user):
        async def authenticated(*_args, **_kwargs):
            return user

        monkeypatch.setattr(server, "require_user", authenticated)
        return await server.get_project("project_1", None)

    employee = asyncio.run(load({
        "user_id": "employee_1", "permissions": ["projects.read", "purchase_orders.read"],
    }))
    assert employee["purchase_orders"][0]["id"] == "po_1"
    assert employee["invoices"] == []
    assert employee["milestones"] == []
    assert employee["vendor_bills"] == []
    assert "financials" not in employee and "budget" not in employee

    project_manager = asyncio.run(load({
        "user_id": "pm_1",
        "permissions": ["projects.read", "invoices.read", "purchase_orders.read"],
    }))
    assert project_manager["invoices"][0]["id"] == "invoice_1"
    assert project_manager["purchase_orders"][0]["id"] == "po_1"
    assert project_manager["vendor_bills"] == []
    assert "vendor_cost" not in project_manager["financials"]
    assert project_manager["can_view_vendor_costs"] is False

    accountant = asyncio.run(load({
        "user_id": "accountant_1",
        "permissions": ["projects.read", "invoices.read", "purchase_orders.read", "finance.read"],
    }))
    assert accountant["vendor_bills"][0]["id"] == "bill_1"
    assert accountant["financials"]["vendor_cost"] == 400
    assert accountant["can_view_vendor_costs"] is True

    assert collections.invoices.find_calls == 2
    assert collections.payment_milestones.find_calls == 2
    assert collections.purchase_orders.find_calls == 3
    assert collections.vendor_bills.find_calls == 1


def test_invoice_issue_and_draft_transitions_post_and_reverse_accrual(monkeypatch):
    import routes.accounting as accounting

    class Invoices:
        def __init__(self):
            self.row = {
                "id": "inv_1", "number": "INV-1", "doc_type": "invoice",
                "status": "draft", "subtotal": 1000, "tax": 180, "total": 1180,
            }

        async def find_one(self, *_args, **_kwargs):
            return dict(self.row)

        async def update_one(self, _query, update):
            self.row.update(update.get("$set", {}))

    class Journals:
        async def find_one(self, *_args, **_kwargs):
            return None

    invoices = Invoices()
    calls = []

    async def post_accrual(_user, _invoice):
        calls.append("post")
        return {"id": "je_issue"}

    async def reverse_accrual(_user, _invoice):
        calls.append("reverse")
        return {"id": "je_issue_reversal"}

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        server, "sdb", SimpleNamespace(invoices=invoices, journal_entries=Journals()))
    monkeypatch.setattr(server, "has_permission", lambda *_args: True)
    monkeypatch.setattr(server, "audit_log", noop)
    monkeypatch.setattr(accounting, "post_invoice_accrual_je", post_accrual)
    monkeypatch.setattr(accounting, "reverse_invoice_accrual_je", reverse_accrual)

    issued = asyncio.run(server._update_invoice_status_locked(
        {"user_id": "admin"}, "inv_1", server.InvoiceStatusUpdate(status="sent")))
    assert issued["status"] == "sent"
    assert issued["accrual_journal_id"] == "je_issue"

    draft = asyncio.run(server._update_invoice_status_locked(
        {"user_id": "admin"}, "inv_1", server.InvoiceStatusUpdate(status="draft")))
    assert draft["status"] == "draft"
    assert draft["accrual_journal_id"] is None
    assert calls == ["post", "reverse"]
