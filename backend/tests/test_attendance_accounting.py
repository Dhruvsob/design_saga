"""
Regression tests for Attendance and Accounting modules.
Auth via Bearer test_session_admin_001 (admin).
Requires REACT_APP_BACKEND_URL env var (frontend/.env is source of truth).
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://design-track-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TOKEN = "test_session_admin_001"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update(HEADERS)
    return sess


# ---------- helpers ----------
def _get(s, path, **kw):
    return s.get(f"{API}{path}", timeout=30, **kw)


def _post(s, path, json=None, **kw):
    return s.post(f"{API}{path}", json=json, timeout=30, **kw)


# ============================================================
# ATTENDANCE
# ============================================================
class TestAttendance:
    def test_meta(self, s):
        r = _get(s, "/attendance/meta")
        assert r.status_code == 200
        d = r.json()
        assert len(d["statuses"]) == 6
        assert set(d["statuses"]) == {"present", "absent", "half_day", "leave", "holiday", "week_off"}
        assert len(d["leave_types"]) == 7
        assert isinstance(d["default_allowance"], dict)

    def test_leave_rules_get_put(self, s):
        r = _get(s, "/attendance/leave-rules")
        assert r.status_code == 200
        assert "allowances" in r.json()
        # PUT
        r = s.put(f"{API}/attendance/leave-rules", json={
            "allowances": {"casual": 10, "sick": 10, "earned": 15, "unpaid": 0,
                           "comp_off": 0, "maternity": 90, "paternity": 15},
            "working_days_per_week": 6,
            "week_off_days": [6],
        }, timeout=30)
        assert r.status_code == 200
        assert r.json()["allowances"]["casual"] == 10

    def test_checkin_flow(self, s):
        # Clean today's record so we can re-run
        import pymongo
        # Use API-side clean via override? no delete api; skip cleanup here.
        # Attempt check-in
        r = _post(s, "/attendance/check-in", {"notes": "TEST_ci"})
        # Either 200 first time OR 400 already checked in (idempotent-ish test)
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            d = r.json()
            assert d["status"] == "present"
            assert "check_in" in d
            assert "check_in_ip" in d
            # Second call must be 400
            r2 = _post(s, "/attendance/check-in", {})
            assert r2.status_code == 400
        else:
            assert "Already checked in" in r.text

    def test_me_today(self, s):
        r = _get(s, "/attendance/me/today")
        assert r.status_code == 200
        d = r.json()
        assert "record" in d and "date" in d

    def test_me_summary(self, s):
        today = date.today()
        r = _get(s, f"/attendance/me/summary?year={today.year}&month={today.month}")
        assert r.status_code == 200
        d = r.json()
        assert "records" in d and "counts" in d
        assert "present" in d["counts"] and "leave" in d["counts"]

    def test_monthly_admin(self, s):
        today = date.today()
        r = _get(s, f"/attendance/monthly?year={today.year}&month={today.month}")
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d
        for row in d["rows"]:
            assert "employee" in row and "counts" in row and "worked_hours" in row

    def test_override(self, s):
        emp_id = f"TEST_emp_{uuid.uuid4().hex[:6]}"
        r = _post(s, "/attendance/override", {
            "employee_id": emp_id,
            "date": date.today().isoformat(),
            "status": "holiday",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "holiday"

    def test_checkout_without_checkin_returns_400_for_new_emp(self, s):
        # Use a fake employee_id with no prior check-in
        r = _post(s, "/attendance/check-out", {
            "employee_id": f"TEST_noci_{uuid.uuid4().hex[:6]}",
        })
        assert r.status_code == 400


# ============================================================
# LEAVES
# ============================================================
class TestLeaves:
    def test_invalid_leave_type(self, s):
        today = date.today().isoformat()
        r = _post(s, "/leaves", {"leave_type": "vacation", "from_date": today, "to_date": today})
        assert r.status_code == 400

    def test_create_and_approve_leave(self, s):
        d1 = (date.today() + timedelta(days=10)).isoformat()
        d2 = (date.today() + timedelta(days=12)).isoformat()
        r = _post(s, "/leaves", {
            "leave_type": "casual", "from_date": d1, "to_date": d2, "reason": "TEST_leave"
        })
        assert r.status_code == 200, r.text
        lv = r.json()
        assert lv["days"] == 3, f"expected inclusive days=3 got {lv['days']}"
        assert lv["status"] == "pending"
        lv_id = lv["id"]

        # Mine
        r = _get(s, "/leaves?mine=true")
        assert r.status_code == 200
        assert any(x["id"] == lv_id for x in r.json())

        # Approve
        r = _post(s, f"/leaves/{lv_id}/action", {"action": "approve", "remarks": "ok"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # Second action should fail (already approved)
        r = _post(s, f"/leaves/{lv_id}/action", {"action": "reject"})
        assert r.status_code == 400

    def test_leave_balance(self, s):
        r = _get(s, f"/leaves/balance/user_testadmin?year={date.today().year}")
        assert r.status_code == 200
        d = r.json()
        assert "balance" in d
        for t in ["casual", "sick", "earned"]:
            assert t in d["balance"]
            assert set(d["balance"][t].keys()) == {"allowance", "used", "remaining"}


# ============================================================
# ACCOUNTING — Chart of Accounts + Journal + reports
# ============================================================
class TestAccounting:
    @pytest.fixture(scope="class")
    def coa(self, s):
        r = _get(s, "/accounts")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 36, f"expected >=36 default accounts, got {len(rows)}"
        # Index by name for lookups
        by_name = {a["name"]: a for a in rows}
        for expected in ["Cash", "Bank - Primary", "Consultancy Income", "Employee Salary", "GST Payable"]:
            assert expected in by_name, f"missing default account {expected}"
        return by_name

    def test_meta(self, s):
        r = _get(s, "/accounting/meta")
        assert r.status_code == 200
        d = r.json()
        assert set(d["account_types"]) == {"asset", "liability", "income", "expense", "equity"}

    def test_filter_expense_accounts(self, s):
        r = _get(s, "/accounts?type=expense")
        assert r.status_code == 200
        assert all(a["type"] == "expense" for a in r.json())

    def test_create_custom_account(self, s):
        r = _post(s, "/accounts", {"name": f"TEST_Acc_{uuid.uuid4().hex[:6]}", "type": "expense"})
        assert r.status_code == 200
        assert r.json()["type"] == "expense"

    def test_journal_balanced(self, s, coa):
        r = _post(s, "/journal-entries", {
            "date": date.today().isoformat(),
            "narration": "TEST_je balanced",
            "lines": [
                {"account_id": coa["Cash"]["id"], "debit": 100, "credit": 0},
                {"account_id": coa["Consultancy Income"]["id"], "debit": 0, "credit": 100},
            ],
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 100
        assert len(d["lines"]) == 2

    def test_journal_unbalanced_400(self, s, coa):
        r = _post(s, "/journal-entries", {
            "date": date.today().isoformat(),
            "narration": "unbalanced",
            "lines": [
                {"account_id": coa["Cash"]["id"], "debit": 100, "credit": 0},
                {"account_id": coa["Consultancy Income"]["id"], "debit": 0, "credit": 90},
            ],
        })
        assert r.status_code == 400

    def test_journal_zero_400(self, s, coa):
        r = _post(s, "/journal-entries", {
            "date": date.today().isoformat(),
            "narration": "zero",
            "lines": [
                {"account_id": coa["Cash"]["id"], "debit": 0, "credit": 0},
            ],
        })
        assert r.status_code == 400

    def test_income_wrapper(self, s, coa):
        r = _post(s, "/accounting/income", {
            "date": date.today().isoformat(),
            "amount": 5000,
            "income_account_id": coa["Consultancy Income"]["id"],
            "bank_account_id": coa["Bank - Primary"]["id"],
            "notes": "TEST_income",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 5000
        assert d["source"] == "income"
        assert len(d["lines"]) == 2

    def test_expense_wrapper_with_gst(self, s, coa):
        r = _post(s, "/accounting/expense", {
            "date": date.today().isoformat(),
            "amount": 1000,
            "gst": 180,
            "expense_account_id": coa["Office Rent"]["id"],
            "paid_from_account_id": coa["Bank - Primary"]["id"],
            "bill_url": "https://example.com/bill.pdf",
            "notes": "TEST_expense",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "expense"
        assert d["total"] == 1180
        # Bill url attached
        assert d.get("bill_url") == "https://example.com/bill.pdf"
        # 3 lines: expense + GST + paid_from
        assert len(d["lines"]) == 3

    def test_journal_filters(self, s):
        r = _get(s, f"/journal-entries?source=income&from_date={date.today().isoformat()}")
        assert r.status_code == 200
        rows = r.json()
        assert all(x["source"] == "income" for x in rows)

    def test_account_ledger(self, s, coa):
        acc_id = coa["Bank - Primary"]["id"]
        r = _get(s, f"/accounting/ledger/account/{acc_id}")
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "total_debit" in d and "total_credit" in d
        assert "closing_balance" in d

    def test_pl_report(self, s):
        r = _get(s, "/accounting/reports/pl")
        assert r.status_code == 200
        d = r.json()
        for k in ("income", "expense", "total_income", "total_expense", "net_profit"):
            assert k in d
        assert round(d["net_profit"], 2) == round(d["total_income"] - d["total_expense"], 2)

    def test_trial_balance_equal(self, s):
        r = _get(s, "/accounting/reports/trial-balance")
        assert r.status_code == 200
        d = r.json()
        assert round(d["total_debit"], 2) == round(d["total_credit"], 2), \
            f"Trial balance mismatch: DR={d['total_debit']} CR={d['total_credit']}"

    def test_dashboard(self, s):
        r = _get(s, "/accounting/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ("cash_bank", "income_month", "expense_month", "profit_month",
                  "salary_month", "outstanding", "overdue", "today_collections"):
            assert k in d["kpis"]
        assert "upcoming_payments" in d
        assert "recent_transactions" in d


# ============================================================
# VENDORS + MILESTONES
# ============================================================
class TestVendorsMilestones:
    def test_vendors_crud(self, s):
        r = _post(s, "/vendors", {"name": f"TEST_Vendor_{uuid.uuid4().hex[:6]}", "phone": "9999"})
        assert r.status_code == 200
        v = r.json()
        assert "id" in v
        r = _get(s, "/vendors")
        assert r.status_code == 200
        assert any(x["id"] == v["id"] for x in r.json())
        # Vendor ledger
        r = _get(s, f"/accounting/ledger/vendor/{v['id']}")
        assert r.status_code == 200
        d = r.json()
        assert "transactions" in d and "total_purchase" in d

    def test_milestones_crud(self, s):
        # Need a project - fetch one
        r = _get(s, "/projects")
        assert r.status_code == 200
        projs = r.json()
        if not projs:
            pytest.skip("No projects available to test milestones")
        proj = projs[0]
        pid = proj["id"]

        r = _post(s, f"/projects/{pid}/milestones", {
            "project_id": pid, "name": "TEST_Milestone", "percent": 25,
            "due_date": (date.today() + timedelta(days=15)).isoformat(),
        })
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["percent"] == 25
        # If project has budget, amount computed
        if proj.get("budget"):
            assert m["amount"] is not None
        mid = m["id"]

        # List
        r = _get(s, f"/projects/{pid}/milestones")
        assert r.status_code == 200
        assert any(x["id"] == mid for x in r.json())

        # PATCH
        r = s.patch(f"{API}/milestones/{mid}", json={"name": "TEST_Milestone2"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Milestone2"

        # DELETE
        r = s.delete(f"{API}/milestones/{mid}", timeout=30)
        assert r.status_code == 200

    def test_project_ledger(self, s):
        r = _get(s, "/projects")
        projs = r.json()
        if not projs:
            pytest.skip("No projects")
        pid = projs[0]["id"]
        r = _get(s, f"/accounting/ledger/project/{pid}")
        assert r.status_code == 200
        d = r.json()
        for k in ("revenue", "expense", "profit", "milestones", "transactions"):
            assert k in d

    def test_client_ledger(self, s):
        r = _get(s, "/clients") if False else _get(s, "/projects")
        projs = r.json()
        if not projs or not projs[0].get("client_id"):
            pytest.skip("No client_id on projects")
        cid = projs[0]["client_id"]
        r = _get(s, f"/accounting/ledger/client/{cid}")
        assert r.status_code == 200
        d = r.json()
        for k in ("client", "projects", "total_project_value", "received", "outstanding",
                  "milestones", "transactions"):
            assert k in d


# ============================================================
# BACKWARD COMPAT — existing endpoints still 200
# ============================================================
class TestBackwardCompat:
    @pytest.mark.parametrize("path", [
        "/auth/me", "/dashboard/stats", "/projects", "/employees",
        "/leads", "/quotations-adv", "/tasks", "/tasks/meta",
    ])
    def test_endpoint_200(self, s, path):
        r = _get(s, path)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
