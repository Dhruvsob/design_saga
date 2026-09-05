"""Iteration 13 — Business Mode (Consultancy | Turnkey | Hybrid) tests."""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

SA_TOKEN = "sa_testtok_stable"
DS_TOKEN = "stable_testtok_do_not_delete"

SA_HDR = {"Authorization": f"Bearer {SA_TOKEN}"}
DS_HDR = {"Authorization": f"Bearer {DS_TOKEN}"}

EXPECTED_MODULE_KEYS = {
    "crm", "clients", "projects", "quotations", "employees", "attendance",
    "payroll", "accounting", "vendor_commissions", "tasks", "documents",
    "reports", "loans", "expenses", "invoices", "procurement",
    "purchase_orders", "inventory", "material_tracking", "vendor_billing",
    "labour_billing", "site_material", "project_costing",
}

# Track created orgs to clean up
_created_org_ids = []


def _create_org(mode: str):
    suffix = uuid.uuid4().hex[:8]
    body = {
        "name": f"TEST_{mode}_{suffix}",
        "admin_email": f"test_{mode}_{suffix}@example.com",
        "admin_name": f"Admin {mode}",
        "admin_password": "TestPass123!",
        "business_mode": mode,
    }
    r = requests.post(f"{API}/platform/orgs", json=body, headers=SA_HDR, timeout=30)
    assert r.status_code == 200, f"Create {mode} org failed: {r.status_code} {r.text}"
    data = r.json()
    _created_org_ids.append(data["org"]["org_id"])
    # login as admin
    lr = requests.post(f"{API}/auth/login-password",
                       json={"identifier": body["admin_email"], "password": body["admin_password"]},
                       timeout=30)
    assert lr.status_code == 200, f"Admin login failed: {lr.status_code} {lr.text}"
    token = lr.json()["session_token"]
    return data["org"], {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def consultancy_org():
    org, hdr = _create_org("consultancy")
    return org, hdr


@pytest.fixture(scope="module")
def turnkey_org():
    org, hdr = _create_org("turnkey")
    return org, hdr


@pytest.fixture(scope="module")
def hybrid_org():
    org, hdr = _create_org("hybrid")
    return org, hdr


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    # Ensure Design Saga default org is hybrid before tests run
    try:
        requests.patch(f"{API}/platform/orgs/org_default",
                       json={"business_mode": "hybrid"}, headers=SA_HDR, timeout=30)
    except Exception as e:
        print(f"pre-setup DS hybrid failed: {e}")
    yield
    for oid in _created_org_ids:
        try:
            requests.delete(f"{API}/platform/orgs/{oid}?purge=true", headers=SA_HDR, timeout=30)
        except Exception as e:
            print(f"cleanup failed for {oid}: {e}")


# ============================================================
# 1. ORG CREATION WITH MODE
# ============================================================
class TestOrgCreationWithMode:
    def test_consultancy_features(self, consultancy_org):
        org, _ = consultancy_org
        assert org["business_mode"] == "consultancy"
        m = org["features"]["modules"]
        assert m["procurement"] is False
        assert m["purchase_orders"] is False
        assert m["inventory"] is False
        assert m["crm"] is True
        assert m["accounting"] is True

    def test_turnkey_features(self, turnkey_org):
        org, _ = turnkey_org
        assert org["business_mode"] == "turnkey"
        m = org["features"]["modules"]
        assert m["procurement"] is True
        assert m["purchase_orders"] is True
        assert m["inventory"] is True

    def test_hybrid_features(self, hybrid_org):
        org, _ = hybrid_org
        assert org["business_mode"] == "hybrid"
        m = org["features"]["modules"]
        for k in ["procurement", "purchase_orders", "inventory", "crm", "accounting"]:
            assert m[k] is True, f"hybrid module {k} should be True"


# ============================================================
# 2. DEFAULT ORG RETROFIT
# ============================================================
class TestDefaultOrgRetrofit:
    def test_design_saga_hybrid(self):
        r = requests.get(f"{API}/org/current", headers=DS_HDR, timeout=30)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o.get("business_mode") == "hybrid"
        m = o["features"]["modules"]
        assert m["procurement"] is True
        assert m["purchase_orders"] is True

    def test_org_current_shape(self):
        r = requests.get(f"{API}/org/current", headers=DS_HDR, timeout=30)
        o = r.json()
        assert "business_mode" in o
        assert "features" in o and "modules" in o["features"]
        keys = set(o["features"]["modules"].keys())
        missing = EXPECTED_MODULE_KEYS - keys
        assert not missing, f"missing module keys: {missing}"


# ============================================================
# 3. MODULE GATING — CONSULTANCY
# ============================================================
class TestModuleGatingConsultancy:
    def test_post_po_blocked(self, consultancy_org):
        _, hdr = consultancy_org
        payload = {"vendor_id": "v1",
                   "lines": [{"item_name": "Cement", "quantity": 10, "unit_price": 100}]}
        r = requests.post(f"{API}/purchase-orders", json=payload, headers=hdr, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
        assert "Purchase Orders" in r.text or "purchase_orders" in r.text.lower()

    def test_get_po_blocked(self, consultancy_org):
        _, hdr = consultancy_org
        r = requests.get(f"{API}/purchase-orders", headers=hdr, timeout=30)
        assert r.status_code == 403

    def test_get_grns_blocked(self, consultancy_org):
        _, hdr = consultancy_org
        r = requests.get(f"{API}/grns", headers=hdr, timeout=30)
        assert r.status_code == 403

    def test_post_grns_blocked(self, consultancy_org):
        _, hdr = consultancy_org
        payload = {"po_id": "po_x", "lines": [{"po_line_id": "l1", "received_qty": 5}]}
        r = requests.post(f"{API}/grns", json=payload, headers=hdr, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_other_endpoints_work(self, consultancy_org):
        _, hdr = consultancy_org
        for path in ["/projects", "/vendors", "/leads",
                     "/accounting/reports/balance-sheet", "/expenses"]:
            r = requests.get(f"{API}{path}", headers=hdr, timeout=30)
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


# ============================================================
# 4. MODULE GATING — TURNKEY
# ============================================================
class TestModuleGatingTurnkey:
    def test_po_allowed(self, turnkey_org):
        _, hdr = turnkey_org
        r = requests.get(f"{API}/purchase-orders", headers=hdr, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_vendors_projects_allowed(self, turnkey_org):
        _, hdr = turnkey_org
        for path in ["/vendors", "/projects"]:
            r = requests.get(f"{API}{path}", headers=hdr, timeout=30)
            assert r.status_code == 200


# ============================================================
# 5. MODE CHANGE VIA PATCH
# ============================================================
class TestModeChange:
    def test_patch_turnkey_to_consultancy(self, turnkey_org):
        org, hdr = turnkey_org
        oid = org["org_id"]
        r = requests.patch(f"{API}/platform/orgs/{oid}",
                           json={"business_mode": "consultancy"},
                           headers=SA_HDR, timeout=30)
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["features"]["modules"]["purchase_orders"] is False

        # PO endpoint now returns 403
        r2 = requests.get(f"{API}/purchase-orders", headers=hdr, timeout=30)
        assert r2.status_code == 403


# ============================================================
# 6. PROJECT engagement_type
# ============================================================
class TestProjectEngagementType:
    def test_consultancy_auto(self, consultancy_org):
        _, hdr = consultancy_org
        r = requests.post(f"{API}/projects",
                          json={"name": f"TEST_solo_{uuid.uuid4().hex[:6]}", "budget": 100000},
                          headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("engagement_type") == "consultancy"

    def test_turnkey_auto(self):
        # Create fresh turnkey since fixture-turnkey was patched to consultancy
        _, hdr = _create_org("turnkey")
        r = requests.post(f"{API}/projects",
                          json={"name": f"TEST_tk_{uuid.uuid4().hex[:6]}"},
                          headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("engagement_type") == "turnkey"

    def test_hybrid_required(self):
        r = requests.post(f"{API}/projects",
                          json={"name": f"TEST_hyb_{uuid.uuid4().hex[:6]}"},
                          headers=DS_HDR, timeout=30)
        assert r.status_code == 400
        assert "engagement_type" in r.text.lower()

    def test_hybrid_consultancy(self):
        r = requests.post(f"{API}/projects",
                          json={"name": f"TEST_hyb_c_{uuid.uuid4().hex[:6]}",
                                "engagement_type": "consultancy"},
                          headers=DS_HDR, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["engagement_type"] == "consultancy"

    def test_hybrid_turnkey(self):
        r = requests.post(f"{API}/projects",
                          json={"name": f"TEST_hyb_t_{uuid.uuid4().hex[:6]}",
                                "engagement_type": "turnkey"},
                          headers=DS_HDR, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["engagement_type"] == "turnkey"

    def test_hybrid_invalid(self):
        r = requests.post(f"{API}/projects",
                          json={"name": f"TEST_hyb_bad_{uuid.uuid4().hex[:6]}",
                                "engagement_type": "foo"},
                          headers=DS_HDR, timeout=30)
        assert r.status_code == 400


# ============================================================
# 7. BACKWARD COMPAT
# ============================================================
class TestBackwardCompat:
    @pytest.mark.parametrize("path", [
        "/dashboard/stats", "/leads", "/projects", "/tasks", "/vendors",
        "/invoices", "/accounting/reports/balance-sheet", "/notifications",
        "/loans", "/expenses", "/audit-log",
    ])
    def test_user_endpoints(self, path):
        r = requests.get(f"{API}{path}", headers=DS_HDR, timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("path", ["/platform/orgs", "/platform/analytics"])
    def test_platform_endpoints(self, path):
        r = requests.get(f"{API}{path}", headers=SA_HDR, timeout=30)
        assert r.status_code == 200
