"""P2.4/P2.5 timesheets: weekly grid, submit/approve, cost snapshot, profitability."""
import asyncio
import copy
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.timesheets as ts


def _match(row, q):
    for k, v in (q or {}).items():
        if k == "$or":
            if not any(_match(row, x) for x in v):
                return False
            continue
        val = row.get(k)
        if isinstance(v, dict):
            if "$in" in v and val not in v["$in"]:
                return False
            if "$nin" in v and val in v["$nin"]:
                return False
            if "$ne" in v and val == v["$ne"]:
                return False
        elif val != v:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    async def to_list(self, _n=None):
        return [copy.deepcopy(r) for r in self.rows]

    def __aiter__(self):
        async def it():
            for r in self.rows:
                yield copy.deepcopy(r)
        return it()


class _Coll:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, q=None, _p=None):
        return _Cursor([r for r in self.rows if _match(r, q)])

    async def find_one(self, q, _p=None):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, q)), None)

    async def insert_many(self, docs):
        self.rows += [dict(d) for d in docs]

    async def delete_many(self, q):
        self.rows = [r for r in self.rows if not _match(r, q)]

    async def update_many(self, q, u):
        for r in self.rows:
            if _match(r, q):
                r.update(u["$set"])

    async def update_one(self, q, u):
        for r in self.rows:
            if _match(r, q):
                r.update(u["$set"])
                return


WEEK = "2026-11-09"          # a Monday
STAFF = {"user_id": "u_staff", "org_id": "org_a", "role": "Designer", "name": "Asha"}
PM = {"user_id": "u_pm", "org_id": "org_a", "role": "ProjectManager", "name": "Ravi"}


@pytest.fixture
def db(monkeypatch):
    fake = SimpleNamespace(
        time_entries=_Coll(),
        projects=_Coll([{"id": "p1", "name": "Villa", "budget": 100000}, {"id": "p2", "name": "Office"}]),
        project_phases=_Coll([{"id": "ph1", "project_id": "p1", "name": "Concept", "order": 0}]),
        users=_Coll([{"user_id": "u_staff", "email": "asha@studio.in", "name": "Asha", "role": "Designer"},
                     {"user_id": "u_pm", "email": "ravi@studio.in", "name": "Ravi", "role": "ProjectManager"}]),
        employees=_Coll([{"id": "e1", "user_id": "u_staff", "first_name": "Asha",
                          "salary": {"gross_monthly": 52000}, "weekly_hours": 48}]),
        invoices=_Coll([{"project_id": "p1", "total": 60000, "status": "sent"},
                        {"project_id": "p1", "total": 999, "status": "draft"}]),
        vendor_bills=_Coll([{"project_id": "p1", "total": 10000, "status": "approved"}]),
        expenses=_Coll([{"project_id": "p1", "total": 2000, "status": "approved"},
                        {"project_id": "p1", "total": 500, "status": "rejected"}]),
    )
    monkeypatch.setattr(ts, "sdb", fake)

    async def visible(_u):
        return {}

    async def get_visible_project(_u, project_id, *_a, **_k):
        p = await fake.projects.find_one({"id": project_id})
        if not p:
            raise HTTPException(404, "Project not found")
        return p

    async def noop(*_a, **_k):
        return 0

    import core.notifications
    monkeypatch.setattr(ts, "project_visibility_query", visible)
    monkeypatch.setattr(ts, "get_visible_project", get_visible_project)
    monkeypatch.setattr(ts, "audit", noop)
    monkeypatch.setattr(core.notifications, "emit", noop)
    return fake


def _as(monkeypatch, user):
    async def req(*_a, **_k):
        return user
    monkeypatch.setattr(ts, "require_user", req)


def _save(entries):
    return asyncio.run(ts.save_week(ts.WeekIn(week=WEEK, entries=[ts.EntryIn(**e) for e in entries]), request=None))


def test_pure_helpers():
    assert ts.week_start(date(2026, 11, 12)) == date(2026, 11, 9)
    assert ts.hourly_cost({"salary": {"gross_monthly": 52000}, "weekly_hours": 48}) == 250.0
    assert ts.hourly_cost({"cost_rate_hourly": 400, "salary": {"gross_monthly": 52000}}) == 400.0
    assert ts.hourly_cost({}) is None
    assert ts.week_status([]) == "empty"
    assert ts.week_status([{"status": "approved"}, {"status": "submitted"}]) == "submitted"
    assert ts.week_status([{"status": "approved"}]) == "approved"


