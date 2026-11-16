"""One-click employee profile for owners/admins whose login has no employee
record (8 of 9 production Admin logins on 2026-11-16), so attendance, leave
and My day work for them too."""
import asyncio
import copy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import server


class _Coll:
    def __init__(self, rows=None):
        self.rows = [copy.deepcopy(r) for r in rows or []]
        self.inserted = []

    @staticmethod
    def _match(r, q):
        if "$or" in q:
            return any(_Coll._match(r, alt) for alt in q["$or"])
        for k, v in q.items():
            if isinstance(v, dict) and "$in" in v:
                if r.get(k) not in v["$in"]:
                    return False
            elif r.get(k) != v:
                return False
        return True

    async def find_one(self, q, _p=None):
        return next((copy.deepcopy(r) for r in self.rows if self._match(r, q)), None)

    async def insert_one(self, doc):
        self.rows.append(copy.deepcopy(doc))
        self.inserted.append(doc)

    async def update_one(self, q, u):
        for r in self.rows:
            if self._match(r, q):
                r.update(u["$set"])
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


OWNER = {"user_id": "u_owner", "org_id": "org_a", "email": "anita@studio.test", "name": "Anita Mehta Shah",
         "role": "Admin", "employee_id": "DS0001", "permissions": ["*.*", "employees.create"]}


@pytest.fixture
def env(monkeypatch):
    state = SimpleNamespace(user=dict(OWNER), employees=_Coll(), users=_Coll([dict(OWNER)]), audits=[])

    async def current(*_a, **_k):
        return state.user

    async def record(user, action, **kw):
        state.audits.append(action)

    async def next_code(_org):
        return "DS0009"

    monkeypatch.setattr(server, "sdb", SimpleNamespace(employees=state.employees))
    monkeypatch.setattr(server, "db", SimpleNamespace(users=state.users))
    monkeypatch.setattr(server, "require_user", current)
    monkeypatch.setattr(server, "has_permission", lambda u, p: p in u.get("permissions", []))
    monkeypatch.setattr(server, "audit_log", record)
    monkeypatch.setattr(server, "_next_employee_id", next_code)
    return state


def call(body=None):
    return asyncio.run(server.create_my_employee_profile(request=None, payload=body))


def test_owner_gets_a_linked_profile_that_keeps_their_login_code(env):
    out = call()
    emp = out["employee"]
    assert out["created"] is True
    assert (emp["employee_id"], emp["user_id"], emp["email"]) == ("DS0001", "u_owner", "anita@studio.test")
    assert (emp["first_name"], emp["last_name"], emp["designation"], emp["department"]) == \
        ("Anita", "Mehta Shah", "Principal", "Management")
    assert emp["shift_start"] is None and emp["employment_status"] == "active"   # workspace hours apply
    assert env.audits == ["employee.self_profile"]


def test_a_taken_login_code_gets_the_next_free_code(env):
    env.employees.rows.append({"id": "emp_x", "employee_id": "DS0001", "user_id": "u_other", "email": "x@studio.test"})
    assert call()["employee"]["employee_id"] == "DS0009"


def test_login_without_a_code_receives_the_new_one(env):
    env.user = {**OWNER, "employee_id": None}
    out = call(server.SelfProfileIn(designation="Founder", phone="98250 00000"))
    assert out["employee"]["employee_id"] == "DS0009" and out["employee"]["designation"] == "Founder"
    assert env.users.rows[0]["employee_id"] == "DS0009"


def test_existing_record_is_returned_not_duplicated_and_unlinked_one_is_linked(env):
    env.employees.rows.append({"id": "emp_old", "employee_id": "DS0004", "user_id": None, "email": "anita@studio.test"})
    out = call()
    assert out["created"] is False and out["employee"]["user_id"] == "u_owner"
    assert env.employees.inserted == [] and env.audits == ["employee.self_link"]
    again = call()
    assert again["created"] is False and len(env.employees.rows) == 1


@pytest.mark.parametrize("user,detail", [
    ({**OWNER, "role": "Employee", "permissions": ["tasks.read"]}, "Ask your administrator"),
    ({**OWNER, "org_id": None, "is_super_admin": True}, "Open a workspace"),   # platform staff
])
def test_staff_and_platform_accounts_cannot_self_create(env, user, detail):
    env.user = user
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == 403 and detail in exc.value.detail
    assert env.employees.inserted == []
