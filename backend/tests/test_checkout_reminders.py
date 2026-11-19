"""Missing check-outs: evening reminders and the My day pointer.

Production 2026-11-19: 51 of 100 attendance rows were past days with a
check-in and no check-out; nothing reminded people."""
import asyncio
import copy
from datetime import date, datetime
from types import SimpleNamespace

import pytest

import core.checkout_reminders as cr
import core.notifications as notifications
from core.attendance_engine import IST


def _match(doc, q):
    for k, v in (q or {}).items():
        if k == "$or":
            if not any(_match(doc, alt) for alt in v):
                return False
            continue
        have = doc.get(k)
        if isinstance(v, dict):
            for op, x in v.items():
                if op == "$ne" and have == x:
                    return False
                if op == "$nin" and have in x:
                    return False
                if op == "$in" and have not in x:
                    return False
                if op == "$gte" and not (have is not None and have >= x):
                    return False
                if op == "$lt" and not (have is not None and have < x):
                    return False
        elif have != v:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows = sorted(self.rows, key=lambda r: r.get(key) or "", reverse=direction == -1)
        return self

    async def to_list(self, n=None):
        return copy.deepcopy(self.rows[:n] if n else self.rows)

    def __aiter__(self):
        self._it = iter(copy.deepcopy(self.rows))
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def find(self, q=None, _p=None):
        return _Cursor([r for r in self.rows if _match(r, q)])

    async def find_one(self, q=None, _p=None):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, q)), None)


TODAY = "2026-11-19"


@pytest.fixture
def env(monkeypatch):
    fake = SimpleNamespace(
        organizations=_Coll([{"org_id": "org_a"}, {"org_id": "org_off", "is_suspended": True}]),
        attendance_policies=_Coll([{"org_id": "org_a", "office_end": "19:00"}]),
        attendance=_Coll([
            {"org_id": "org_a", "employee_id": "emp_open", "date": TODAY, "check_in": "2026-11-19T04:35:00+00:00"},
            {"org_id": "org_a", "employee_id": "emp_done", "date": TODAY, "check_in": "2026-11-19T04:30:00+00:00",
             "check_out": "2026-11-19T13:30:00+00:00"},
            {"org_id": "org_a", "employee_id": "emp_late_shift", "date": TODAY, "check_in": "2026-11-19T06:00:00+00:00"},
            {"org_id": "org_a", "employee_id": "emp_no_login", "date": TODAY, "check_in": "2026-11-19T04:00:00+00:00"},
            {"org_id": "org_off", "employee_id": "emp_x", "date": TODAY, "check_in": "2026-11-19T04:00:00+00:00"},
        ]),
        employees=_Coll([
            {"org_id": "org_a", "id": "emp_open", "user_id": "u_open"},
            {"org_id": "org_a", "id": "emp_done", "user_id": "u_done"},
            {"org_id": "org_a", "id": "emp_late_shift", "user_id": "u_late", "shift_end": "22:00"},
            {"org_id": "org_a", "id": "emp_no_login", "email": "nologin@studio.test"},
            {"org_id": "org_off", "id": "emp_x", "user_id": "u_x"},
        ]),
        users=_Coll([]),
    )
    sent = []

    async def emit(user_ids, kind, title, **kw):
        sent.append({"to": user_ids, "kind": kind, "title": title, **kw})
        return 1

    monkeypatch.setattr(cr, "db", fake)
    monkeypatch.setattr(notifications, "emit", emit)
    return sent


def at(hh, mm):
    return datetime(2026, 11, 19, hh, mm, tzinfo=IST)


def test_nothing_before_shift_end_plus_an_hour(env):
    assert asyncio.run(cr.send_checkout_reminders(at(19, 59)))["reminders"] == 0 and env == []


def test_open_check_ins_get_one_reminder_with_the_ist_time(env):
    out = asyncio.run(cr.send_checkout_reminders(at(20, 5)))
    assert [s["to"] for s in env] == [["u_open"]]               # checked-out, later shift, no login, suspended: skipped
    assert env[0]["kind"] == "attendance_pending" and env[0]["link"] == "/attendance"
    assert "10:05" in env[0]["body"]                             # 04:35 UTC shown as IST
    assert env[0]["dedup_key"] == f"checkout-reminder:{TODAY}"   # once per person per day
    assert out == {"open_check_ins": 3, "reminders": 1}          # suspended workspace not scanned


def test_a_later_shift_is_reminded_after_its_own_end(env):
    asyncio.run(cr.send_checkout_reminders(at(23, 5)))
    assert sorted(s["to"][0] for s in env) == ["u_late", "u_open"]


def test_due_rule():
    assert cr.due(None, at(20, 0)) and not cr.due("19:30", at(20, 0)) and cr.due("bad", at(20, 1))


# ---------------------------------------------------------------- My day
def test_my_day_points_at_the_latest_missing_check_out(monkeypatch):
    import routes.tasks as tasks
    fake = SimpleNamespace(
        tasks=_Coll([]),
        employees=_Coll([{"id": "emp_1", "user_id": "u1"}]),
        attendance=_Coll([
            {"employee_id": "emp_1", "date": "2026-11-17", "check_in": "x"},
            {"employee_id": "emp_1", "date": "2026-11-18", "check_in": "x"},
            {"employee_id": "emp_1", "date": "2026-11-16", "check_in": "x", "check_out": "y"},
            {"employee_id": "emp_1", "date": "2026-11-05", "check_in": "x"},            # older than a week
        ]),
        attendance_corrections=_Coll([{"employee_id": "emp_1", "date": "2026-11-18", "status": "pending"}]),
        leaves=_Coll([]),
    )

    async def user(*_a, **_k):
        return {"user_id": "u1", "org_id": "org_a", "permissions": []}

    async def ids(_u):
        return {"u1", "emp_1"}

    import core.access_control as ac
    monkeypatch.setattr(tasks, "sdb", fake)
    monkeypatch.setattr(tasks, "require_user", user)
    monkeypatch.setattr(ac, "user_identity_ids", ids)
    monkeypatch.setattr(tasks, "business_today", lambda: date(2026, 11, 19))
    out = asyncio.run(tasks.my_day(request=None))
    assert out["attendance"]["missing_checkout"] == "2026-11-17"     # 18th already has a correction request
    assert out["attendance"]["missing_checkout_count"] == 1
