"""P2.5 capacity heatmap: availability (offs, holidays, leave), planned load
from task estimates, logged hours, and who sees which rows."""
import asyncio
import copy
from datetime import date
from types import SimpleNamespace

import pytest

import core.capacity as cap
import routes.capacity as rc

SUN = {6}
WED = date(2026, 11, 18)          # "today" in these tests (Mon 16 Nov week)


def T(est, start=None, due=None, **kw):
    return {"id": kw.pop("id", "t"), "estimate_hours": est, "start_date": start, "due_date": due, **kw}


# ---------------------------------------------------------------- rules
def test_spread_evenly_over_working_days_across_weeks():
    # Thu 19 .. Tue 24 Nov, Sunday off: Thu Fri Sat | Mon Tue = 5 days of 2 h
    out = cap.spread(T(10, "2026-11-19", "2026-11-24"), WED, SUN, set())
    assert out == {"2026-11-16": pytest.approx(6.0), "2026-11-23": pytest.approx(4.0)}


def test_due_date_only_lands_in_the_due_week_and_skips_holidays():
    out = cap.spread(T(8, due="2026-12-02"), WED, SUN, {"2026-12-01"})   # Mon 30 Nov, Wed 2 Dec; Tue holiday
    assert out == {"2026-11-30": pytest.approx(8.0)}


def test_past_and_overdue_work_moves_to_today_onwards():
    started = cap.spread(T(12, "2026-11-09", "2026-11-21"), WED, SUN, set())   # Wed..Sat left = 4 days
    assert started == {"2026-11-16": pytest.approx(12.0)}
    overdue = cap.spread(T(6, "2026-11-02", "2026-11-10"), WED, SUN, set())
    assert overdue == {"2026-11-16": pytest.approx(6.0)}
    assert cap.spread(T(0, due="2026-11-20"), WED, SUN, set()) == {}
    assert cap.spread(T(5), WED, SUN, set()) == {}             # no due date: unscheduled


def test_week_capacity_removes_offs_holidays_and_leave():
    day = cap.hours_per_day(45, SUN)                            # 6 working days -> 7.5 h
    assert day == 7.5
    capacity, hol, leave = cap.week_capacity(date(2026, 11, 16), day, SUN, {"2026-11-17"},
                                             {"2026-11-19", "2026-11-22"})   # Sunday leave ignored
    assert (capacity, hol, leave) == (30.0, 1, 1)
    assert cap.leave_dates([{"from_date": "2026-11-14", "to_date": "2026-11-17"}],
                           date(2026, 11, 16), date(2026, 11, 22)) == {"2026-11-16", "2026-11-17"}


def test_bands():
    assert [cap.band(x) for x in (None, 0.2, 0.6, 0.9, 1.3)] == ["off", "light", "busy", "full", "over"]


# ---------------------------------------------------------------- endpoint
def _match(doc, q):
    for k, v in (q or {}).items():
        have = doc.get(k)
        if isinstance(v, dict):
            for op, x in v.items():
                if op == "$ne" and have == x:
                    return False
                if op == "$in" and have not in x:
                    return False
                if op == "$lte" and not (have is not None and have <= x):
                    return False
                if op == "$gte" and not (have is not None and have >= x):
                    return False
                if op == "$gt" and not (have is not None and have > x):
                    return False
        elif have != v:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, _n=None):
        return [copy.deepcopy(r) for r in self.rows]

    def __aiter__(self):
        self._it = iter(copy.deepcopy(self.rows))
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, rows=None):
        self.rows = rows or []

    def find(self, q=None, _p=None):
        return _Cursor([r for r in self.rows if _match(r, q)])

    async def find_one(self, q=None, _p=None):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, q)), None)


MANAGER = {"user_id": "u_mgr", "org_id": "org_a", "name": "Meera"}
STAFF = {"user_id": "u_asha", "org_id": "org_a", "name": "Asha"}


