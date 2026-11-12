"""P1.5 onboarding: bulk employee import from a spreadsheet."""
import asyncio
from types import SimpleNamespace

import server


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        async def it():
            for r in self.rows:
                yield dict(r)
        return it()


class _Employees:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def find(self, *_a, **_k):
        return _Cursor(self.rows)

    async def insert_one(self, doc):
        self.rows.append(dict(doc))


def _wire(monkeypatch, perms=("employees.create", "payroll.create"), existing=()):
    emps = _Employees(existing)
    numbers = iter(range(1, 1000))
    audits = []

    async def require_user(*_a, **_k):
        return {"user_id": "admin", "org_id": "org_a", "role": "Admin"}

    async def next_id(_org):
        return f"EMP-2026-{next(numbers):04d}"

    async def audit(*a, **k):
        audits.append((a, k))

    monkeypatch.setattr(server, "require_user", require_user)
    monkeypatch.setattr(server, "has_permission", lambda _u, p: p in perms)
    monkeypatch.setattr(server, "sdb", SimpleNamespace(employees=emps))
    monkeypatch.setattr(server, "_next_employee_id", next_id)
    monkeypatch.setattr(server, "audit_log", audit)
    return emps, audits


def _run(rows, dry_run):
    payload = server.EmployeeImportIn(rows=[server.EmployeeImportRow(**r) for r in rows], dry_run=dry_run)
    return asyncio.run(server.import_employees(payload, request=None))


GOOD = [
    {"first_name": "Asha", "last_name": "Mehta", "email": "Asha@Studio.in", "phone": "+91 98765 43210",
     "joining_date": "01/04/2026", "employment_type": "Full time", "monthly_salary": "45,000"},
    {"first_name": "Ravi", "designation": "Site Engineer"},
]


def test_dry_run_checks_rows_without_saving(monkeypatch):
    emps, _ = _wire(monkeypatch)
    out = _run(GOOD, dry_run=True)
    assert out == {"created": 0, "valid": 2, "invalid": 0, "rows": out["rows"]}
    assert emps.rows == []


def test_import_creates_every_row_with_normalised_fields(monkeypatch):
    emps, audits = _wire(monkeypatch)
    out = _run(GOOD, dry_run=False)
    assert out["created"] == 2
    asha, ravi = emps.rows
    assert asha["email"] == "asha@studio.in" and asha["joining_date"] == "2026-04-01"
    assert asha["employment_type"] == "full_time" and asha["monthly_salary"] == 45000.0
    assert asha["employee_id"] == "EMP-2026-0001" and ravi["employee_id"] == "EMP-2026-0002"
    assert ravi["department"] == "Design" and ravi["employment_status"] == "active"
    assert audits and audits[0][0][1] == "employee.import"


def test_any_bad_row_saves_nothing(monkeypatch):
    emps, _ = _wire(monkeypatch, existing=[{"email": "taken@studio.in"}])
    out = _run([
        {"first_name": "Ok"},
        {"first_name": "", "email": "x@studio.in"},
        {"first_name": "Dup", "email": "taken@studio.in"},
        {"first_name": "Twice", "email": "same@studio.in"},
        {"first_name": "Twice", "email": "same@studio.in"},
        {"first_name": "Date", "joining_date": "April 1st"},
        {"first_name": "Type", "employment_type": "freelancer"},
    ], dry_run=False)
    assert out["created"] == 0 and emps.rows == [{"email": "taken@studio.in"}]
    problems = {r["row"]: r["errors"] for r in out["rows"] if r["errors"]}
    assert set(problems) == {2, 3, 5, 6, 7}
    assert "already exists" in problems[3][0] and "twice" in problems[5][0]


def test_salary_needs_payroll_permission(monkeypatch):
    emps, _ = _wire(monkeypatch, perms=("employees.create",))
    out = _run([{"first_name": "Asha", "monthly_salary": "30000"}], dry_run=False)
    assert out["created"] == 0 and "permission" in out["rows"][0]["errors"][0]
    assert emps.rows == []
