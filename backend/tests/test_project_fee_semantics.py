"""Project fee structure: what missing / null / zero / a value mean on update.

The edit form (ProjectDetail.saveEdit) sends every fee field, using null for an
empty input and null for "no fee structure". Earlier Codex/Claude changes
disagreed about clearing; these pin the agreed contract:
  * a field not sent       -> unchanged
  * null                    -> cleared (fee fields and the type are clearable)
  * fee type null           -> the whole structure is cleared
  * switching the type      -> the other types' inputs are cleared
  * a chosen type must be complete with positive values (0 is refused)
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import server

BASE = {"id": "p1", "name": "Villa", "fee_structure_type": "percentage_consultancy",
        "fee_project_value": 5000000.0, "fee_percentage": 8.0, "budget": 5000000.0, "client_id": "c1"}


@pytest.fixture
def project(monkeypatch):
    state = {"doc": dict(BASE), "ops": []}

    class Projects:
        async def update_one(self, q, u):
            state["ops"].append(u)
            state["doc"].update(u.get("$set", {}))
            for k in u.get("$unset", {}):
                state["doc"].pop(k, None)
            return SimpleNamespace(matched_count=1)

        async def find_one(self, q, _p=None):
            return dict(state["doc"])

    async def user(*_a, **_k):
        return {"user_id": "u", "org_id": "org_a"}

    async def visible(*_a, **_k):
        return dict(state["doc"])

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(server, "sdb", SimpleNamespace(projects=Projects()))
    monkeypatch.setattr(server, "require_user", user)
    monkeypatch.setattr(server, "has_permission", lambda *_a: True)
    monkeypatch.setattr(server, "get_visible_project", visible)
    monkeypatch.setattr(server, "audit_log", noop)
    monkeypatch.setattr(server, "_rescale_percent_milestones", noop)
    return state


def patch(**fields):
    return asyncio.run(server.update_project("p1", server.ProjectUpdate(**fields), request=None))


def test_field_not_sent_is_left_alone(project):
    out = patch(name="Villa Serena")
    assert (out["fee_percentage"], out["fee_project_value"]) == (8.0, 5000000.0)


def test_switching_type_clears_the_previous_inputs(project):
    out = patch(fee_structure_type="lump_sum", fee_lump_sum_amount=350000)
    assert out["fee_structure_type"] == "lump_sum" and out["fee_lump_sum_amount"] == 350000
    assert "fee_percentage" not in out and "fee_project_value" not in out


def test_null_type_clears_the_whole_structure(project):
    out = patch(fee_structure_type=None, fee_project_value=None, fee_percentage=None,
                fee_lump_sum_amount=None, fee_contract_value=None, fee_rate_per_sqft=None)
    assert not any(k.startswith("fee_") for k in out)
    unset = project["ops"][-1]["$unset"]
    assert "fee_structure_type" in unset and "fee_percentage" in unset
    assert not set(unset) & set(project["ops"][-1]["$set"])          # never set and unset one field


@pytest.mark.parametrize("fields", [
    {"fee_structure_type": "lump_sum"},                                   # amount missing
    {"fee_structure_type": "lump_sum", "fee_lump_sum_amount": 0},         # zero is not a fee
    {"fee_structure_type": "per_sqft", "fee_rate_per_sqft": 120},         # area missing
    {"fee_structure_type": "percentage_consultancy", "fee_percentage": None},   # clearing a required input
])
def test_incomplete_structure_is_refused_with_a_clear_message(project, fields):
    with pytest.raises(HTTPException) as exc:
        patch(**fields)
    assert exc.value.status_code == 400 and exc.value.detail.startswith("Complete the selected fee structure")
    assert project["ops"] == []                                           # nothing written


def test_empty_string_type_is_a_validation_error_not_a_crash():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        server.ProjectUpdate(fee_structure_type="")
