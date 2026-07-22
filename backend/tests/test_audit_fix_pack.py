"""Iteration #5 — Audit Fix Pack backend tests (Tiers A/B/C/D).

Covers only the new/changed behaviour listed by the main agent — does NOT
re-run the vendor module suite from iteration #4.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # frontend .env is the source of truth per environment
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"

ADMIN_TOKEN = "stable_testtok_do_not_delete"
PENDING_TOKEN = "newbie_tok"


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    return H(ADMIN_TOKEN)


@pytest.fixture(scope="module")
def coa_accounts(admin_headers):
    """Ensure Chart of Accounts is seeded and return income + bank accounts."""
    r = requests.get(f"{API}/accounts", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    accs = r.json()
    if not any(a.get("type") == "income" for a in accs) or not any(a.get("type") == "asset" for a in accs):
        seed = requests.post(f"{API}/accounting/seed-coa", headers=admin_headers, timeout=15)
        assert seed.status_code in (200, 201), seed.text
        r = requests.get(f"{API}/accounts", headers=admin_headers, timeout=15)
        accs = r.json()
    income = next(a for a in accs if a.get("type") == "income")
    # Prefer bank/cash asset
    bank = next((a for a in accs if a.get("type") == "asset" and "bank" in (a.get("name") or "").lower()), None)
    if not bank:
        bank = next(a for a in accs if a.get("type") == "asset")
    return {"income": income, "bank": bank}


# ---------------------------------------------------------------------------
# A1 — dashboard.kpis.revenue from journal_entries
# ---------------------------------------------------------------------------
class TestA1DashboardRevenue:
    def test_revenue_reflects_income_journal(self, admin_headers, coa_accounts):
        r0 = requests.get(f"{API}/dashboard/stats", headers=admin_headers, timeout=15)
        assert r0.status_code == 200, r0.text
        baseline = float(r0.json()["kpis"]["revenue"])

        # Post an income entry
        payload = {
            "amount": 10000,
            "income_account_id": coa_accounts["income"]["id"],
            "bank_account_id": coa_accounts["bank"]["id"],
            "date": time.strftime("%Y-%m-%d"),
            "payment_method": "cash",
            "notes": "TEST_audit_a1",
        }
        r1 = requests.post(f"{API}/accounting/income", headers=admin_headers,
                           json=payload, timeout=15)
        assert r1.status_code in (200, 201), r1.text
        je = r1.json()

        r2 = requests.get(f"{API}/dashboard/stats", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        new_rev = float(r2.json()["kpis"]["revenue"])
        assert new_rev == pytest.approx(baseline + 10000, abs=0.01), \
            f"revenue {new_rev} != {baseline}+10000"

        # cleanup — delete the JE we just added if possible
        try:
            requests.delete(f"{API}/accounting/journal-entries/{je.get('id')}",
                            headers=admin_headers, timeout=10)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# A2 — Task with vendor_id backfills vendor_contact
# ---------------------------------------------------------------------------
class TestA2TaskVendorContact:
    def test_task_backfills_vendor_contact_and_appears_on_vendor(self, admin_headers):
        vs = requests.get(f"{API}/vendors", headers=admin_headers, timeout=15)
        assert vs.status_code == 200, vs.text
        vendors = vs.json()
        assert vendors, "No vendors seeded — test cannot run"
        vendor = vendors[0]
        vid = vendor["id"]

        payload = {
            "task_type": "vendor",
            "vendor_id": vid,
            "priority": "medium",
            "status_detail": "Not Started",
            "title": "TEST_audit_a2_ui_task",
        }
        r = requests.post(f"{API}/tasks", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        task = r.json()
        vc = task.get("vendor_contact") or {}
        assert vc.get("vendor_name") == vendor.get("name"), \
            f"vendor_contact.vendor_name '{vc.get('vendor_name')}' != master '{vendor.get('name')}'"

        # Fetch vendor detail — task should appear in .tasks[]
        vd = requests.get(f"{API}/vendors/{vid}", headers=admin_headers, timeout=15)
        assert vd.status_code == 200, vd.text
        vd_tasks = vd.json().get("tasks") or []
        assert any(t.get("id") == task["id"] for t in vd_tasks), \
            "New task not reflected in GET /vendors/{id}.tasks[]"


# ---------------------------------------------------------------------------
# A4 — utilization weighted by priority
# ---------------------------------------------------------------------------
class TestA4Utilization:
    def test_priority_weighted_load(self, admin_headers):
        # Create urgent + low task for LoadTester
        for prio in ("urgent", "low"):
            payload = {
                "task_type": "employee",
                "assignee_name": "LoadTester",
                "priority": prio,
                "status_detail": "Not Started",
                "title": f"TEST_audit_a4_{prio}",
            }
            r = requests.post(f"{API}/tasks", headers=admin_headers, json=payload, timeout=15)
            assert r.status_code in (200, 201), r.text

        stats = requests.get(f"{API}/dashboard/stats", headers=admin_headers, timeout=15)
        assert stats.status_code == 200
        util = stats.json().get("utilization") or []
        row = next((u for u in util if u["name"] == "LoadTester"), None)
        assert row is not None, f"LoadTester not in utilization: {util}"
        assert row["load"] >= 4, f"Expected load>=4 for urgent+low, got {row['load']}"


# ---------------------------------------------------------------------------
# B1 — seed endpoints gated
# ---------------------------------------------------------------------------
class TestB1SeedGated:
    @pytest.mark.parametrize("path", [
        "/seed",
        "/employees/seed",
        "/quotations-adv/seed",
    ])
    def test_seed_returns_403(self, admin_headers, path):
        r = requests.post(f"{API}{path}", headers=admin_headers, timeout=15)
        assert r.status_code == 403, f"{path} → {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").upper()
        assert "ENABLE_SEED_DEMO" in detail, f"detail missing gate mention: {r.text}"


# ---------------------------------------------------------------------------
# C1 — Pending user is gated but /auth/me still 200
# ---------------------------------------------------------------------------
class TestC1PendingGate:
    def test_pending_user_blocked_on_leads(self):
        r = requests.get(f"{API}/leads", headers=H(PENDING_TOKEN), timeout=15)
        assert r.status_code == 403, r.text
        assert "awaiting Admin approval" in (r.json().get("detail") or "")

    def test_pending_user_can_hit_me(self):
        r = requests.get(f"{API}/auth/me", headers=H(PENDING_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # server may nest user or return flat — accept either
        u = body.get("user") if isinstance(body, dict) and "user" in body else body
        assert u.get("approval_status") == "pending", f"approval_status={u.get('approval_status')}"


# ---------------------------------------------------------------------------
# C2 — Admin approval + rejection workflow
# ---------------------------------------------------------------------------
def _create_pending_user_via_admin(admin_headers, suffix):
    """Use POST /auth/register with approve_immediately=False to create pending user."""
    email = f"TEST_pending_{suffix}@ds.co"
    payload = {
        "email": email, "password": "Test@1234", "name": f"Pending{suffix}",
        "role": "Designer", "approve_immediately": False,
    }
    r = requests.post(f"{API}/auth/register", headers=admin_headers, json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json(), email


class TestC2Approval:
    def test_approve_flow(self, admin_headers):
        u, email = _create_pending_user_via_admin(admin_headers, f"appr_{uuid.uuid4().hex[:6]}")
        uid = u["user_id"]

        # GET /rbac/pending should include this user
        p = requests.get(f"{API}/rbac/pending", headers=admin_headers, timeout=15)
        assert p.status_code == 200, p.text
        assert any(x["user_id"] == uid for x in p.json())

        # Approve as Designer
        appr = requests.post(f"{API}/rbac/users/{uid}/approve", headers=admin_headers,
                             json={"decision": "approve", "role": "Designer"}, timeout=15)
        assert appr.status_code == 200, appr.text
        fresh = appr.json()
        assert fresh["approval_status"] == "approved"
        assert fresh["is_active"] is True
        assert (fresh.get("employee_id") or "").startswith("DS")

        # Now login and hit /leads
        login = requests.post(f"{API}/auth/login-password",
                              json={"identifier": email, "password": "Test@1234"}, timeout=15)
        assert login.status_code == 200, login.text
        tok = login.json()["session_token"]
        leads = requests.get(f"{API}/leads", headers=H(tok), timeout=15)
        assert leads.status_code == 200, leads.text

    def test_reject_flow(self, admin_headers):
        u, email = _create_pending_user_via_admin(admin_headers, f"rej_{uuid.uuid4().hex[:6]}")
        uid = u["user_id"]
        # Give the user a session so we can verify it is invalidated
        # (login-password will fail because pending, so seed a session by approving briefly? No —
        # rejection should nuke DB-created sessions. Just call reject and check user status.)
        rej = requests.post(f"{API}/rbac/users/{uid}/approve", headers=admin_headers,
                            json={"decision": "reject", "reason": "TEST"}, timeout=15)
        assert rej.status_code == 200, rej.text
        assert rej.json()["approval_status"] == "rejected"


# ---------------------------------------------------------------------------
# D1 — password login (email + employee_id) + brute-force lock
# ---------------------------------------------------------------------------
class TestD1PasswordLogin:
    def test_register_and_login_both_identifiers(self, admin_headers):
        suffix = uuid.uuid4().hex[:6]
        email = f"testps_{suffix}@ds.co"
        r = requests.post(f"{API}/auth/register", headers=admin_headers, json={
            "email": email, "password": "Test@1234", "name": "Tester",
            "role": "Designer", "approve_immediately": True,
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        u = r.json()
        emp_id = u.get("employee_id")
        assert emp_id and emp_id.startswith("DS")

        # Login by email
        r1 = requests.post(f"{API}/auth/login-password",
                           json={"identifier": email, "password": "Test@1234"}, timeout=15)
        assert r1.status_code == 200, r1.text
        assert r1.json().get("session_token")

        # Login by employee_id
        r2 = requests.post(f"{API}/auth/login-password",
                           json={"identifier": emp_id, "password": "Test@1234"}, timeout=15)
        assert r2.status_code == 200, r2.text

        # Wrong password → 401
        rw = requests.post(f"{API}/auth/login-password",
                           json={"identifier": email, "password": "WRONG_PW"}, timeout=15)
        assert rw.status_code == 401, rw.text

    def test_brute_force_lockout(self):
        # Use fresh identifier so we're not polluted by previous tests
        ident = f"lockout_{uuid.uuid4().hex[:6]}@ds.co"
        codes = []
        for _ in range(6):
            r = requests.post(f"{API}/auth/login-password",
                              json={"identifier": ident, "password": "nope"}, timeout=15)
            codes.append(r.status_code)
        assert 429 in codes, f"No 429 after 6 attempts: {codes}"


class TestD1PendingBlock:
    def test_pending_password_user_blocked(self, admin_headers):
        suffix = uuid.uuid4().hex[:6]
        email = f"TEST_pw_pending_{suffix}@ds.co"
        r = requests.post(f"{API}/auth/register", headers=admin_headers, json={
            "email": email, "password": "Test@1234", "name": "P", "role": "Designer",
            "approve_immediately": False,
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        uid = r.json()["user_id"]

        rl = requests.post(f"{API}/auth/login-password",
                           json={"identifier": email, "password": "Test@1234"}, timeout=15)
        assert rl.status_code == 403, rl.text
        assert "awaiting Admin approval" in (rl.json().get("detail") or "")

        # Approve then login should succeed
        ap = requests.post(f"{API}/rbac/users/{uid}/approve", headers=admin_headers,
                           json={"decision": "approve", "role": "Designer"}, timeout=15)
        assert ap.status_code == 200, ap.text

        rl2 = requests.post(f"{API}/auth/login-password",
                            json={"identifier": email, "password": "Test@1234"}, timeout=15)
        assert rl2.status_code == 200, rl2.text


# ---------------------------------------------------------------------------
# D2 — change/reset password
# ---------------------------------------------------------------------------
class TestD2ChangeReset:
    def test_change_password_google_only_400(self):
        # Pending user has no password_hash → change-password → 400
        r = requests.post(f"{API}/auth/change-password", headers=H(PENDING_TOKEN),
                          json={"old_password": "x", "new_password": "abcdef1"}, timeout=15)
        # pending is blocked at require_user with 403; we need an approved google user.
        # Use the admin test session which was created without a password.
        # Fallback: accept 403 if pending blocks first, else 400.
        assert r.status_code in (400, 403), r.text
        # If 403 (pending), also validate the actual detail for the awaited case
        if r.status_code == 400:
            assert "no password" in (r.json().get("detail") or "").lower()

    def test_change_password_google_only_admin_400(self, admin_headers):
        # test-admin has no password_hash — perfect
        r = requests.post(f"{API}/auth/change-password", headers=admin_headers,
                          json={"old_password": "x", "new_password": "abcdef1"}, timeout=15)
        assert r.status_code == 400, r.text
        assert "no password" in (r.json().get("detail") or "").lower()

    def test_change_password_wrong_old(self, admin_headers):
        # Create password user & login
        suffix = uuid.uuid4().hex[:6]
        email = f"TEST_chg_{suffix}@ds.co"
        requests.post(f"{API}/auth/register", headers=admin_headers, json={
            "email": email, "password": "Test@1234", "name": "C", "role": "Designer",
            "approve_immediately": True,
        }, timeout=15)
        login = requests.post(f"{API}/auth/login-password",
                              json={"identifier": email, "password": "Test@1234"}, timeout=15)
        tok = login.json()["session_token"]

        wrong = requests.post(f"{API}/auth/change-password", headers=H(tok),
                              json={"old_password": "WRONG", "new_password": "NewPass1"},
                              timeout=15)
        assert wrong.status_code == 401, wrong.text

        ok = requests.post(f"{API}/auth/change-password", headers=H(tok),
                           json={"old_password": "Test@1234", "new_password": "NewPass1"},
                           timeout=15)
        assert ok.status_code == 200, ok.text

        # Old password now fails
        old = requests.post(f"{API}/auth/login-password",
                            json={"identifier": email, "password": "Test@1234"}, timeout=15)
        assert old.status_code == 401
        newl = requests.post(f"{API}/auth/login-password",
                             json={"identifier": email, "password": "NewPass1"}, timeout=15)
        assert newl.status_code == 200

    def test_admin_reset_invalidates_sessions(self, admin_headers):
        suffix = uuid.uuid4().hex[:6]
        email = f"TEST_rst_{suffix}@ds.co"
        u = requests.post(f"{API}/auth/register", headers=admin_headers, json={
            "email": email, "password": "Test@1234", "name": "R", "role": "Designer",
            "approve_immediately": True,
        }, timeout=15).json()
        uid = u["user_id"]

        login = requests.post(f"{API}/auth/login-password",
                              json={"identifier": email, "password": "Test@1234"}, timeout=15)
        old_tok = login.json()["session_token"]

        # Admin resets password
        rs = requests.post(f"{API}/auth/reset-password/{uid}", headers=admin_headers,
                          json={"new_password": "Reset@123"}, timeout=15)
        assert rs.status_code == 200, rs.text

        # Old session → 401
        me = requests.get(f"{API}/auth/me", headers=H(old_tok), timeout=15)
        assert me.status_code == 401, f"old bearer still valid: {me.status_code} {me.text}"

        # New password works
        nl = requests.post(f"{API}/auth/login-password",
                           json={"identifier": email, "password": "Reset@123"}, timeout=15)
        assert nl.status_code == 200


# ---------------------------------------------------------------------------
# Refactor — Director gets vendors.*
# ---------------------------------------------------------------------------
class TestDirectorVendors:
    def test_director_can_list_vendors(self, admin_headers):
        suffix = uuid.uuid4().hex[:6]
        email = f"TEST_dir_{suffix}@ds.co"
        requests.post(f"{API}/auth/register", headers=admin_headers, json={
            "email": email, "password": "Test@1234", "name": "Dir", "role": "Director",
            "approve_immediately": True,
        }, timeout=15)
        login = requests.post(f"{API}/auth/login-password",
                              json={"identifier": email, "password": "Test@1234"}, timeout=15)
        tok = login.json()["session_token"]
        r = requests.get(f"{API}/vendors", headers=H(tok), timeout=15)
        assert r.status_code == 200, r.text
