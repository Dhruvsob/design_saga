"""Iteration 10 — Strict tenant isolation across all business collections.

Covers the 7 features in the review_request:
 1. Tenant isolation end-to-end (fresh org sees nothing, doesn't leak into Design Saga)
 2. SuperAdmin analytics aggregates across orgs
 3. Backward compat for the default (Design Saga) org
 4. Google auth domain matching (structural check on PATCH features)
 5. Platform org endpoints (list + suspend logs out sessions)
 6. Slip PDF (skipped if no payroll_run)
 7. Scoped proxy behavior — no scope leak between requests
"""
import os
import time
import uuid

import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not found")

BASE_URL = _load_backend_url().rstrip("/")
API = f"{BASE_URL}/api"

SA_TOKEN = "sa_testtok_stable"
DS_TOKEN = "stable_testtok_do_not_delete"


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Session-scoped fixture: create a fresh org, log in its admin, tear down.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def iso_org():
    ts = int(time.time())
    admin_email = f"iso_admin_{ts}@example.com"
    admin_password = "Iso@1234"
    payload = {
        "name": f"Iso Test Studio {ts}",
        "admin_email": admin_email,
        "admin_name": "Iso Admin",
        "admin_password": admin_password,
    }
    r = requests.post(f"{API}/platform/orgs", json=payload, headers=_h(SA_TOKEN), timeout=30)
    assert r.status_code == 200, f"create_org failed: {r.status_code} {r.text}"
    body = r.json()
    org = body["org"]
    org_id = org["org_id"]

    # Login the newly-created admin via password.
    lr = requests.post(
        f"{API}/auth/login-password",
        json={"identifier": admin_email, "password": admin_password},
        timeout=30,
    )
    assert lr.status_code == 200, f"login-password failed: {lr.status_code} {lr.text}"
    ldata = lr.json()
    admin_token = ldata.get("session_token") or ldata.get("token")
    if not admin_token:
        # Some builds set only a cookie
        admin_token = lr.cookies.get("session_token")
    assert admin_token, f"no session token in login response: {ldata}"

    yield {"org_id": org_id, "admin_token": admin_token, "admin_email": admin_email}

    # Teardown: purge the org.
    requests.delete(
        f"{API}/platform/orgs/{org_id}",
        params={"purge": "true"},
        headers=_h(SA_TOKEN),
        timeout=30,
    )


