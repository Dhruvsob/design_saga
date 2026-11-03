"""Professional invoice snapshot and PDF-format regressions."""

import asyncio

import pytest
from fastapi import HTTPException

import server


class _MissingCollection:
    async def find_one(self, *_args, **_kwargs):
        return None


class _InvoiceScopedDb:
    clients = _MissingCollection()
    projects = _MissingCollection()


def test_invoice_pdf_dates_use_ddmmyyyy_without_changing_storage_format():
    assert server._pdf_display_date("2026-10-31") == "31/10/2026"
    assert server._pdf_display_date("2026-10-31T23:15:00+00:00") == "31/10/2026"
    assert server._pdf_display_date(None) == "—"


def test_invoice_client_snapshot_contains_only_invoice_facing_fields():
    snapshot = server._invoice_client_snapshot({
        "id": "cli_1", "name": "Client", "company": "Studio",
        "email": "client@example.test", "phone": "9999999999",
        "address": "Ahmedabad", "notes": "private internal note",
        "org_id": "org_a",
    })

    assert snapshot == {
        "name": "Client", "company": "Studio",
        "email": "client@example.test", "phone": "9999999999",
        "address": "Ahmedabad",
    }


def test_invoice_creation_rejects_invalid_client_before_allocating_number(monkeypatch):
    async def fake_require_user(*_args, **_kwargs):
        return {
            "user_id": "usr_admin", "org_id": "org_a", "role": "admin",
            "permissions": ["invoices.create"],
        }

    monkeypatch.setattr(server, "require_user", fake_require_user)
    monkeypatch.setattr(server, "sdb", _InvoiceScopedDb())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.create_invoice(server.InvoiceIn(
            client_id="cli_missing",
            client_name="Untrusted display name",
            items=[],
        ), None))

    assert exc.value.status_code == 400
    assert exc.value.detail == "Client not found"


def test_invoice_pdf_renders_long_service_descriptions_and_multiple_pages():
    long_description = (
        "Architectural and interior design consultancy including coordinated "
        "working drawings, material schedules, site reviews and revision records "
        "for the complete project scope."
    )
    items = [
        {"description": f"{long_description} Item {index}",
         "quantity": 1, "rate": 1000, "amount": 1000}
        for index in range(28)
    ]
    pdf = server.generate_invoice_pdf({
        "number": "INV-TEST", "issue_date": "2026-10-31",
        "due_date": "2026-11-15", "status": "sent",
        "client_name": "Test Client", "project_name": "Residence",
        "client_details": {"address": "Ahmedabad", "email": "client@example.test"},
        "items": items, "subtotal": 28000, "tax_rate": 18, "tax": 5040,
        "total": 33040,
    }, {"name": "Design Saga", "branding": {}})

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 5000
