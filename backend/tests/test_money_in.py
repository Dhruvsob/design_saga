"""Invoices are documents, reminders ask for money, only Record Payment books it."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import server
import routes.accounting as accounting
from routes import money_in


def test_whatsapp_numbers_get_india_code_and_digits_only():
    assert money_in.whatsapp_number("98250 12345") == "919825012345"
    assert money_in.whatsapp_number("+91 98250-12345") == "919825012345"
    assert money_in.whatsapp_number("098250 12345") == "919825012345"
    assert money_in.whatsapp_number("0091 98250 12345") == "919825012345"
    assert money_in.whatsapp_number("12345") is None
    assert money_in.whatsapp_number(None) is None


def test_indian_amounts_and_reminder_message():
    assert money_in._inr(590000) == "5,90,000"
    assert money_in._inr(10000.5) == "10,000.50"
    reminder = {"number": "PR-0001", "party_name": "Krunal Soni", "project_name": "Cloud-9",
                "amount_due": 590000, "due_by": "2026-11-30", "party_phone": "9825012345"}
    org = {"name": "Design Saga", "bank_details": {"upi": "designsaga@hdfc", "ifsc": "HDFC0001"}}
    text = money_in.reminder_message(reminder, org)
    assert "Rs. 5,90,000" in text and "30/11/2026" in text and "designsaga@hdfc" in text
    assert "already paid" in text
    url = money_in.whatsapp_url(reminder, org)
    assert url.startswith("https://wa.me/919825012345?text=")


def test_reminder_pdf_is_a_pdf_and_says_it_is_not_a_receipt():
    reminder = {"number": "PR-0007", "party_name": "Krunal Soni", "party_phone": "9825012345",
                "project_name": "Cloud-9", "title": "Invoice INV-1004", "reference": "INV-1004",
                "total_amount": 600000, "received_before": 10000, "amount_due": 590000,
                "due_by": "2026-11-30", "created_at": "2026-11-07T10:00:00+00:00",
                "message": "Kindly clear before handover."}
    pdf = money_in.generate_reminder_pdf(reminder, {"name": "Design Saga", "phone": "98250 00000",
                                                     "bank_details": {"bank": "HDFC", "account": "123"}})
    assert pdf[:4] == b"%PDF" and len(pdf) > 1500


def test_cash_basis_sending_an_invoice_posts_nothing(monkeypatch):
    row = {"id": "inv_1", "number": "INV-1", "doc_type": "invoice", "status": "draft",
           "subtotal": 600000, "tax": 0, "total": 600000}

    class Invoices:
        async def find_one(self, *_a, **_k):
            return dict(row)

        async def update_one(self, _q, update):
            row.update(update.get("$set", {}))

    calls = []

    async def post_accrual(*_a):
        calls.append("accrual")

    async def noop(*_a, **_k):
        return None

    async def cash():
        return "cash"

    monkeypatch.setattr(server, "sdb", SimpleNamespace(invoices=Invoices(), journal_entries=None))
    monkeypatch.setattr(server, "has_permission", lambda *_a: True)
    monkeypatch.setattr(server, "audit_log", noop)
    monkeypatch.setattr(accounting, "post_invoice_accrual_je", post_accrual)
    monkeypatch.setattr(accounting, "reverse_invoice_accrual_je", noop)
    monkeypatch.setattr(accounting, "org_accounting_basis", cash)
    sent = asyncio.run(server._update_invoice_status_locked(
        {"user_id": "admin"}, "inv_1", server.InvoiceStatusUpdate(status="sent")))
    assert sent["status"] == "sent" and calls == []
    with pytest.raises(HTTPException) as err:
        asyncio.run(server._update_invoice_status_locked(
            {"user_id": "admin"}, "inv_1", server.InvoiceStatusUpdate(status="paid")))
    assert err.value.status_code == 409


def test_project_money_keeps_value_billing_and_cash_apart():
    money = server._project_money(
        {"budget": 600000},
        [{"total": 600000, "paid_amount": 10000, "status": "partially_paid"},
         {"total": 5000, "status": "draft"}],
        [{"amount": 60000}, {"amount": 540000}],
        received=10000,
    )
    assert money == {"project_value": 600000, "scheduled": 600000, "invoiced": 600000,
                     "billed_unpaid": 590000, "received": 10000, "still_to_receive": 590000}


def test_marking_a_milestone_paid_is_refused(monkeypatch):
    class Milestones:
        async def find_one(self, *_a, **_k):
            return {"id": "ms_1", "amount": 50000, "status": "pending", "project_id": "p1"}

    async def user(*_a, **_k):
        return {"user_id": "admin"}

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(payment_milestones=Milestones()))
    monkeypatch.setattr(accounting, "require_user", user)
    monkeypatch.setattr(accounting, "has_permission", lambda *_a: True)
    with pytest.raises(HTTPException) as err:
        asyncio.run(accounting.update_milestone(
            "ms_1", accounting.MilestoneUpdate(status="paid"), None))
    assert err.value.status_code == 409 and "Record Payment" in err.value.detail
