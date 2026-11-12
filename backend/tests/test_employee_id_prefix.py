"""Workspace login-ID prefixes: Design Saga keeps DS, new studios get their own."""
import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import routes.auth as auth
from core.employee_ids import counter_kind, derive_prefix, normalize_prefix, prefix_for_org
from models.organization import OrgCreateIn, OrgUpdateIn


def test_prefix_rules():
    assert prefix_for_org(None) == "DS"
    assert prefix_for_org({"employee_id_prefix": "ab"}) == "AB"
    assert prefix_for_org({"employee_id_prefix": "A1"}) == "DS"        # invalid → legacy
    assert derive_prefix("Studio Arc Pvt Ltd") == "SA"
    assert derive_prefix("Zenith") == "ZE"
    assert derive_prefix("123") == "ID"
    assert normalize_prefix(" xyz ") == "XYZ" and normalize_prefix("TOOLONG") is None
    assert counter_kind("DS") == "user_employee_id"                       # legacy counter key kept
    assert counter_kind("SA") == "user_employee_id:SA"


def test_models_reject_bad_prefixes():
    base = {"name": "Studio", "admin_email": "a@b.co", "admin_name": "A"}
    assert OrgCreateIn(**base, employee_id_prefix="sa").employee_id_prefix == "sa"
    with pytest.raises(ValidationError):
        OrgCreateIn(**base, employee_id_prefix="S1")
    with pytest.raises(ValidationError):
        OrgUpdateIn(employee_id_prefix="TOOLONG")


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self._it = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Counters:
    def __init__(self):
        self.rows = {}

    async def find_one(self, key):
        return self.rows.get(key["kind"])

    async def insert_one(self, doc):
        self.rows[doc["kind"]] = dict(doc)

    async def find_one_and_update(self, key, update, return_document=None):
        row = self.rows[key["kind"]]
        row["seq"] += update["$inc"]["seq"]
        return row


def _fake_db(prefix, existing):
    async def org_find_one(_q, _p=None):
        return {"employee_id_prefix": prefix} if prefix else {}

    seen = {}

    def users_find(query, _p=None):
        seen["regex"] = query["employee_id"]["$regex"]
        return _Cursor([{"employee_id": e} for e in existing])

    return SimpleNamespace(organizations=SimpleNamespace(find_one=org_find_one),
                           users=SimpleNamespace(find=users_find),
                           counters=_Counters()), seen


def test_next_id_uses_the_workspace_prefix(monkeypatch):
    fake, seen = _fake_db("SA", ["SA0001", "SA0004"])
    monkeypatch.setattr(auth, "db", fake)
    assert asyncio.run(auth._next_employee_id("org_sa")) == "SA0005"
    assert seen["regex"] == r"^SA\d+$"


def test_legacy_workspace_keeps_ds(monkeypatch):
    fake, _ = _fake_db(None, ["DS0012"])
    monkeypatch.setattr(auth, "db", fake)
    assert asyncio.run(auth._next_employee_id("org_default")) == "DS0013"
