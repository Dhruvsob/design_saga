"""Concurrency coverage for CRM-to-project conversion."""
import asyncio
from types import SimpleNamespace

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
