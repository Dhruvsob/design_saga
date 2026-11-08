"""Editing a paid salary, and keeping cancelled salaries out of the books."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routes import payroll
import routes.accounting as accounting


def _run(**over):
    run = {
        "id": "run_1", "employee_id": "emp_1", "employee_name": "Meet Mistry",
        "year": 2026, "month": 10, "status": "paid", "net": 12000.0,
        "journal_id": "je_1", "period_key": "org_a:emp_1:2026-10",
        "salary_account_id": "acc_salary", "paid_from_account_id": "acc_cash",
        "breakdown": {"basic": 12000.0, "additions": 0.0, "gross": 12000.0,
                      "deductions_total": 0.0, "net": 12000.0},
        "extras": {"bonus": 0.0, "advances_recovered": 0.0},
    }
    run.update(over)
    return run


def _wire(monkeypatch, runs, journal, accounts):
    calls = {"posted": [], "reversed": [], "hidden": []}

    class Runs:
        async def find_one(self, query, *_a):
            for r in runs:
                if query.get("id") == r["id"]:
                    return dict(r)
                if "employee_id" in query and r["employee_id"] == query["employee_id"] \
                        and r["id"] != query["id"]["$ne"] and r["status"] in query["status"]["$in"]:
                    return dict(r)
            return None

        async def insert_one(self, doc):
            runs.append(dict(doc))

        async def update_one(self, query, update):
            for r in runs:
                if r["id"] == query["id"]:
                    r.update(update.get("$set", {}))
                    for key in update.get("$unset", {}):
                        r.pop(key, None)
            return SimpleNamespace(modified_count=1)

        async def delete_one(self, query):
            runs[:] = [r for r in runs if r["id"] != query["id"]]

    class Journals:
        async def find_one(self, query, *_a):
            return dict(journal) if query.get("id") == journal["id"] else None

    class Accounts:
        async def find_one(self, query, *_a):
            return accounts.get(query.get("id"))

    async def user(*_a, **_k):
        return {"user_id": "admin", "org_id": "org_a", "name": "Admin"}

    async def post(_user, date, narration, lines, **kwargs):
        calls["posted"].append({"date": date, "lines": lines, **kwargs})
        return {"id": "je_new"}

    async def reverse(_user, row, **kwargs):
        calls["reversed"].append((row["id"], kwargs))
        return {"id": "je_rev"}

    async def hide(_user, row, reason):
        calls["hidden"].append((row["id"], reason))

    async def noop(*_a, **_k):
        return None

    @asynccontextmanager
    async def unlocked(*_a, **_k):
        yield

    monkeypatch.setattr(payroll, "require_user", user)
    monkeypatch.setattr(payroll, "has_permission", lambda *_a: True)
    monkeypatch.setattr(payroll, "sdb", SimpleNamespace(
        payroll_runs=Runs(), journal_entries=Journals(), accounts=Accounts()))
    monkeypatch.setattr(payroll, "doc_lock", unlocked)
    monkeypatch.setattr(payroll, "assert_period_open", noop)  # books open in these cases
    monkeypatch.setattr(payroll, "audit", noop)
    monkeypatch.setattr(payroll, "_post_journal", post)
    monkeypatch.setattr(accounting, "_reverse_journal_entry", reverse)
    monkeypatch.setattr(accounting, "_hide_reversed_pair", hide)
    return calls


CASH = {"acc_cash": {"id": "acc_cash", "name": "Cash", "type": "asset", "is_bank": True}}


def _correct(run_id="run_1", **body):
    body = {"net": 15000, "bonus": 3000, "payment_date": "2026-10-31",
            "paid_from_account_id": "acc_cash", "payment_method": "cash", **body}
    return asyncio.run(payroll.correct_salary_payment(
        run_id, payroll.SalaryCorrectionIn(**body), request=None))


def test_editing_a_paid_salary_replaces_it_and_hides_the_old_one(monkeypatch):
    runs = [_run()]
    journal = {"id": "je_1", "date": "2026-10-28", "source": "payroll", "source_id": "run_1"}
    calls = _wire(monkeypatch, runs, journal, CASH)
    result = _correct()
    new = result["run"]
    assert new["net"] == 15000 and new["status"] == "paid"
    assert new["payment_date"] == "2026-10-31" and new["period_key"] == "org_a:emp_1:2026-10"
    assert new["breakdown"]["additions"] == 3000 and new["breakdown"]["gross"] == 15000
    assert new["extras"]["bonus"] == 3000
    old = next(r for r in runs if r["id"] == "run_1")
    assert old["status"] == "corrected" and old["period_key"] == f"org_a:emp_1:2026-10#corrected-run_1"
    assert old["corrected_to_run_id"] == new["id"]
    (posted,) = calls["posted"]
    assert posted["date"] == "2026-10-31" and posted["source"] == "payroll"
    assert [l["debit"] for l in posted["lines"]] == [15000, 0]
    (rev_id, kwargs) = calls["reversed"][0]
    assert rev_id == "je_1" and kwargs["hide_from_books"] is True
    assert kwargs["reversal_date"] == "2026-10-28"


def test_a_salary_reversed_earlier_can_be_paid_again_correctly(monkeypatch):
    runs = [_run(status="reversed", original_period_key="org_a:emp_1:2026-10", period_key=None)]
    runs[0].pop("period_key")
    journal = {"id": "je_1", "date": "2026-10-28", "source": "payroll", "source_id": "run_1",
               "reversed": True, "reversal_je_id": "je_r"}
    calls = _wire(monkeypatch, runs, journal, CASH)
    result = _correct()
    assert calls["hidden"] == [("je_1", "payroll_correction")]
    assert calls["reversed"] == []
    assert result["run"]["period_key"] == "org_a:emp_1:2026-10"


def test_correction_rounding_goes_to_other_earning_or_deduction():
    run = _run(net=23999.92, breakdown={"gross": 25923.0, "deductions_total": 1923.08,
                                        "additions": 923.0, "net": 23999.92})
    up, _ = payroll._corrected_breakdown(run, 24000.0, None)
    assert up["other_earning"] == 0.08 and up["net"] == 24000.0
    assert round(up["gross"] - up["deductions_total"], 2) == 24000.0
    down, _ = payroll._corrected_breakdown(run, 23000.0, None)
    assert round(down["gross"] - down["deductions_total"], 2) == 23000.0


def test_correction_refuses_when_another_paid_run_exists(monkeypatch):
    runs = [_run(status="reversed"), _run(id="run_2", status="paid")]
    journal = {"id": "je_1", "date": "2026-10-28", "source": "payroll", "source_id": "run_1"}
    _wire(monkeypatch, runs, journal, CASH)
    with pytest.raises(HTTPException) as err:
        _correct()
    assert err.value.status_code == 409


def test_cash_method_must_use_the_cash_account(monkeypatch):
    runs = [_run()]
    journal = {"id": "je_1", "date": "2026-10-28", "source": "payroll", "source_id": "run_1"}
    bank = {"acc_hdfc": {"id": "acc_hdfc", "name": "Bank_HDFC", "type": "asset", "is_bank": True}}
    _wire(monkeypatch, runs, journal, bank)
    with pytest.raises(HTTPException):
        _correct(paid_from_account_id="acc_hdfc", payment_method="cash")


def test_cancelling_a_salary_hides_it_from_the_books(monkeypatch):
    runs = [_run()]
    journal = {"id": "je_1", "date": "2026-10-28", "source": "payroll", "source_id": "run_1"}
    calls = _wire(monkeypatch, runs, journal, CASH)

    async def no_restore(*_a):
        return None
    import routes.employee_advances as adv
    monkeypatch.setattr(adv, "restore_recovery", no_restore)
    asyncio.run(payroll.reverse_salary_payment("run_1", None))
    (rev_id, kwargs) = calls["reversed"][0]
    assert kwargs["hide_from_books"] is True and kwargs["reversal_date"] == "2026-10-28"


def test_salary_journals_cannot_be_reversed_from_the_daybook(monkeypatch):
    async def user(*_a, **_k):
        return {"user_id": "admin"}

    class Journals:
        async def find_one(self, *_a, **_k):
            return {"id": "je_1", "source": "payroll", "source_id": "run_1"}

    monkeypatch.setattr(accounting, "require_user", user)
    monkeypatch.setattr(accounting, "has_permission", lambda *_a: True)
    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(journal_entries=Journals()))
    with pytest.raises(HTTPException) as err:
        asyncio.run(accounting.reverse_journal("je_1", None))
    assert err.value.status_code == 409


def test_editing_a_salary_in_closed_books_is_refused_before_anything_changes(monkeypatch):
    runs = [_run()]
    journal = {"id": "je_1", "date": "2026-03-28", "source": "payroll", "source_id": "run_1"}
    calls = _wire(monkeypatch, runs, journal, CASH)

    async def closed(day, what="This entry"):
        if day <= "2026-03-31":
            raise HTTPException(status_code=409, detail=f"{what} is in closed books")
    monkeypatch.setattr(payroll, "assert_period_open", closed)
    with pytest.raises(HTTPException) as exc:
        _correct(payment_date="2026-04-05")
    assert exc.value.status_code == 409 and "salary being edited" in exc.value.detail
    assert runs == [_run()] and calls["posted"] == [] and calls["reversed"] == []