def test_week_is_saved_validated_submitted_and_locked(db, monkeypatch):
    _as(monkeypatch, STAFF)
    out = _save([{"date": "2026-11-09", "project_id": "p1", "phase_id": "ph1", "hours": 3.1},
                 {"date": "2026-11-10", "project_id": "p2", "hours": 2, "billable": False}])
    assert out["total_hours"] == 5.0 and out["entries"][0]["hours"] == 3.0   # quarter hours
    for bad, msg in (([{"date": "2026-11-16", "project_id": "p1", "hours": 1}], "not in the week"),
                     ([{"date": "2026-11-09", "project_id": "p2", "phase_id": "ph1", "hours": 1}], "different project"),
                     ([{"date": "2026-11-09", "project_id": "p1", "hours": 20},
                       {"date": "2026-11-09", "project_id": "p2", "hours": 5}], "More than 24")):
        with pytest.raises(HTTPException) as exc:
            _save(bad)
        assert msg in exc.value.detail
    asyncio.run(ts.submit_week(ts.WeekRef(week=WEEK), request=None))
    assert {r["status"] for r in db.time_entries.rows} == {"submitted"}
    with pytest.raises(HTTPException) as exc:
        _save([{"date": "2026-11-09", "project_id": "p1", "hours": 1}])
    assert exc.value.status_code == 409


def test_approval_snapshots_cost_and_nobody_approves_themselves(db, monkeypatch):
    _as(monkeypatch, STAFF)
    _save([{"date": "2026-11-09", "project_id": "p1", "phase_id": "ph1", "hours": 4}])
    asyncio.run(ts.submit_week(ts.WeekRef(week=WEEK), request=None))
    with pytest.raises(HTTPException):                       # staff cannot approve at all
        asyncio.run(ts.approve_week(ts.DecisionIn(user_id="u_staff", week=WEEK), request=None))
    _as(monkeypatch, PM)
    out = asyncio.run(ts.approve_week(ts.DecisionIn(user_id="u_staff", week=WEEK), request=None))
    assert out["status"] == "approved"
    row = db.time_entries.rows[0]
    assert row["cost_rate"] == 250.0 and row["cost"] == 1000.0 and row["approved_by"] == "u_pm"
    # PM's own week needs someone else
    db.time_entries.rows.append({"id": "x", "user_id": "u_pm", "week": WEEK, "date": WEEK,
                                 "project_id": "p1", "hours": 2, "status": "submitted"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ts.approve_week(ts.DecisionIn(user_id="u_pm", week=WEEK), request=None))
    assert exc.value.status_code == 403


def test_returned_week_can_be_edited_again(db, monkeypatch):
    _as(monkeypatch, STAFF)
    _save([{"date": "2026-11-09", "project_id": "p1", "hours": 4}])
    asyncio.run(ts.submit_week(ts.WeekRef(week=WEEK), request=None))
    _as(monkeypatch, PM)
    asyncio.run(ts.return_week(ts.DecisionIn(user_id="u_staff", week=WEEK, reason="Split by phase"), request=None))
    assert db.time_entries.rows[0]["status"] == "rejected"
    _as(monkeypatch, STAFF)
    assert _save([{"date": "2026-11-09", "project_id": "p1", "phase_id": "ph1", "hours": 4}])["status"] == "draft"


def test_costs_hidden_from_staff_and_profitability_for_finance(db, monkeypatch):
    _as(monkeypatch, STAFF)
    _save([{"date": "2026-11-09", "project_id": "p1", "phase_id": "ph1", "hours": 4},
           {"date": "2026-11-10", "project_id": "p1", "hours": 2, "billable": False}])
    asyncio.run(ts.submit_week(ts.WeekRef(week=WEEK), request=None))
    _as(monkeypatch, PM)
    asyncio.run(ts.approve_week(ts.DecisionIn(user_id="u_staff", week=WEEK), request=None))
    _as(monkeypatch, STAFF)
    t = asyncio.run(ts.project_time("p1", request=None))
    assert t["totals"] == {"hours": 6.0, "billable_hours": 4.0, "approved_hours": 6.0}
    assert "cost" not in t["by_phase"][0] and {r["phase"] for r in t["by_phase"]} == {"Concept", "No phase"}
    with pytest.raises(HTTPException):
        asyncio.run(ts.project_profitability("p1", request=None))
    _as(monkeypatch, {"user_id": "u_acc", "org_id": "org_a", "role": "Accountant"})
    p = asyncio.run(ts.project_profitability("p1", request=None))
    assert p["invoiced"] == 60000 and p["costs"]["vendor_bills"] == 10000 and p["costs"]["expenses"] == 2000
    assert p["costs"]["labour"] == 1500.0 and p["approved_hours"] == 6.0
    assert p["margin_on_invoiced"] == 46500.0 and p["fee_used_pct"] == 13.5
