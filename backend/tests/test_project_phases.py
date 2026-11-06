"""Project phase templates (PRJ-01): planning maths, summary and access gates."""
import asyncio
from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routes.phases as phases


def test_templates_cover_one_hundred_percent_of_fee():
    for key, tpl in phases.PHASE_TEMPLATES.items():
        assert sum(fee for _, fee, _, _ in tpl["phases"]) == 100, key


def test_phase_dates_are_sequential_without_gaps_or_overlap():
    docs = phases.build_phase_docs("turnkey", "p1", date(2026, 4, 1))
    assert docs[0]["planned_start"] == "2026-04-01"
    for prev, nxt in zip(docs, docs[1:]):
        assert date.fromisoformat(nxt["planned_start"]) == date.fromisoformat(prev["planned_end"]).__add__(
            __import__("datetime").timedelta(days=1))
    assert all(d["status"] == "not_started" and d["deliverables"] for d in docs)
    assert len({d["id"] for d in docs}) == len(docs)


def test_fee_milestones_sum_exactly_to_the_fee():
    pct = [fee for _, fee, _, _ in phases.PHASE_TEMPLATES["consultancy"]["phases"]]
    amounts = phases.fee_milestone_amounts(123456.79, pct)
    assert round(sum(amounts), 2) == 123456.79
    assert all(a > 0 for a in amounts)


def test_summary_reports_progress_current_and_overdue_phases():
    docs = [
        {"name": "A", "status": "done", "planned_end": "2026-01-01", "deliverables": [{"done": True}]},
        {"name": "B", "status": "in_progress", "planned_end": "2000-01-01", "deliverables": [{"done": False}]},
        {"name": "C", "status": "not_started", "planned_end": "2999-01-01", "deliverables": []},
    ]
    s = phases.phase_summary(docs)
    assert s["progress_pct"] == 33 and s["current_phase"] == "B"
    assert s["overdue_phases"] == ["B"]
    assert (s["deliverables_done"], s["deliverables_total"]) == (1, 2)


def test_inputs_are_validated():
    with pytest.raises(ValidationError):
        phases.ApplyTemplateIn(template="unknown")
    with pytest.raises(ValidationError):
        phases.ApplyTemplateIn(template="consultancy", start_date="31/10/2026")
    with pytest.raises(ValidationError):
        phases.PhaseUpdateIn(status="archived")


def _deny(*_args, **_kwargs):
    raise HTTPException(status_code=404, detail="Project not found")


@pytest.mark.parametrize("call", [
    lambda: phases.list_project_phases("p_other", request=None),
    lambda: phases.apply_template("p_other", phases.ApplyTemplateIn(template="consultancy"), request=None),
    lambda: phases.update_phase("p_other", "ph_1", phases.PhaseUpdateIn(status="done"), request=None),
    lambda: phases.delete_phase("p_other", "ph_1", request=None),
])
def test_every_route_resolves_the_project_through_visibility_first(monkeypatch, call):
    async def fake_user(*_a, **_k):
        return {"user_id": "u1", "org_id": "org_a", "role": "Employee"}

    async def deny(*_a, **_k):
        _deny()

    class Exploding:
        def __getattr__(self, _name):
            raise AssertionError("phase data must not be read before the project check")

    monkeypatch.setattr(phases, "require_user", fake_user)
    monkeypatch.setattr(phases, "get_visible_project", deny)
    monkeypatch.setattr(phases, "sdb", Exploding())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(call())
    assert exc.value.status_code == 404


def test_write_routes_require_projects_update(monkeypatch):
    seen = []

    async def fake_user(*_a, **_k):
        return {"user_id": "u1", "org_id": "org_a"}

    async def visible(_user, _pid, permission="projects.read", projection=None):
        seen.append(permission)
        raise HTTPException(status_code=403, detail="Missing permission")

    monkeypatch.setattr(phases, "require_user", fake_user)
    monkeypatch.setattr(phases, "get_visible_project", visible)
    for call in (
        phases.apply_template("p1", phases.ApplyTemplateIn(template="turnkey"), request=None),
        phases.update_phase("p1", "ph", phases.PhaseUpdateIn(status="done"), request=None),
        phases.delete_phase("p1", "ph", request=None),
    ):
        with pytest.raises(HTTPException):
            asyncio.run(call)
    assert seen == ["projects.update"] * 3
