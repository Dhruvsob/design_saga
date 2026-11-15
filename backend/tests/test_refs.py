"""Body references must point at records of the caller's own workspace.

Found by the cross-tenant probe (2026-11-15): projects, quotations, tasks,
attendance locations and recurring expenses accepted another workspace's
client/project/vendor/account/employee IDs inside the request body."""
import asyncio
import inspect

import pytest
from fastapi import HTTPException

import core.refs as refs


class _Coll:
    def __init__(self, rows):
        self.rows = rows

    async def find_one(self, q, _p=None):
        return next((r for r in self.rows if all(r.get(k) == v for k, v in q.items())), None)


class _Scoped:
    """Only this workspace's rows are visible, like core.scoped_db.sdb."""
    def __init__(self, data):
        self.data = data

    def __getitem__(self, name):
        return _Coll(self.data.get(name, []))


@pytest.fixture
def own(monkeypatch):
    monkeypatch.setattr(refs, "sdb", _Scoped({
        "clients": [{"id": "cli_own"}], "projects": [{"id": "prj_own"}], "accounts": [{"id": "acc_own"}],
        "employees": [{"id": "emp_own"}], "users": [{"user_id": "u_own"}], "vendors": [{"id": "ven_own"}],
    }))


def run(**kw):
    return asyncio.run(refs.ensure_in_tenant(**kw))


def test_own_records_and_empty_values_pass(own):
    run(client_id="cli_own", project_id="prj_own", paid_from_account_id="acc_own",
        assignee_id="u_own", assignees=["emp_own", "u_own"], vendor_id="ven_own",
        employee_id=None, expense_account_id="")


@pytest.mark.parametrize("field,value,label", [
    ("client_id", "cli_other_workspace", "Client"),
    ("project_id", "prj_other", "Project"),
    ("paid_from_account_id", "acc_other", "Paid-from account"),
    ("expense_account_id", "probe-value", "Expense account"),
    ("assignee_id", "emp_other", "Assignee"),
    ("assignees", ["emp_own", "emp_other"], "Assignee"),
    ("vendor_id", "ven_other", "Vendor"),
])
def test_foreign_or_unknown_ids_are_refused(own, field, value, label):
    with pytest.raises(HTTPException) as exc:
        run(**{field: value})
    assert exc.value.status_code == 400 and exc.value.detail == f"{label} not found in this workspace"


def test_handlers_check_body_references():
    import server
    import routes.attendance as attendance
    import routes.finance_extras as fx
    import routes.tasks as tasks
    for fn in (server.create_project, server.update_project, server.adv_create, server.adv_update,
               tasks.create_task, tasks.update_task, tasks.bulk_update, attendance.create_location,
               fx.create_recurring, fx.update_recurring):
        assert "ensure_in_tenant" in inspect.getsource(fn), fn.__name__
