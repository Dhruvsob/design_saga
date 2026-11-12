"""P2.8 task dependencies, rippling dates and baselines."""
import asyncio
import copy
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.scheduling as sch
import routes.timeline as tl


def T(tid, start=None, due=None, deps=None, status="todo"):
    return {"id": tid, "title": tid.upper(), "start_date": start, "due_date": due,
            "depends_on": deps or [], "status": status}


def test_span_and_cycles():
    assert sch.span(T("a", due="2026-11-10")) == (sch.parse("2026-11-10"), sch.parse("2026-11-10"))
    tasks = {"a": T("a"), "b": T("b", deps=["a"]), "c": T("c", deps=["b"])}
    assert sch.creates_cycle(tasks, "a", ["c"])            # a -> b -> c -> a
    assert sch.creates_cycle(tasks, "a", ["a"])            # waits for itself
    assert not sch.creates_cycle(tasks, "c", ["a", "b"])


def test_finish_moving_later_ripples_down_the_chain_keeping_lengths():
    tasks = {"a": T("a", "2026-11-02", "2026-11-10"),
             "b": T("b", "2026-11-11", "2026-11-13", ["a"]),
             "c": T("c", "2026-11-16", "2026-11-20", ["b"]),
             "d": T("d", "2026-11-11", "2026-11-12", ["a"], status="done")}
    tasks["a"]["due_date"] = "2026-11-14"                 # a slips four days
    moved = sch.reschedule(tasks, ["a"])
    assert moved["b"] == {"start_date": "2026-11-15", "due_date": "2026-11-17"}
    assert moved["c"] == {"start_date": "2026-11-18", "due_date": "2026-11-22"}
    assert "d" not in moved                               # finished tasks never move


def test_successors_are_not_pulled_earlier_and_wait_for_the_latest_predecessor():
    tasks = {"a": T("a", "2026-11-02", "2026-11-05"), "x": T("x", "2026-11-02", "2026-11-09"),
             "b": T("b", "2026-11-12", "2026-11-12", ["a", "x"])}
    assert sch.reschedule(tasks, ["a"]) == {}             # a finishing earlier changes nothing
    tasks["x"]["due_date"] = "2026-11-12"
    assert sch.reschedule(tasks, ["x"])["b"] == {"start_date": "2026-11-13", "due_date": "2026-11-13"}


def test_baseline_variance():
    t = {**T("a", "2026-11-02", "2026-11-14"), "baseline": {"due_date": "2026-11-10"}}
    assert sch.baseline_variance(t) == 4
    assert sch.baseline_variance(T("a", due="2026-11-14")) is None


# ---------------------------------------------------------------- endpoints
class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, _n=None):
        return [copy.deepcopy(r) for r in self.rows]


class _Coll:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, q=None, _p=None):
        q = q or {}
        return _Cursor([r for r in self.rows if all(r.get(k) == v for k, v in q.items() if not k.startswith("$"))])

    async def find_one(self, q, _p=None):
        return next((copy.deepcopy(r) for r in self.rows if all(r.get(k) == v for k, v in q.items())), None)

    async def update_one(self, q, u):
        for r in self.rows:
            if all(r.get(k) == v for k, v in q.items()):
                r.update(u.get("$set", {}))
                for k, v in (u.get("$push") or {}).items():
                    r.setdefault(k, []).append(v)


PM = {"user_id": "u_pm", "org_id": "org_a", "role": "ProjectManager", "name": "Ravi"}


@pytest.fixture
def db(monkeypatch):
    rows = [{**T("a", "2026-11-02", "2026-11-10"), "project_id": "p1"},
            {**T("b", "2026-11-11", "2026-11-13", ["a"]), "project_id": "p1"},
            {**T("c", None, "2026-11-20"), "project_id": "p1"},
            {**T("z", None, None), "project_id": "p1"}]
    fake = SimpleNamespace(tasks=_Coll(rows), projects=_Coll([{"id": "p1", "name": "Villa"}]),
                           project_phases=_Coll([]))
    monkeypatch.setattr(tl, "sdb", fake)

    async def user(*_a, **_k):
        return PM

    async def visible_task(_u, task_id, *_a, **_k):
        t = await fake.tasks.find_one({"id": task_id})
        if not t:
            raise HTTPException(404, "Task not found")
        return t

    async def visible_project(_u, project_id, *_a, **_k):
        return await fake.projects.find_one({"id": project_id})

    async def no_filter(_u):
        return {}

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(tl, "require_user", user)
    monkeypatch.setattr(tl, "get_visible_task", visible_task)
    monkeypatch.setattr(tl, "get_visible_project", visible_project)
    monkeypatch.setattr(tl, "task_visibility_query", no_filter)
    monkeypatch.setattr(tl, "audit", noop)
    return fake


def _row(db, tid):
    return next(r for r in db.tasks.rows if r["id"] == tid)


def test_schedule_edit_ripples_and_refuses_loops(db):
    out = asyncio.run(tl.set_schedule("a", tl.ScheduleIn(start_date="2026-11-02", due_date="2026-11-12"), request=None))
    assert [m["id"] for m in out["moved"]] == ["b"]
    assert (_row(db, "b")["start_date"], _row(db, "b")["due_date"]) == ("2026-11-13", "2026-11-15")
    assert "because \"A\" changed" in _row(db, "b")["timeline"][-1]["details"]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tl.set_schedule("a", tl.ScheduleIn(start_date="2026-11-02", due_date="2026-11-12",
                                                       depends_on=["b"]), request=None))
    assert "loop" in exc.value.detail
    with pytest.raises(HTTPException):
        asyncio.run(tl.set_schedule("a", tl.ScheduleIn(start_date="2026-11-12", due_date="2026-11-02"), request=None))


def test_adding_a_predecessor_moves_the_task_itself_if_too_early(db):
    out = asyncio.run(tl.set_schedule("c", tl.ScheduleIn(start_date="2026-11-12", due_date="2026-11-14",
                                                         depends_on=["b"]), request=None))
    assert out["moved_self"] is True
    assert (_row(db, "c")["start_date"], _row(db, "c")["due_date"]) == ("2026-11-14", "2026-11-16")


def test_baseline_then_timeline_shows_slip(db):
    asyncio.run(tl.save_baseline("p1", request=None))
    assert _row(db, "a")["baseline"]["due_date"] == "2026-11-10" and "baseline" not in _row(db, "z")
    asyncio.run(tl.set_schedule("a", tl.ScheduleIn(start_date="2026-11-02", due_date="2026-11-13"), request=None))
    view = asyncio.run(tl.project_timeline("p1", request=None))
    by_id = {t["id"]: t for t in view["tasks"]}
    assert by_id["a"]["variance_days"] == 3 and by_id["b"]["variance_days"] == 3
    assert view["summary"] == {"dated": 3, "undated": 1, "behind_baseline": 2, "worst_slip_days": 3}
    assert view["undated"] == [{"id": "z", "title": "Z"}]


def test_schedule_changes_need_project_update_and_task_edits_ripple():
    assert '"projects.update"' in inspect.getsource(tl.set_schedule)
    assert '"projects.update"' in inspect.getsource(tl.save_baseline)
    import routes.tasks as tasks
    assert "ripple_after_edit" in inspect.getsource(tasks.update_task)
