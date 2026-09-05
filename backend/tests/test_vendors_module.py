"""Backend tests for the Phase-2 Vendor / Agency management + Ledger module.

Coverage:
- Vendor CRUD (create/list/get/patch/soft-delete)
- Metadata (agency_types, bill_statuses)
- Search & filter
- Documents attach/remove
- Rating create + aggregate average
- Vendor bills (compute totals, patch recompute, delete rules)
- Vendor payments (journal entry, FIFO, bill status propagation, splits)
- Ledger (running balance, totals)
- Performance score composition
- RBAC gates for Designer / Employee / HR / Accountant
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://competent-matsumoto-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_TOKEN = "stable_testtok_do_not_delete"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------- helpers ----------
def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _mk_user_with_role(role: str):
    """Create a user + session directly in Mongo with the given role. Returns token."""
    cli = MongoClient(MONGO_URL)
    db = cli[DB_NAME]
    uid = f"user_test_{role.lower()}_{uuid.uuid4().hex[:8]}"
    tok = f"tok_{role.lower()}_{uuid.uuid4().hex[:10]}"
    db.users.insert_one({
        "user_id": uid, "email": f"TEST_{uid}@ds.co", "name": f"Test {role}",
        "role": role, "created_at": "2026-01-01T00:00:00Z",
    })
    from datetime import datetime, timedelta
    db.user_sessions.insert_one({
        "user_id": uid, "session_token": tok,
        "expires_at": datetime.utcnow() + timedelta(days=1),
        "created_at": datetime.utcnow(),
    })
    cli.close()
    return tok, uid


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_headers():
    return _headers(ADMIN_TOKEN)


@pytest.fixture(scope="module")
def role_tokens():
    tokens = {}
    for r in ["Designer", "Employee", "HR", "Accountant"]:
        tokens[r], _ = _mk_user_with_role(r)
    return tokens


@pytest.fixture(scope="module")
def created_vendor(admin_headers):
    payload = {
        "name": "TEST_Vendor_Alpha",
        "company": "Alpha Interiors",
        "agency_type": "contractor",
        "contact_person": "John Doe",
        "phone": "9998887777",
        "email": "alpha@example.com",
        "gstin": "27ABCDE1234F1Z5",
        "pan": "ABCDE1234F",
        "bank_name": "HDFC",
        "bank_account_number": "111222333",
        "bank_ifsc": "HDFC0001",
        "upi_id": "alpha@upi",
        "tds_applicable": True,
        "tds_rate": 1.0,
        "category": "carpentry",
    }
    r = requests.post(f"{API}/vendors", json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("id", "").startswith("vnd_")
    assert d.get("active") is True
    assert d.get("documents") == []
    assert "created_at" in d
    return d


@pytest.fixture(scope="module")
def bank_account():
    """Get a bank/cash account for payment tests."""
    r = requests.get(f"{API}/accounts", headers=_headers(ADMIN_TOKEN))
    assert r.status_code == 200
    accs = r.json()
    # pick any Bank type account
    banks = [a for a in accs if a.get("type") == "asset" and ("Bank" in a.get("name", "") or "Cash" in a.get("name", ""))]
    assert banks, "No bank/cash account in COA"
    return banks[0]


# ==================================================
# Meta
# ==================================================
class TestVendorMeta:
    def test_meta_shape(self, admin_headers):
        r = requests.get(f"{API}/vendors/meta", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert "agency_types" in d and "bill_statuses" in d
        assert len(d["agency_types"]) == 8
        assert len(d["bill_statuses"]) == 6
        assert "contractor" in d["agency_types"]
        assert "partially_paid" in d["bill_statuses"]


# ==================================================
# CRUD
# ==================================================
class TestVendorCRUD:
    def test_list_returns_created(self, admin_headers, created_vendor):
        r = requests.get(f"{API}/vendors", headers=admin_headers)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert created_vendor["id"] in ids
        # outstanding rollup present
        target = next(v for v in r.json() if v["id"] == created_vendor["id"])
        assert "outstanding" in target

    def test_search_q(self, admin_headers, created_vendor):
        r = requests.get(f"{API}/vendors?q=TEST_Vendor_Alpha", headers=admin_headers)
        assert r.status_code == 200
        assert any(v["id"] == created_vendor["id"] for v in r.json())

    def test_filter_agency_type(self, admin_headers, created_vendor):
        r = requests.get(f"{API}/vendors?agency_type=contractor", headers=admin_headers)
        assert r.status_code == 200
        assert all(v.get("agency_type") == "contractor" for v in r.json())

    def test_get_detail_summary(self, admin_headers, created_vendor):
        r = requests.get(f"{API}/vendors/{created_vendor['id']}", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert "summary" in d
        for k in ("total_billed", "total_paid", "outstanding", "open_bills", "task_count", "project_count"):
            assert k in d["summary"]
        for k in ("bills", "payments", "tasks", "projects"):
            assert isinstance(d[k], list)

    def test_patch_partial(self, admin_headers, created_vendor):
        r = requests.patch(f"{API}/vendors/{created_vendor['id']}",
                           json={"phone": "8887776666"}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json().get("phone") == "8887776666"

    def test_patch_invalid_agency_type(self, admin_headers, created_vendor):
        r = requests.patch(f"{API}/vendors/{created_vendor['id']}",
                           json={"agency_type": "not_a_real_type"}, headers=admin_headers)
        assert r.status_code == 400

    def test_soft_delete_and_undelete(self, admin_headers):
        # Create a throwaway vendor to delete
        r = requests.post(f"{API}/vendors",
                          json={"name": "TEST_Throwaway", "agency_type": "vendor"},
                          headers=admin_headers)
        assert r.status_code == 200
        vid = r.json()["id"]
        r2 = requests.delete(f"{API}/vendors/{vid}", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json().get("soft_deleted") is True
        # Findable via mongo directly
        cli = MongoClient(MONGO_URL)
        doc = cli[DB_NAME].vendors_acc.find_one({"id": vid})
        assert doc and doc.get("active") is False and doc.get("deleted_at")
        cli.close()


# ==================================================
# Documents
# ==================================================
class TestVendorDocuments:
    def test_add_and_remove_document(self, admin_headers, created_vendor):
        vid = created_vendor["id"]
        r = requests.post(f"{API}/vendors/{vid}/documents",
                          json={"label": "TEST_GST_Cert", "url": "https://example.com/gst.pdf", "kind": "gst_certificate"},
                          headers=admin_headers)
        assert r.status_code == 200
        doc_id = r.json()["id"]
        # verify via get vendor
        r2 = requests.get(f"{API}/vendors/{vid}", headers=admin_headers)
        docs = r2.json().get("documents") or []
        assert any(d["id"] == doc_id for d in docs)
        # delete
        r3 = requests.delete(f"{API}/vendors/{vid}/documents/{doc_id}", headers=admin_headers)
        assert r3.status_code == 200
        r4 = requests.get(f"{API}/vendors/{vid}", headers=admin_headers)
        docs2 = r4.json().get("documents") or []
        assert not any(d["id"] == doc_id for d in docs2)


# ==================================================
# Ratings
# ==================================================
class TestVendorRatings:
    def test_ratings_average(self, admin_headers, created_vendor):
        vid = created_vendor["id"]
        # first rating: all 4
        r1 = requests.post(f"{API}/vendors/{vid}/rate",
                           json={"quality": 4, "timeliness": 4, "cost": 4, "communication": 4, "comment": "TEST_r1"},
                           headers=admin_headers)
        assert r1.status_code == 200
        assert r1.json()["overall"] == 4.0
        # second rating: all 5
        r2 = requests.post(f"{API}/vendors/{vid}/rate",
                           json={"quality": 5, "timeliness": 5, "cost": 5, "communication": 5, "comment": "TEST_r2"},
                           headers=admin_headers)
        assert r2.status_code == 200
        # aggregate should be (4 + 5)/2 = 4.5
        r3 = requests.get(f"{API}/vendors/{vid}", headers=admin_headers)
        assert r3.status_code == 200
        assert abs(r3.json().get("rating", 0) - 4.5) < 0.01


# ==================================================
# Vendor Bills
# ==================================================
class TestVendorBills:
    def test_create_bill_computes_totals(self, admin_headers, created_vendor):
        payload = {
            "vendor_id": created_vendor["id"],
            "bill_date": "2026-01-10",
            "due_date": "2026-12-31",
            "items": [{"description": "Wardrobe", "quantity": 2, "rate": 25000}],
            "tax_rate": 18, "tds_rate": 1,
            "notes": "TEST_bill_1",
        }
        r = requests.post(f"{API}/vendor-bills", json=payload, headers=admin_headers)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["subtotal"] == 50000
        assert b["tax_amount"] == 9000
        assert b["tds_amount"] == 500
        assert b["total"] == 58500
        assert b["outstanding"] == 58500
        assert b["status"] == "received"
        # store for downstream tests
        TestVendorBills.bill_id = b["id"]

    def test_patch_bill_recomputes(self, admin_headers):
        bid = TestVendorBills.bill_id
        r = requests.patch(f"{API}/vendor-bills/{bid}",
                           json={"items": [{"description": "Wardrobe", "quantity": 1, "rate": 25000}]},
                           headers=admin_headers)
        assert r.status_code == 200
        b = r.json()
        assert b["subtotal"] == 25000
        assert b["total"] == 25000 + 4500 - 250  # 29250
        assert b["total"] == 29250

    def test_patch_bill_invalid_status(self, admin_headers):
        bid = TestVendorBills.bill_id
        r = requests.patch(f"{API}/vendor-bills/{bid}",
                           json={"status": "made_up"}, headers=admin_headers)
        assert r.status_code == 400

    def test_delete_unpaid_bill_hard(self, admin_headers, created_vendor):
        # create a throwaway bill and hard-delete it
        p = {"vendor_id": created_vendor["id"], "bill_date": "2026-01-11",
             "items": [{"description": "x", "quantity": 1, "rate": 100}]}
        r = requests.post(f"{API}/vendor-bills", json=p, headers=admin_headers)
        bid = r.json()["id"]
        r2 = requests.delete(f"{API}/vendor-bills/{bid}", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json().get("deleted") is True
        r3 = requests.get(f"{API}/vendor-bills/{bid}", headers=admin_headers)
        assert r3.status_code == 404


@pytest.fixture(scope="module")
def payment_bill(admin_headers, created_vendor):
    """Dedicated bill (total=29250) for the payment tests, isolated from bill-class state."""
    p = {
        "vendor_id": created_vendor["id"],
        "bill_date": "2026-01-10",
        "due_date": "2026-12-31",
        "items": [{"description": "PayTest", "quantity": 1, "rate": 25000}],
        "tax_rate": 18, "tds_rate": 1,
    }
    r = requests.post(f"{API}/vendor-bills", json=p, headers=admin_headers)
    assert r.status_code == 200
    return r.json()


# ==================================================
# Vendor Payments (journal entry integration)
# ==================================================
class TestVendorPayments:
    def test_create_payment_creates_je(self, admin_headers, created_vendor, bank_account, payment_bill):
        bid = payment_bill["id"]
        # First: partial payment 10000
        p = {
            "vendor_id": created_vendor["id"],
            "amount": 10000,
            "payment_date": "2026-01-12",
            "paid_from_account_id": bank_account["id"],
            "payment_method": "bank_transfer",
            "bill_ids": [bid],
            "reference": "TEST_p1",
        }
        r = requests.post(f"{API}/vendor-payments", json=p, headers=admin_headers)
        assert r.status_code == 200, r.text
        pmt = r.json()
        assert pmt["bill_splits"].get(bid) == 10000
        assert pmt.get("journal_entry_id")
        # verify JE exists, balanced 2 lines
        je_r = requests.get(f"{API}/journal-entries?vendor_id={created_vendor['id']}", headers=admin_headers)
        assert je_r.status_code == 200
        jes = [j for j in je_r.json() if j.get("source") == "vendor_payment" and j.get("id") == pmt["journal_entry_id"]]
        assert len(jes) == 1
        je = jes[0]
        assert len(je["lines"]) == 2
        dr = sum(l["debit"] for l in je["lines"])
        cr = sum(l["credit"] for l in je["lines"])
        assert abs(dr - cr) < 0.01 and abs(dr - 10000) < 0.01

        # bill should be partially_paid now
        r2 = requests.get(f"{API}/vendor-bills/{bid}", headers=admin_headers)
        assert r2.json()["status"] == "partially_paid"
        assert r2.json()["paid_amount"] == 10000

    def test_fifo_settlement_no_bill_ids(self, admin_headers, created_vendor, bank_account, payment_bill):
        # Pay a large amount, FIFO across all open bills of this vendor.
        p = {
            "vendor_id": created_vendor["id"],
            "amount": 25000,
            "payment_date": "2026-01-13",
            "paid_from_account_id": bank_account["id"],
            "payment_method": "bank_transfer",
        }
        r = requests.post(f"{API}/vendor-payments", json=p, headers=admin_headers)
        assert r.status_code == 200
        pmt = r.json()
        # bill_splits should distribute across open bills up to the amount
        assert pmt["bill_splits"], "FIFO should settle at least one bill"
        total_split = sum(pmt["bill_splits"].values())
        assert abs(total_split + pmt.get("unallocated", 0) - 25000) < 0.01
        assert pmt.get("journal_entry_id")


# ==================================================
# Ledger
# ==================================================
class TestVendorLedger:
    def test_ledger_running_balance(self, admin_headers, created_vendor):
        r = requests.get(f"{API}/vendors/{created_vendor['id']}/ledger", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert "entries" in d
        for k in ("total_billed", "total_paid", "outstanding"):
            assert k in d
        # totals identity
        assert abs(d["outstanding"] - (d["total_billed"] - d["total_paid"])) < 0.01
        # running balance last entry equals outstanding
        if d["entries"]:
            assert abs(d["entries"][-1]["balance"] - d["outstanding"]) < 0.01


# ==================================================
# Performance
# ==================================================
class TestVendorPerformance:
    def test_performance_score(self, admin_headers, created_vendor):
        r = requests.get(f"{API}/vendors/{created_vendor['id']}/performance", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert 0 <= d["performance_score"] <= 100
        assert "tasks" in d and "ratings" in d and "financial" in d


# ==================================================
# RBAC
# ==================================================
class TestVendorRBAC:
    def test_designer_read_ok_write_forbidden(self, role_tokens, created_vendor, bank_account):
        h = _headers(role_tokens["Designer"])
        assert requests.get(f"{API}/vendors", headers=h).status_code == 200
        r = requests.post(f"{API}/vendors", json={"name": "TEST_d"}, headers=h)
        assert r.status_code == 403
        r2 = requests.post(f"{API}/vendor-bills",
                           json={"vendor_id": created_vendor["id"], "bill_date": "2026-01-01", "items": []},
                           headers=h)
        assert r2.status_code == 403
        r3 = requests.post(f"{API}/vendor-payments",
                           json={"vendor_id": created_vendor["id"], "amount": 10,
                                 "payment_date": "2026-01-01", "paid_from_account_id": bank_account["id"]},
                           headers=h)
        assert r3.status_code == 403

    def test_employee_read_ok_create_forbidden(self, role_tokens):
        h = _headers(role_tokens["Employee"])
        assert requests.get(f"{API}/vendors", headers=h).status_code == 200
        r = requests.post(f"{API}/vendors", json={"name": "TEST_e"}, headers=h)
        assert r.status_code == 403

    def test_hr_forbidden_read(self, role_tokens):
        h = _headers(role_tokens["HR"])
        r = requests.get(f"{API}/vendors", headers=h)
        assert r.status_code == 403

    def test_accountant_full_access(self, role_tokens, created_vendor, bank_account):
        h = _headers(role_tokens["Accountant"])
        assert requests.get(f"{API}/vendors", headers=h).status_code == 200
        # create vendor
        r = requests.post(f"{API}/vendors",
                          json={"name": "TEST_Acc_Vendor", "agency_type": "supplier"},
                          headers=h)
        assert r.status_code == 200
        vid = r.json()["id"]
        # bill
        rb = requests.post(f"{API}/vendor-bills",
                           json={"vendor_id": vid, "bill_date": "2026-01-15",
                                 "items": [{"description": "x", "quantity": 1, "rate": 500}]},
                           headers=h)
        assert rb.status_code == 200
        # payment
        rp = requests.post(f"{API}/vendor-payments",
                           json={"vendor_id": vid, "amount": 100, "payment_date": "2026-01-16",
                                 "paid_from_account_id": bank_account["id"]},
                           headers=h)
        assert rp.status_code == 200