# ---------------------------------------------------------------------------
# 1. TENANT ISOLATION END-TO-END
# ---------------------------------------------------------------------------
class TestTenantIsolation:
    def test_fresh_org_projects_empty(self, iso_org):
        r = requests.get(f"{API}/projects", headers=_h(iso_org["admin_token"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        arr = data if isinstance(data, list) else data.get("projects", data.get("items", []))
        assert len(arr) == 0, f"Expected 0 projects for fresh org, got {len(arr)}"

    def test_fresh_org_vendors_empty(self, iso_org):
        r = requests.get(f"{API}/vendors", headers=_h(iso_org["admin_token"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        arr = data if isinstance(data, list) else data.get("vendors", data.get("items", []))
        assert len(arr) == 0, f"Expected 0 vendors for fresh org, got {len(arr)}"

    def test_fresh_org_leads_empty(self, iso_org):
        r = requests.get(f"{API}/leads", headers=_h(iso_org["admin_token"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        arr = data if isinstance(data, list) else data.get("leads", data.get("items", []))
        assert len(arr) == 0, f"Expected 0 leads for fresh org, got {len(arr)}"

    def test_fresh_org_tasks_empty(self, iso_org):
        r = requests.get(f"{API}/tasks", headers=_h(iso_org["admin_token"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        arr = data if isinstance(data, list) else data.get("tasks", data.get("items", []))
        assert len(arr) == 0, f"Expected 0 tasks for fresh org, got {len(arr)}"

    def test_fresh_org_dashboard_stats_zero(self, iso_org):
        r = requests.get(f"{API}/dashboard/stats", headers=_h(iso_org["admin_token"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # revenue == 0 and active_projects == 0 for a fresh org
        rev = data.get("revenue", data.get("total_revenue", data.get("kpis", {}).get("revenue", 0)))
        active = data.get("active_projects", data.get("activeProjects", data.get("kpis", {}).get("active_projects", 0)))
        assert (rev or 0) == 0, f"revenue should be 0 for fresh org, got {rev}"
        assert (active or 0) == 0, f"active_projects should be 0 for fresh org, got {active}"

    def test_create_project_stamps_org_id_and_isolation(self, iso_org):
        # Create a project as the fresh-org admin
        proj_name = f"Iso-Proj-{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/projects",
            json={"name": proj_name, "client_name": "Iso Client", "budget": 1000},
            headers=_h(iso_org["admin_token"]),
            timeout=30,
        )
        assert r.status_code in (200, 201), f"create project failed: {r.status_code} {r.text}"
        proj = r.json()
        assert proj.get("org_id") == iso_org["org_id"], (
            f"Created project not stamped with iso org_id, got {proj.get('org_id')}"
        )
        proj_id = proj.get("id") or proj.get("project_id") or proj.get("_id")
        assert proj_id, f"no project id returned: {proj}"

        # Fresh org sees exactly 1
        r2 = requests.get(f"{API}/projects", headers=_h(iso_org["admin_token"]), timeout=30)
        assert r2.status_code == 200
        arr2 = r2.json() if isinstance(r2.json(), list) else r2.json().get("projects", [])
        assert len(arr2) == 1, f"Fresh org should see exactly 1 project, got {len(arr2)}"

        # Design Saga admin doesn't see the iso project
        r3 = requests.get(f"{API}/projects", headers=_h(DS_TOKEN), timeout=30)
        assert r3.status_code == 200
        ds_arr = r3.json() if isinstance(r3.json(), list) else r3.json().get("projects", [])
        ds_names = [p.get("name") for p in ds_arr]
        assert proj_name not in ds_names, (
            f"Design Saga leaked iso project! DS projects: {ds_names}"
        )
        assert 1 <= len(ds_arr) <= 20, f"Design Saga project count unexpected: {len(ds_arr)}"

        # Design Saga fetching iso project by id should return 404
        r4 = requests.get(f"{API}/projects/{proj_id}", headers=_h(DS_TOKEN), timeout=30)
        assert r4.status_code == 404, (
            f"Cross-org access NOT blocked: DS got {r4.status_code} for iso project"
        )


# ---------------------------------------------------------------------------
# 2. SUPER ADMIN SEES EVERYTHING
# ---------------------------------------------------------------------------
class TestSuperAdminAnalytics:
    def test_analytics_aggregates_across_orgs(self, iso_org):
        # Snapshot BEFORE creating an extra project in iso org
        r_before = requests.get(f"{API}/platform/analytics", headers=_h(SA_TOKEN), timeout=30)
        assert r_before.status_code == 200, r_before.text
        before = r_before.json()
        projects_before = (
            before.get("projects")
            or before.get("totals", {}).get("projects")
            or before.get("counts", {}).get("projects")
            or 0
        )

        # Create one more iso project
        r = requests.post(
            f"{API}/projects",
            json={"name": f"SA-Bump-{uuid.uuid4().hex[:6]}", "budget": 500},
            headers=_h(iso_org["admin_token"]),
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text

        r_after = requests.get(f"{API}/platform/analytics", headers=_h(SA_TOKEN), timeout=30)
        assert r_after.status_code == 200
        after = r_after.json()
        projects_after = (
            after.get("projects")
            or after.get("totals", {}).get("projects")
            or after.get("counts", {}).get("projects")
            or 0
        )
        assert projects_after >= projects_before + 1, (
            f"Analytics projects didn't increment: before={projects_before}, after={projects_after}"
        )


# ---------------------------------------------------------------------------
# 3. BACKWARD COMPAT FOR DEFAULT ORG (Design Saga)
# ---------------------------------------------------------------------------
class TestDesignSagaBackwardCompat:
    def test_dashboard_stats(self):
        r = requests.get(f"{API}/dashboard/stats", headers=_h(DS_TOKEN), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        rev = data.get("revenue") or data.get("total_revenue") or data.get("kpis", {}).get("revenue") or 0
        assert rev > 0, f"Design Saga revenue should be > 0, got {rev}"

    def test_vendors_present(self):
        r = requests.get(f"{API}/vendors", headers=_h(DS_TOKEN), timeout=30)
        assert r.status_code == 200
        data = r.json()
        arr = data if isinstance(data, list) else data.get("vendors", data.get("items", []))
        assert len(arr) >= 5, f"Design Saga vendors low: {len(arr)}"

    def test_tasks_present(self):
        r = requests.get(f"{API}/tasks", headers=_h(DS_TOKEN), timeout=30)
        assert r.status_code == 200
        data = r.json()
        arr = data if isinstance(data, list) else data.get("tasks", data.get("items", []))
        assert len(arr) >= 5, f"Design Saga tasks low: {len(arr)}"

    def test_leads_endpoint(self):
        r = requests.get(f"{API}/leads", headers=_h(DS_TOKEN), timeout=30)
        assert r.status_code == 200

    def test_projects_present(self):
        r = requests.get(f"{API}/projects", headers=_h(DS_TOKEN), timeout=30)
        assert r.status_code == 200
        data = r.json()
        arr = data if isinstance(data, list) else data.get("projects", data.get("items", []))
        assert len(arr) >= 1, f"Design Saga should have projects, got {len(arr)}"

    def test_balance_sheet(self):
        r = requests.get(
            f"{API}/accounting/reports/balance-sheet",
            headers=_h(DS_TOKEN),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        # Should have some rows/structure
        body = r.json()
        assert body is not None

    def test_notifications(self):
        r = requests.get(f"{API}/notifications", headers=_h(DS_TOKEN), timeout=30)
        assert r.status_code == 200
        body = r.json()
        arr = body if isinstance(body, list) else body.get("notifications", body.get("items", []))
        assert isinstance(arr, list), "notifications should be a list"


# ---------------------------------------------------------------------------
# 4. GOOGLE AUTH DOMAIN MATCHING — structural check on PATCH features/email_domains
# ---------------------------------------------------------------------------
class TestOrgDomainPatch:
    def test_patch_email_domains(self, iso_org):
        r = requests.patch(
            f"{API}/platform/orgs/{iso_org['org_id']}",
            json={"features": {"email_domains": ["example.com"]}},
            headers=_h(SA_TOKEN),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        feats = body.get("features") or {}
        assert "email_domains" in feats, "features.email_domains not persisted"


# ---------------------------------------------------------------------------
# 5. PLATFORM ORG ENDPOINTS — list + suspend kills sessions
# ---------------------------------------------------------------------------
class TestPlatformOrgs:
    def test_list_orgs_shows_both(self, iso_org):
        r = requests.get(f"{API}/platform/orgs", headers=_h(SA_TOKEN), timeout=30)
        assert r.status_code == 200
        body = r.json()
        arr = body if isinstance(body, list) else body.get("orgs", body.get("items", []))
        ids = [o.get("org_id") for o in arr]
        assert "org_default" in ids, f"org_default missing from list: {ids}"
        assert iso_org["org_id"] in ids, f"iso org missing from list: {ids}"

    def test_suspend_kills_sessions(self, iso_org):
        # Sanity: token works
        pre = requests.get(f"{API}/auth/me", headers=_h(iso_org["admin_token"]), timeout=30)
        assert pre.status_code == 200, f"pre-suspend /auth/me failed: {pre.status_code}"

        # Suspend
        s = requests.post(
            f"{API}/platform/orgs/{iso_org['org_id']}/status",
            json={"action": "suspend"},
            headers=_h(SA_TOKEN),
            timeout=30,
        )
        assert s.status_code == 200, f"suspend failed: {s.status_code} {s.text}"

        # Now iso admin's token should be invalidated
        post = requests.get(f"{API}/auth/me", headers=_h(iso_org["admin_token"]), timeout=30)
        assert post.status_code == 401, (
            f"suspend did not kill sessions: /auth/me returned {post.status_code} {post.text[:200]}"
        )

        # Restore for downstream tests (best effort) and re-login to get a fresh token
        requests.post(
            f"{API}/platform/orgs/{iso_org['org_id']}/status",
            json={"action": "activate"},
            headers=_h(SA_TOKEN),
            timeout=30,
        )
        lr = requests.post(
            f"{API}/auth/login-password",
            json={"identifier": iso_org["admin_email"], "password": "Iso@1234"},
            timeout=30,
        )
        if lr.status_code == 200:
            new_tok = lr.json().get("session_token") or lr.json().get("token") or lr.cookies.get("session_token")
            if new_tok:
                iso_org["admin_token"] = new_tok


# ---------------------------------------------------------------------------
# 6. SLIP PDF — best effort, skip if no runs
# ---------------------------------------------------------------------------
class TestSlipPDF:
    def test_slip_pdf_stream(self):
        # Find a payroll_run via listing endpoint (if any)
        r = requests.get(f"{API}/payroll/runs", headers=_h(DS_TOKEN), timeout=30)
        if r.status_code != 200:
            pytest.skip(f"payroll/runs not available: {r.status_code}")
        body = r.json()
        arr = body if isinstance(body, list) else body.get("runs", body.get("items", []))
        if not arr:
            pytest.skip("No payroll_runs present")
        run_id = arr[0].get("run_id") or arr[0].get("id") or arr[0].get("_id")
        if not run_id:
            pytest.skip(f"payroll_run has no id field: {arr[0]}")
        pdf = requests.get(
            f"{API}/payroll/runs/{run_id}/slip.pdf",
            headers={"Authorization": f"Bearer {DS_TOKEN}"},
            timeout=30,
        )
        assert pdf.status_code == 200, f"slip.pdf failed: {pdf.status_code}"
        assert "application/pdf" in pdf.headers.get("Content-Type", ""), (
            f"wrong content-type: {pdf.headers.get('Content-Type')}"
        )


# ---------------------------------------------------------------------------
# 7. SCOPED PROXY BEHAVIOR — no scope leak between requests
# ---------------------------------------------------------------------------
class TestScopeLeak:
    def test_sa_then_fresh_admin_no_leak(self, iso_org):
        """Make a request as SuperAdmin (no scope) then immediately as fresh-org
        admin; the fresh admin must still see scoped (empty) data."""
        # Fresh admin might have created projects in earlier tests — instead
        # of counting, we assert no Design Saga project name leaks.
        sa = requests.get(f"{API}/platform/analytics", headers=_h(SA_TOKEN), timeout=30)
        assert sa.status_code == 200

        ds_projects = requests.get(f"{API}/projects", headers=_h(DS_TOKEN), timeout=30).json()
        ds_names = {
            p.get("name")
            for p in (ds_projects if isinstance(ds_projects, list) else ds_projects.get("projects", []))
        }

        # Now scoped admin
        iso = requests.get(f"{API}/projects", headers=_h(iso_org["admin_token"]), timeout=30)
        assert iso.status_code == 200
        iso_arr = iso.json() if isinstance(iso.json(), list) else iso.json().get("projects", [])
        iso_names = {p.get("name") for p in iso_arr}

        overlap = ds_names & iso_names
        assert not overlap, f"Scope leaked! Overlap projects between DS and iso: {overlap}"
