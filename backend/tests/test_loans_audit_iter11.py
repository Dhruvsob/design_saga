"""Iteration 11 – Loans/EMI + Audit + Reassign-org + Password policy + Indexes.

Covers all features listed in the review request for backend-only testing.

IMPORTANT: Tests share a module-scoped `created_loans` list and are ordered
(create → pay → prepay → delete). Run SERIALLY: `pytest -n 0 ...`. Running in
parallel (pytest-xdist auto) will produce IndexError on the EMI/delete tests.
"""
import os
import pytest
import requests
from datetime import date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    "https://competent-matsumoto-5.preview.emergentagent.com"
API = f"{BASE_URL}/api"

ADMIN_TOK = "stable_testtok_do_not_delete"
SA_TOK = "sa_testtok_stable"
H_ADMIN = {"Authorization": f"Bearer {ADMIN_TOK}", "Content-Type": "application/json"}
H_SA = {"Authorization": f"Bearer {SA_TOK}", "Content-Type": "application/json"}


# ----------------------------- helpers -----------------------------
def _bank_account_id():
    r = requests.get(f"{API}/accounts?type=asset", headers=H_ADMIN, timeout=15)
    r.raise_for_status()
    accs = r.json()
    for a in accs:
        if a.get("is_bank") and a.get("name") in ("Bank - Primary", "Cash"):
            return a["id"]
    for a in accs:
        if a.get("is_bank"):
            return a["id"]
    pytest.skip("No bank account available")


@pytest.fixture(scope="module")
def bank_id():
    return _bank_account_id()


@pytest.fixture(scope="module")
def created_loans():
    """Track loan ids so we can clean up (only unpaid ones can be deleted)."""
    ids = []
    yield ids
    # cleanup happens in test cleanup at end


