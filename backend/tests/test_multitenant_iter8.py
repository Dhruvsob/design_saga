"""
Backend tests for Multi-Tenant SaaS retrofit (iteration 8).
Covers: auth/me tenant fields, SuperAdmin platform routes, org/current branding,
tenancy bootstrap, RBAC SuperAdmin role, payroll slip pdf, invoice pdf,
backward compat of legacy endpoints.
"""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback read
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

ADMIN_TOKEN = "stable_testtok_do_not_delete"
SA_TOKEN = "sa_testtok_stable"
PENDING_TOKEN = "newbie_tok"


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============ Auth / Me ============
class TestAuthMe:
    def test_legacy_admin_me(self):
        r = requests.get(f"{API}/auth/me", headers=H(ADMIN_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("org_id") == "org_default", d
        assert d.get("is_super_admin") in (False, None), d
        assert d.get("email") == "test-admin@ds.co"

    def test_super_admin_me(self):
        r = requests.get(f"{API}/auth/me", headers=H(SA_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("is_super_admin") is True, d
        assert d.get("role") == "SuperAdmin", d
        # org_id may be null for SA
        perms = d.get("permissions") or []
        assert any(p in perms for p in ("*.*", "platform.*")), perms

    def test_password_login(self):
        r = requests.post(f"{API}/auth/login-password", json={"identifier": "pmanager@ds.co", "password": "Test@1234"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "session_token" in d or "token" in d or "access_token" in d, d


# ============ Platform (SuperAdmin) ============
class TestPlatformRoutes:
    def test_orgs_requires_super_admin(self):
        r = requests.get(f"{API}/platform/orgs", headers=H(ADMIN_TOKEN), timeout=15)
        assert r.status_code == 403, r.status_code

    def test_orgs_list_sa(self):
        r = requests.get(f"{API}/platform/orgs", headers=H(SA_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # accept list or {items:[...]}
        items = data if isinstance(data, list) else data.get("items") or data.get("orgs") or []
        assert any((o.get("id") == "org_default" or o.get("org_id") == "org_default" or o.get("slug") == "design-saga") for o in items), items

    def test_analytics(self):
        r = requests.get(f"{API}/platform/analytics", headers=H(SA_TOKEN), timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("orgs", "users", "projects", "tasks", "revenue_total", "leaderboard"):
            assert k in d, f"missing {k} in {d.keys()}"

    def test_create_update_status_admin_reset_delete(self):
        import uuid
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "name": f"Test Org {suffix}",
            "slug": f"test-org-{suffix}",
            "admin_email": f"admin_{suffix}@testorg.co",
            "admin_name": "Admin One",
            "admin_password": "Test@1234",
        }
        r = requests.post(f"{API}/platform/orgs", headers=H(SA_TOKEN), json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        org = created.get("org") or created
        oid = org.get("id") or org.get("org_id") or org.get("_id")
        assert oid, created

        # duplicate email → 400/409
        r2 = requests.post(f"{API}/platform/orgs", headers=H(SA_TOKEN), json={**payload, "slug": payload["slug"] + "-b"}, timeout=20)
        assert r2.status_code in (400, 409), r2.text

        # PATCH
        r3 = requests.patch(f"{API}/platform/orgs/{oid}", headers=H(SA_TOKEN), json={"name": f"Renamed {suffix}"}, timeout=15)
        assert r3.status_code == 200, r3.text

        # status suspend / activate / deactivate
        for act in ("suspend", "activate", "deactivate"):
            rr = requests.post(f"{API}/platform/orgs/{oid}/status", headers=H(SA_TOKEN), json={"action": act}, timeout=15)
            assert rr.status_code == 200, f"{act}: {rr.text}"

        # add admin
        r4 = requests.post(
            f"{API}/platform/orgs/{oid}/admins",
            headers=H(SA_TOKEN),
            json={"email": f"admin2_{suffix}@testorg.co", "name": "Admin Two", "password": "Test@1234"},
            timeout=15,
        )
        assert r4.status_code in (200, 201), r4.text
        u = r4.json()
        uid = (u.get("user") or u).get("id") or (u.get("user") or u).get("_id")
        if uid:
            r5 = requests.post(f"{API}/platform/orgs/{oid}/users/{uid}/reset-password", headers=H(SA_TOKEN), timeout=15)
            assert r5.status_code == 200, r5.text

        # delete (soft)
        r6 = requests.delete(f"{API}/platform/orgs/{oid}", headers=H(SA_TOKEN), timeout=15)
        assert r6.status_code in (200, 204), r6.text
        # purge
        r7 = requests.delete(f"{API}/platform/orgs/{oid}?purge=true", headers=H(SA_TOKEN), timeout=20)
        assert r7.status_code in (200, 204, 404), r7.text

    def test_default_org_protected(self):
        r = requests.post(f"{API}/platform/orgs/org_default/status", headers=H(SA_TOKEN), json={"action": "suspend"}, timeout=15)
        assert r.status_code in (400, 403, 409), r.text
        r2 = requests.delete(f"{API}/platform/orgs/org_default", headers=H(SA_TOKEN), timeout=15)
        assert r2.status_code in (400, 403, 409), r2.text


# ============ Organization / Branding ============
class TestOrgRoutes:
    def test_get_current_authenticated(self):
        r = requests.get(f"{API}/org/current", headers=H(ADMIN_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        branding = d.get("branding") or {}
        assert "primary_color" in branding
        assert "accent_color" in branding
        assert "tagline" in branding

    def test_patch_admin_only(self):
        # pending user should be 401/403
        r = requests.patch(f"{API}/org/current", headers=H(PENDING_TOKEN), json={"branding": {"primary_color": "#123456"}}, timeout=15)
        assert r.status_code in (401, 403), r.status_code
        # legacy admin allowed
        r2 = requests.patch(f"{API}/org/current", headers=H(ADMIN_TOKEN), json={"branding": {"primary_color": "#123456", "tagline": "hello"}}, timeout=15)
        assert r2.status_code == 200, r2.text

    def test_public_org_by_slug(self):
        r = requests.get(f"{API}/org/public/competent-matsumoto-5", timeout=15)
        # This slug may or may not exist. Try design-saga as fallback:
        if r.status_code == 404:
            r = requests.get(f"{API}/org/public/design-saga", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "branding" in d or "primary_color" in d, d


# ============ RBAC ============
class TestRBAC:
    def test_roles_includes_super_admin(self):
        r = requests.get(f"{API}/rbac/roles", headers=H(ADMIN_TOKEN), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        roles = data if isinstance(data, list) else data.get("roles") or []
        role_names = [ (r_["name"] if isinstance(r_, dict) else r_) for r_ in roles]
        assert "SuperAdmin" in role_names, role_names


# ============ Payroll PDF ============
class TestPayrollSlipPdf:
    def test_unknown_run_404(self):
        r = requests.get(f"{API}/payroll/runs/nonexistent_run_xyz/slip.pdf", headers=H(ADMIN_TOKEN), timeout=15)
        assert r.status_code == 404, r.status_code


# ============ Invoice PDF ============
class TestInvoicePdf:
    def test_invoice_pdf_existing(self):
        # find any invoice
        r = requests.get(f"{API}/invoices", headers=H(ADMIN_TOKEN), timeout=15)
        if r.status_code != 200:
            pytest.skip("invoices list not available")
        lst = r.json()
        items = lst if isinstance(lst, list) else lst.get("items") or lst.get("invoices") or []
        if not items:
            pytest.skip("no invoices to test")
        inv = items[0]
        iid = inv.get("id") or inv.get("_id") or inv.get("invoice_id")
        r2 = requests.get(f"{API}/invoices/{iid}/pdf", headers=H(ADMIN_TOKEN), timeout=30)
        assert r2.status_code == 200, r2.text[:200]
        assert "application/pdf" in r2.headers.get("content-type", ""), r2.headers


# ============ Backward compat ============
class TestBackwardCompat:
    @pytest.mark.parametrize("path", [
        "/dashboard/stats",
        "/leads",
        "/projects",
        "/tasks",
        "/vendors",
        "/accounting/reports/balance-sheet",
        "/notifications",
    ])
    def test_legacy_endpoints(self, path):
        r = requests.get(f"{API}{path}", headers=H(ADMIN_TOKEN), timeout=20)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
