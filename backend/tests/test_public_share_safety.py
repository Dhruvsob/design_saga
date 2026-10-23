"""Regression coverage for tenant-owned public share links."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import server


TOKEN = "0123456789ab"


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, limit):
        return [dict(row) for row in self.rows[:limit]]


class _Collection:
    def __init__(self, rows=None, find_one=None):
        self.rows = rows or []
        self._find_one = find_one
        self.find_queries = []
        self.find_one_queries = []
        self.inserted = []

    def find(self, query, *_args, **_kwargs):
        self.find_queries.append(query)
        return _Cursor(self.rows)

    async def find_one(self, query, *_args, **_kwargs):
        self.find_one_queries.append(query)
        if self._find_one:
            row = self._find_one(query)
            return dict(row) if row else None
        return dict(self.rows[0]) if self.rows else None

    async def insert_one(self, row):
        self.inserted.append(dict(row))
        return SimpleNamespace(inserted_id=row.get("id"))


def _active_db(**children):
    project = _Collection([{
        "id": "shared_project", "org_id": "org_a", "share_token": TOKEN,
        "name": "Shared Project", "stage": "Requirement",
    }])
    organizations = _Collection(find_one=lambda query: {
        "org_id": "org_a", "name": "Tenant A",
    } if query.get("org_id") == "org_a" else None)
    return SimpleNamespace(projects=project, organizations=organizations, **children)


def test_public_share_rejects_non_application_token_without_database_lookup(monkeypatch):
    projects = _Collection([])
    monkeypatch.setattr(server, "db", SimpleNamespace(projects=projects))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._public_project_by_token("not-a-valid-token"))

    assert exc.value.status_code == 404
    assert projects.find_one_queries == []


def test_public_share_rejects_suspended_tenant(monkeypatch):
    project = _Collection([{
        "id": "shared_project", "org_id": "org_a", "share_token": TOKEN,
    }])
    organizations = _Collection([])
    monkeypatch.setattr(
        server, "db", SimpleNamespace(projects=project, organizations=organizations),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server._public_project_by_token(TOKEN))

    assert exc.value.status_code == 404
    assert organizations.find_one_queries == [{
        "org_id": "org_a", "is_active": {"$ne": False},
        "is_suspended": {"$ne": True},
    }]


def test_portal_child_queries_are_bound_to_token_owners_tenant(monkeypatch):
    children = {
        name: _Collection([])
        for name in ("tasks", "files", "invoices", "payment_milestones")
    }
    monkeypatch.setattr(server, "db", _active_db(**children))

    result = asyncio.run(server.portal_view(TOKEN))

    assert result["project"]["id"] == "shared_project"
    owned = {"project_id": "shared_project", "org_id": "org_a"}
    assert children["tasks"].find_queries == [owned]
    assert children["payment_milestones"].find_queries == [owned]
    assert children["files"].find_queries == [{**owned, "client_visible": True}]
    assert children["invoices"].find_queries == [{
        **owned, "status": {"$in": ["sent", "paid", "overdue"]},
    }]


def test_portal_milestones_expose_only_client_safe_fields(monkeypatch):
    children = {
        "tasks": _Collection([]),
        "files": _Collection([]),
        "invoices": _Collection([]),
        "payment_milestones": _Collection([{
            "id": "ms_1", "org_id": "org_a", "project_id": "shared_project",
            "name": "Design approval", "amount": 10000, "percent": 20,
            "due_date": "2026-10-31", "status": "pending",
            "notes": "Internal collection note", "created_by": "user_1",
        }]),
    }
    monkeypatch.setattr(server, "db", _active_db(**children))

    result = asyncio.run(server.portal_view(TOKEN))

    assert result["milestones"] == [{
        "id": "ms_1", "name": "Design approval", "amount": 10000,
        "percent": 20, "due_date": "2026-10-31", "status": "pending",
    }]


def test_shared_invoice_pdf_uses_project_and_tenant_in_same_lookup(monkeypatch):
    invoice = {
        "id": "invoice_collision", "project_id": "shared_project",
        "org_id": "org_a", "number": "INV-1", "status": "sent",
    }
    invoices = _Collection(find_one=lambda query: invoice if query == {
        "id": "invoice_collision", "project_id": "shared_project", "org_id": "org_a",
        "status": {"$in": ["sent", "paid", "overdue"]},
    } else None)
    fake_db = _active_db(invoices=invoices)
    monkeypatch.setattr(server, "db", fake_db)

    async def anonymous(*_args, **_kwargs):
        return None

    monkeypatch.setattr(server, "get_current_user", anonymous)
    monkeypatch.setattr(server, "generate_invoice_pdf", lambda *_args: b"%PDF-test")
    request = Request({
        "type": "http", "method": "GET", "path": "/api/invoices/invoice_collision/pdf",
        "headers": [], "client": ("203.0.113.10", 1234),
        "scheme": "https", "server": ("gamaa.in", 443),
    })

    response = asyncio.run(server.invoice_pdf(
        "invoice_collision", request, token=TOKEN,
    ))

    assert response.media_type == "application/pdf"
    assert invoices.find_one_queries == [{
        "id": "invoice_collision", "project_id": "shared_project", "org_id": "org_a",
        "status": {"$in": ["sent", "paid", "overdue"]},
    }]


def test_new_file_links_are_private_by_default():
    payload = server.FileIn(
        project_id="project_1", name="Internal drawing",
        url="https://files.example.test/drawing.pdf",
    )

    assert payload.client_visible is False
