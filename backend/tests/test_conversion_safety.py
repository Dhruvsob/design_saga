"""Concurrency coverage for CRM-to-project conversion."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import server


class _LeadCollection:
    def __init__(self):
        self.row = {"id": "lead_1", "name": "Client", "stage": "Qualified"}
        self.lock = asyncio.Lock()

    async def find_one_and_update(self, _query, update, **_kwargs):
        async with self.lock:
            if self.row.get("converted_project_id") or self.row.get("conversion_claim"):
                return None
            self.row.update(update["$set"])
            return dict(self.row)

    async def find_one(self, _query, *_args, **_kwargs):
        return dict(self.row)

    async def update_one(self, query, update):
        if query.get("conversion_claim") != self.row.get("conversion_claim"):
            return SimpleNamespace(matched_count=0)
        self.row.update(update.get("$set", {}))
        for key in update.get("$unset", {}):
            self.row.pop(key, None)
        return SimpleNamespace(matched_count=1)


class _Rows:
    def __init__(self):
        self.rows = []

    async def insert_one(self, row):
        self.rows.append(dict(row))

    async def delete_one(self, query):
        self.rows = [row for row in self.rows if row.get("id") != query.get("id")]

    async def delete_many(self, query):
        self.rows = [row for row in self.rows if any(row.get(k) != v for k, v in query.items())]

    async def find_one(self, query, *_args, **_kwargs):
        return next((dict(row) for row in self.rows
                     if all(row.get(k) == v for k, v in query.items())), None)


class _QuotationCollection(_LeadCollection):
    def __init__(self):
        super().__init__()
        self.row = {
            "id": "quote_1", "status": "approved", "project_title": "Residence",
            "client_name": "Client", "cost": {"grand_total": 1000},
            "boq": [{"category": "Joinery"}],
            "timeline": [{"phase": "Design", "start_offset_weeks": 0,
                          "duration_weeks": 1}],
        }


class _LifecycleCollection:
    def __init__(self, row):
        self.row = dict(row)
        self.lock = asyncio.Lock()
        self.read_barrier = None
        self.reads_at_barrier = 0

    def _matches(self, query):
        return all(self.row.get(key) == value for key, value in query.items())

    async def find_one(self, query, *_args, **_kwargs):
        result = dict(self.row) if self._matches(query) else None
        if self.read_barrier is not None and self.reads_at_barrier < 2:
            self.reads_at_barrier += 1
            if self.reads_at_barrier == 2:
                self.read_barrier.set()
            await self.read_barrier.wait()
        return result

    def block_next_two_reads(self):
        self.read_barrier = asyncio.Event()
        self.reads_at_barrier = 0

    async def update_one(self, query, update):
        async with self.lock:
            if not self._matches(query):
                return SimpleNamespace(matched_count=0)
            self.row.update(update.get("$set", {}))
            for key, value in update.get("$push", {}).items():
                self.row.setdefault(key, []).append(value)
            return SimpleNamespace(matched_count=1)

    async def replace_one(self, query, replacement):
        async with self.lock:
            if not self._matches(query):
                return SimpleNamespace(matched_count=0)
            self.row = dict(replacement)
            return SimpleNamespace(matched_count=1)

    async def delete_one(self, query):
        async with self.lock:
            if not self._matches(query):
                return SimpleNamespace(deleted_count=0)
            self.row = {}
            return SimpleNamespace(deleted_count=1)


def _request(method="POST", path="/api/quotations-adv/quote_1"):
    return Request({
        "type": "http", "method": method, "path": path,
        "headers": [], "client": ("203.0.113.10", 1234),
        "scheme": "https", "server": ("gamaa.in", 443),
    })


def _allow_quotation_user(monkeypatch, collection):
    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "name": "Admin", "org_id": "org_a"}

    monkeypatch.setattr(server, "sdb", SimpleNamespace(quotations_adv=collection))
    monkeypatch.setattr(server, "require_user", user)
    monkeypatch.setattr(server, "_require_perm", lambda *_args: None)
    monkeypatch.setattr(server, "has_permission", lambda *_args: True)


def test_concurrent_lead_conversion_has_exactly_one_winner(monkeypatch):
    leads = _LeadCollection()
    clients = _Rows()
    projects = _Rows()
    monkeypatch.setattr(
        server, "sdb", SimpleNamespace(leads=leads, clients=clients, projects=projects),
    )

    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "name": "Admin", "org_id": "org_a"}

    async def no_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(server, "require_user", user)
    monkeypatch.setattr(server, "has_permission", lambda *_args: True)
    monkeypatch.setattr(server, "audit_log", no_audit)
    request = Request({
        "type": "http", "method": "POST", "path": "/api/leads/lead_1/convert",
        "headers": [], "client": ("203.0.113.10", 1234),
        "scheme": "https", "server": ("gamaa.in", 443),
    })

    async def convert():
        return await server.convert_lead_to_project("lead_1", request)

    async def race():
        return await asyncio.gather(convert(), convert(), return_exceptions=True)

    results = asyncio.run(race())
    winners = [result for result in results if isinstance(result, dict)]
    losers = [result for result in results if isinstance(result, HTTPException)]

    assert len(winners) == 1
    assert len(losers) == 1 and losers[0].status_code == 409
    assert len(clients.rows) == 1
    assert len(projects.rows) == 1
    assert leads.row["converted_project_id"] == projects.rows[0]["id"]
    assert "conversion_claim" not in leads.row


def test_concurrent_quotation_conversion_has_one_project_and_task_set(monkeypatch):
    quotations = _QuotationCollection()
    clients, projects, tasks = _Rows(), _Rows(), _Rows()
    monkeypatch.setattr(server, "sdb", SimpleNamespace(
        quotations_adv=quotations, clients=clients, projects=projects, tasks=tasks,
    ))

    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "name": "Admin", "org_id": "org_a"}

    monkeypatch.setattr(server, "require_user", user)
    monkeypatch.setattr(server, "_require_perm", lambda *_args: None)
    monkeypatch.setattr(server, "has_permission", lambda *_args: True)
    request = Request({
        "type": "http", "method": "POST",
        "path": "/api/quotations-adv/quote_1/convert-to-project",
        "headers": [], "client": ("203.0.113.10", 1234),
        "scheme": "https", "server": ("gamaa.in", 443),
    })

    async def race():
        async def convert():
            return await server.adv_convert("quote_1", request)
        return await asyncio.gather(convert(), convert(), return_exceptions=True)

    results = asyncio.run(race())
    winners = [result for result in results if isinstance(result, dict)]
    losers = [result for result in results if isinstance(result, HTTPException)]

    assert len(winners) == 1
    assert len(losers) == 1 and losers[0].status_code == 409
    assert len(clients.rows) == 1
    assert len(projects.rows) == 1
    assert len(tasks.rows) == 2
    assert {task["project_id"] for task in tasks.rows} == {projects.rows[0]["id"]}
    assert quotations.row["status"] == "converted"
    assert "conversion_claim" not in quotations.row


def test_quotation_conversion_requires_project_and_task_create_permissions(monkeypatch):
    quotations = _QuotationCollection()
    clients, projects, tasks = _Rows(), _Rows(), _Rows()
    monkeypatch.setattr(server, "sdb", SimpleNamespace(
        quotations_adv=quotations, clients=clients, projects=projects, tasks=tasks,
    ))

    async def user(*_args, **_kwargs):
        return {
            "user_id": "designer", "name": "Designer", "org_id": "org_a",
            "role": "Designer", "permissions": ["quotations.update"],
        }

    monkeypatch.setattr(server, "require_user", user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.adv_convert("quote_1", _request()))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing permission: projects.create"
    assert not quotations.row.get("conversion_claim")
    assert clients.rows == []
    assert projects.rows == []
    assert tasks.rows == []


def test_quotation_conversion_requires_client_create_only_for_new_client(monkeypatch):
    quotations = _QuotationCollection()
    clients, projects, tasks = _Rows(), _Rows(), _Rows()
    monkeypatch.setattr(server, "sdb", SimpleNamespace(
        quotations_adv=quotations, clients=clients, projects=projects, tasks=tasks,
    ))

    async def user(*_args, **_kwargs):
        return {
            "user_id": "project_user", "name": "Project User", "org_id": "org_a",
            "permissions": ["quotations.update", "projects.create", "tasks.create"],
        }

    monkeypatch.setattr(server, "require_user", user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.adv_convert("quote_1", _request()))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing permission: clients.create"
    assert not quotations.row.get("conversion_claim")
    assert "conversion_claimed_at" not in quotations.row
    assert clients.rows == []
    assert projects.rows == []
    assert tasks.rows == []


def test_converted_quotation_remains_readable_but_cannot_be_mutated(monkeypatch):
    quotations = _LifecycleCollection({
        "id": "quote_1", "status": "converted", "converted_project_id": "project_1",
        "project_title": "Residence", "updated_at": "2026-10-18T00:00:00Z",
    })
    _allow_quotation_user(monkeypatch, quotations)

    async def check():
        doc = await server.adv_get("quote_1", _request("GET"))
        assert doc["converted_project_id"] == "project_1"

        mutations = [
            server.adv_update(
                "quote_1", server.QuotationUpdate(project_title="Changed"), _request("PUT")
            ),
            server.adv_delete("quote_1", _request("DELETE")),
            server.adv_status(
                "quote_1", server.StatusUpdate(status="sent"), _request()
            ),
            server.adv_approval(
                "quote_1",
                server.ApprovalUpdate(actor="internal", decision="approved"),
                _request(),
            ),
            server.adv_new_version("quote_1", _request()),
            server.adv_change_order(
                "quote_1", server.ChangeOrderIn(description="Extra work"), _request()
            ),
        ]
        for mutation in mutations:
            try:
                await mutation
                raise AssertionError("Converted quotation mutation unexpectedly succeeded")
            except HTTPException as exc:
                assert exc.status_code == 409

    asyncio.run(check())
    assert quotations.row["project_title"] == "Residence"


def test_internal_endpoint_rejects_forged_client_approval(monkeypatch):
    quotations = _LifecycleCollection({
        "id": "quote_1", "status": "sent", "updated_at": "2026-10-18T00:00:00Z",
    })
    _allow_quotation_user(monkeypatch, quotations)

    async def check():
        try:
            await server.adv_approval(
                "quote_1",
                server.ApprovalUpdate(actor="client", decision="approved"),
                _request(),
            )
            raise AssertionError("Forged client approval unexpectedly succeeded")
        except HTTPException as exc:
            assert exc.status_code == 403

    asyncio.run(check())
    assert "approval" not in quotations.row


def test_status_cannot_directly_convert_and_concurrent_updates_have_one_winner(monkeypatch):
    quotations = _LifecycleCollection({
        "id": "quote_1", "status": "sent", "updated_at": "2026-10-18T00:00:00Z",
    })
    _allow_quotation_user(monkeypatch, quotations)

    async def check():
        try:
            await server.adv_status(
                "quote_1", server.StatusUpdate(status="converted"), _request()
            )
            raise AssertionError("Direct conversion status unexpectedly succeeded")
        except HTTPException as exc:
            assert exc.status_code == 409

        quotations.block_next_two_reads()
        results = await asyncio.gather(
            server.adv_status(
                "quote_1", server.StatusUpdate(status="approved"), _request()
            ),
            server.adv_status(
                "quote_1", server.StatusUpdate(status="rejected"), _request()
            ),
            return_exceptions=True,
        )
        winners = [result for result in results if isinstance(result, dict)]
        losers = [result for result in results if isinstance(result, HTTPException)]
        assert len(winners) == 1
        assert len(losers) == 1 and losers[0].status_code == 409

    asyncio.run(check())
    assert quotations.row["status"] in {"approved", "rejected"}