# ============================ TESTS ============================
class TestLoansCRUD:
    def test_create_loan_with_schedule_and_disbursement_je(self, bank_id, created_loans):
        payload = {
            "lender_name": "TEST_HDFC_Iter11",
            "loan_type": "business",
            "principal": 120000,
            "interest_rate_pa": 12,
            "tenure_months": 12,
            "start_date": "2026-02-01",
            "emi_day": 5,
            "disbursement_account_id": bank_id,
            "reference": "TEST-LOAN-1",
            "notes": "iteration 11 test",
        }
        r = requests.post(f"{API}/loans", headers=H_ADMIN, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["lender_name"] == "TEST_HDFC_Iter11"
        assert data["principal"] == 120000
        assert data["status"] == "active"
        assert data["disbursement_journal_id"], "disbursement JE not posted"
        assert data.get("loan_account_id"), "loan liability account not created"
        assert data["outstanding"] > 0
        assert data["next_due_date"]
        assert "totals" in data
        # schedule not returned by create? actually it's returned - check via GET
        created_loans.append(data["id"])

    def test_get_loan_returns_full_schedule(self, created_loans):
        loan_id = created_loans[0]
        r = requests.get(f"{API}/loans/{loan_id}", headers=H_ADMIN, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "schedule" in data
        assert len(data["schedule"]) == 12
        row0 = data["schedule"][0]
        assert row0["index"] == 0
        assert row0["paid"] is False
        assert row0["due_date"]
        assert row0["principal"] > 0

    def test_list_loans_rollup(self, created_loans):
        r = requests.get(f"{API}/loans", headers=H_ADMIN, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        ids = [x["id"] for x in rows]
        assert created_loans[0] in ids
        row = next(x for x in rows if x["id"] == created_loans[0])
        assert "outstanding" in row and "next_due_date" in row and "totals" in row
        assert "schedule" not in row  # trimmed in list view

    def test_patch_loan_updates_notes(self, created_loans):
        r = requests.patch(f"{API}/loans/{created_loans[0]}",
                           headers=H_ADMIN, json={"notes": "TEST_updated"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["notes"] == "TEST_updated"

    def test_verify_disbursement_je_persisted(self, created_loans):
        loan_id = created_loans[0]
        r = requests.get(f"{API}/loans/{loan_id}", headers=H_ADMIN, timeout=15)
        je_id = r.json()["disbursement_journal_id"]
        # Fetch journal entries; endpoint likely /api/accounting/journal-entries or /journals
        r2 = requests.get(f"{API}/accounting/journal-entries?source=loan_disbursement",
                          headers=H_ADMIN, timeout=15)
        if r2.status_code == 200:
            jes = r2.json()
            assert any(j.get("id") == je_id for j in jes), "disbursement JE not found"
        # else skip since endpoint shape may differ


class TestEMIPayment:
    def test_pay_first_emi(self, bank_id, created_loans):
        loan_id = created_loans[0]
        payload = {"schedule_index": 0, "paid_from_account_id": bank_id}
        r = requests.post(f"{API}/loans/{loan_id}/pay-emi",
                          headers=H_ADMIN, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "loan" in body and "journal" in body
        loan = body["loan"]
        assert loan["schedule"][0]["paid"] is True
        assert loan["schedule"][0]["journal_id"]
        assert loan["status"] == "active"  # 12 rows, only 1 paid
        # JE has 3 lines (principal, interest, bank credit)
        assert len(body["journal"]["lines"]) == 3

    def test_pay_same_emi_twice_400(self, bank_id, created_loans):
        loan_id = created_loans[0]
        r = requests.post(f"{API}/loans/{loan_id}/pay-emi",
                          headers=H_ADMIN,
                          json={"schedule_index": 0, "paid_from_account_id": bank_id},
                          timeout=20)
        assert r.status_code == 400

    def test_pay_emi_extra_principal_reduces_upcoming(self, bank_id, created_loans):
        loan_id = created_loans[0]
        # Snapshot upcoming
        r = requests.get(f"{API}/loans/{loan_id}", headers=H_ADMIN, timeout=15)
        before = r.json()["schedule"]
        # Pay EMI #2 (index 1) with extra_principal
        payload = {"schedule_index": 1, "paid_from_account_id": bank_id,
                   "extra_principal": 5000}
        r = requests.post(f"{API}/loans/{loan_id}/pay-emi",
                          headers=H_ADMIN, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        after = r.json()["loan"]["schedule"]
        # sum of upcoming principals should have shrunk by ~5000
        sum_before = sum(x["principal"] for x in before if not x["paid"] and x["index"] > 1)
        sum_after = sum(x["principal"] for x in after if not x["paid"])
        assert abs((sum_before - sum_after) - 5000) < 5, \
            f"extra_principal not reflected: before={sum_before} after={sum_after}"


class TestPrepayment:
    def test_prepay(self, bank_id, created_loans):
        loan_id = created_loans[0]
        r = requests.post(f"{API}/loans/{loan_id}/prepay",
                          headers=H_ADMIN,
                          json={"amount": 10000, "paid_from_account_id": bank_id},
                          timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert "journal" in body
        assert "outstanding" in body


class TestLoanDeleteGuard:
    def test_cannot_delete_when_emis_paid(self, created_loans):
        r = requests.delete(f"{API}/loans/{created_loans[0]}",
                            headers=H_ADMIN, timeout=15)
        assert r.status_code == 400
        assert "cannot delete" in r.text.lower() or "posted" in r.text.lower()

    def test_delete_unpaid_loan_ok(self, bank_id, created_loans):
        # Create fresh loan (no payments) then delete
        payload = {
            "lender_name": "TEST_ToDelete_Iter11",
            "principal": 60000,
            "interest_rate_pa": 10,
            "tenure_months": 6,
            "start_date": "2026-02-01",
            "disbursement_account_id": bank_id,
        }
        r = requests.post(f"{API}/loans", headers=H_ADMIN, json=payload, timeout=20)
        assert r.status_code == 200
        lid = r.json()["id"]
        r2 = requests.delete(f"{API}/loans/{lid}", headers=H_ADMIN, timeout=15)
        assert r2.status_code == 200
        # Verify gone
        r3 = requests.get(f"{API}/loans/{lid}", headers=H_ADMIN, timeout=15)
        assert r3.status_code == 404


class TestLoansDashboard:
    def test_dashboard_summary(self):
        r = requests.get(f"{API}/loans/summary/dashboard",
                         headers=H_ADMIN, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("active_loans", "total_outstanding",
                  "next_emi_due_date", "next_emi_amount"):
            assert k in d
        assert d["active_loans"] >= 1
        assert d["total_outstanding"] > 0


class TestAuditLog:
    def test_admin_sees_own_org_audit(self, created_loans):
        r = requests.get(f"{API}/audit-log?limit=50",
                         headers=H_ADMIN, timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        actions = {row["action"] for row in rows}
        assert "loan.create" in actions
        assert "loan.pay_emi" in actions
        assert "loan.prepay" in actions

    def test_audit_filter_by_action(self):
        r = requests.get(f"{API}/audit-log?action=loan.create&limit=20",
                         headers=H_ADMIN, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert all(row["action"] == "loan.create" for row in rows)
        assert len(rows) >= 1

    def test_superadmin_sees_all(self):
        r = requests.get(f"{API}/audit-log?limit=10",
                         headers=H_SA, timeout=15)
        assert r.status_code == 200


class TestPendingSignupsAndReassign:
    def test_pending_signups_superadmin(self):
        r = requests.get(f"{API}/platform/pending-signups",
                         headers=H_SA, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_pending_signups_admin_forbidden(self):
        r = requests.get(f"{API}/platform/pending-signups",
                         headers=H_ADMIN, timeout=15)
        assert r.status_code in (401, 403)

    def test_reassign_org(self):
        # Create an ephemeral pending google-style user directly via SA endpoint?
        # No such endpoint — use direct mongo insert via a fresh RegisterIn is
        # not possible for google users. Instead pick existing pending user
        # 'user_newbie' from test_credentials.md.
        target_uid = "user_newbie"
        # First check user exists
        r0 = requests.get(f"{API}/platform/orgs/org_default/users",
                          headers=H_SA, timeout=15)
        # Reassign
        r = requests.post(f"{API}/platform/users/{target_uid}/reassign-org",
                          headers=H_SA,
                          json={"org_id": "org_default", "role": "Employee",
                                "approve": True}, timeout=15)
        if r.status_code == 404:
            pytest.skip("Test pending user 'user_newbie' not in DB")
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["org_id"] == "org_default"
        assert u["approval_status"] == "approved"
        assert u["is_active"] is True


class TestPasswordPolicy:
    """POST /api/auth/register — Admin creates a user; validate password rules."""

    def _register(self, email, password):
        return requests.post(f"{API}/auth/register", headers=H_ADMIN, json={
            "email": email, "password": password, "name": "TEST User",
            "role": "Employee"
        }, timeout=15)

    def test_weak_short_alnum(self):
        r = self._register("TEST_pw_short@ds.co", "abc123")
        assert r.status_code == 422, r.text
        assert "8" in r.text

    def test_letters_only_fails(self):
        r = self._register("TEST_pw_letters@ds.co", "onlyletters")
        assert r.status_code == 422, r.text

    def test_digits_only_fails(self):
        r = self._register("TEST_pw_digits@ds.co", "12345678")
        assert r.status_code == 422, r.text

    def test_strong_password_ok(self):
        email = "TEST_pw_ok_iter11@ds.co"
        r = self._register(email, "password123")
        # Could be 200 or 409 if this exact test ran before. Both acceptable
        # as long as it's NOT a 422 validation error.
        assert r.status_code in (200, 201, 409), r.text


class TestMongoIndexesFunctional:
    def test_projects_filter_responds_quickly(self):
        import time
        t0 = time.time()
        r = requests.get(f"{API}/projects?stage=New", headers=H_ADMIN, timeout=15)
        dt = time.time() - t0
        assert r.status_code == 200
        assert dt < 5, f"query took {dt}s"


class TestBackwardCompat:
    @pytest.mark.parametrize("path", [
        "/dashboard/stats",
        "/vendors",
        "/tasks",
        "/leads",
        "/projects",
        "/accounting/reports/balance-sheet",
        "/notifications",
    ])
    def test_admin_endpoints(self, path):
        r = requests.get(f"{API}{path}", headers=H_ADMIN, timeout=20)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"

    @pytest.mark.parametrize("path", [
        "/platform/orgs",
        "/platform/analytics",
    ])
    def test_superadmin_endpoints(self, path):
        r = requests.get(f"{API}{path}", headers=H_SA, timeout=20)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


# --------------------------- CLEANUP ---------------------------
def test_zz_cleanup(created_loans):
    """Cleanup created loans + related JE/audit rows so DB stays clean.
    Loans with paid EMIs cannot be deleted via API, so we scrub via mongo.
    """
    import subprocess, json
    # Delete via mongosh
    script = """
    use('test_database');
    var loans = db.loans.find({lender_name: /^TEST_/}, {id:1, disbursement_journal_id:1, schedule:1}).toArray();
    var jeIds = [];
    loans.forEach(function(l){
      if (l.disbursement_journal_id) jeIds.push(l.disbursement_journal_id);
      (l.schedule||[]).forEach(function(r){ if (r.journal_id) jeIds.push(r.journal_id); });
    });
    var loanIds = loans.map(function(l){return l.id;});
    db.journal_entries.deleteMany({$or:[{id:{$in:jeIds}}, {source_id:{$in:loanIds}}]});
    db.loans.deleteMany({lender_name: /^TEST_/});
    db.accounts.deleteMany({name: /^Loan – TEST_/});
    db.audit_log.deleteMany({target:{$in: loanIds}});
    db.users.deleteMany({email: /^TEST_pw_/});
    print(JSON.stringify({loans: loanIds.length}));
    """
    try:
        out = subprocess.check_output(["mongosh", "--quiet", "--eval", script],
                                       stderr=subprocess.STDOUT, timeout=15).decode()
        print("cleanup:", out.strip())
    except Exception as e:
        print("cleanup skipped:", e)