@pytest.fixture
def env(monkeypatch):
    fake = SimpleNamespace(
        attendance_policies=_Coll([{"weekly_off_days": [6]}]),
        users=_Coll([{"user_id": "u_asha", "email": "asha@studio.test"}, {"user_id": "u_ravi", "email": "ravi@studio.test"}]),
        employees=_Coll([
            {"id": "emp_asha", "first_name": "Asha", "email": "asha@studio.test", "weekly_hours": 45, "employment_status": "active"},
            {"id": "emp_ravi", "first_name": "Ravi", "user_id": "u_ravi", "weekly_hours": 30, "employment_status": "active"},
            {"id": "emp_old", "first_name": "Old", "employment_status": "terminated"},
        ]),
        leaves=_Coll([{"employee_id": "emp_ravi", "status": "approved", "from_date": "2026-11-23", "to_date": "2026-11-24"},
                      {"employee_id": "emp_asha", "status": "pending", "from_date": "2026-11-23", "to_date": "2026-11-28"}]),
        tasks=_Coll([
            T(40, "2026-11-18", "2026-11-21", id="t1", title="Kitchen GFC", project_id="p1", assignee_id="emp_asha", status="todo"),
            T(12, "2026-11-23", "2026-11-28", id="t2", title="BOQ", project_id="p1", assignees=["u_ravi", "emp_asha"], status="in_progress"),
            T(None, due="2026-11-25", id="t3", title="Site visit", assignee_id="emp_ravi", status="todo"),
            T(6, id="t4", title="Mood board", assignee_id="emp_asha", status="todo"),
            T(9, due="2026-11-27", id="t5", title="Unowned", status="todo"),
            T(30, due="2026-11-20", id="t6", title="Done already", assignee_id="emp_asha", status="done"),
        ]),
        projects=_Coll([{"id": "p1", "name": "Villa Serena"}]),
        time_entries=_Coll([{"user_id": "u_asha", "week": "2026-11-09", "hours": 20},
                            {"user_id": "u_asha", "week": "2026-11-16", "hours": 6},
                            {"user_id": "u_asha", "week": "2026-11-09", "hours": 22.5}]),
    )
    viewer = {"user": MANAGER}

    async def user(*_a, **_k):
        return viewer["user"]

    async def no_filter(_u):
        return {}

    async def identities(u):
        return {"u_asha", "emp_asha"} if u["user_id"] == "u_asha" else {u["user_id"]}

    async def holidays(_year):
        return {"2026-11-27"}       # Friday holiday in the 23 Nov week

    monkeypatch.setattr(rc, "sdb", fake)
    monkeypatch.setattr(rc, "require_user", user)
    monkeypatch.setattr(rc, "task_visibility_query", no_filter)
    monkeypatch.setattr(rc, "user_identity_ids", identities)
    monkeypatch.setattr(rc, "get_holiday_dates", holidays)
    monkeypatch.setattr(rc, "business_today", lambda: WED)
    monkeypatch.setattr(rc, "has_any_permission", lambda u, *p: u["user_id"] == "u_mgr")
    return viewer


def _get(**kw):
    return asyncio.run(rc.team_capacity(request=None, start="2026-11-09", weeks=3, **kw))


def test_manager_sees_team_with_capacity_load_and_tasks(env):
    out = _get()
    assert [w["week"] for w in out["weeks"]] == ["2026-11-09", "2026-11-16", "2026-11-23"]
    assert [w["is_current"] for w in out["weeks"]] == [False, True, False]
    rows = {r["id"]: r for r in out["rows"]}
    assert set(rows) == {"emp_asha", "emp_ravi", "_unassigned"}      # terminated staff left out

    asha = {c["week"]: c for c in rows["emp_asha"]["cells"]}
    assert asha["2026-11-09"]["load"] == 42.5 and asha["2026-11-09"]["band"] == "full"   # logged, past week (94%)
    cur = asha["2026-11-16"]                                     # 6 logged + 40 planned (Wed..Sat)
    assert (cur["logged"], cur["planned"], cur["load"], cur["capacity"]) == (6.0, 40.0, 46.0, 45.0)
    assert cur["band"] == "over" and cur["tasks"][0]["project_name"] == "Villa Serena"
    nxt = asha["2026-11-23"]                                     # half of BOQ; Friday holiday
    assert (nxt["planned"], nxt["capacity"], nxt["holidays"], nxt["leave_days"]) == (6.0, 37.5, 1, 0)

    ravi = {c["week"]: c for c in rows["emp_ravi"]["cells"]}["2026-11-23"]
    assert (ravi["planned"], ravi["leave_days"], ravi["capacity"]) == (6.0, 2, 15.0)   # 30 h/6 days; 2 leave + holiday
    assert rows["emp_ravi"]["unestimated_tasks"] == 1                # Site visit has no estimate
    assert rows["emp_asha"]["unscheduled_hours"] == 6.0              # Mood board has no due date
    assert {c["week"]: c for c in rows["_unassigned"]["cells"]}["2026-11-23"]["planned"] == 9.0
    assert out["rows"][-1]["id"] == "_unassigned"
    total = {t["week"]: t for t in out["totals"]}["2026-11-16"]
    assert total["overbooked"] == 1 and total["capacity"] == 45.0 + 30.0


def test_many_unestimated_open_tasks_do_not_crowd_out_planned_work(env, monkeypatch):
    monkeypatch.setattr(rc, "MAX_TASKS", 3)
    rc.sdb.tasks.rows[:0] = [T(None, due="2027-03-01", id=f"filler{n}", assignee_id="emp_asha", status="todo")
                             for n in range(10)]
    asha = {c["week"]: c for c in {r["id"]: r for r in _get()["rows"]}["emp_asha"]["cells"]}
    assert asha["2026-11-16"]["planned"] == 40.0       # Kitchen GFC still counted


def test_staff_see_only_their_own_row(env):
    env["user"] = STAFF
    out = _get()
    assert out["team_view"] is False
    assert [r["id"] for r in out["rows"]] == ["emp_asha"] and out["rows"][0]["is_me"] is True


def test_task_estimates_are_validated_and_tracked():
    from pydantic import ValidationError
    import inspect
    from models.task import TaskIn, TaskUpdate
    import routes.tasks as tasks
    assert TaskIn(title="x", estimate_hours=7.5).estimate_hours == 7.5
    for bad in (-1, 5000, float("nan")):
        with pytest.raises(ValidationError):
            TaskUpdate(estimate_hours=bad)
    assert '"estimate_hours"' in inspect.getsource(tasks.update_task)
