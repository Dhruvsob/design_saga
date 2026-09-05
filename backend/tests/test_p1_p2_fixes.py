"""Tests for P1/P2 fixes:
- Vendor Bill soft-cancel reverses commission JE (P1)
- Balance Sheet imbalance detection + reconcile endpoint (P2)
- Object-storage-backed logo upload (P2)
"""
import os
import base64
import pytest
import requests
from datetime import datetime, timezone

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN_TOK = "stable_testtok_do_not_delete"


def _h(tok=ADMIN_TOK):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin():
    return _h()


@pytest.fixture(scope="module")
def bank_account_id(admin):
    r = requests.get(f"{API}/accounts", headers=admin)
    assert r.status_code == 200
    for a in r.json():
        if a.get("is_bank") or a.get("name") == "Cash":
            return a["id"]
    return r.json()[0]["id"]


# ============================================================
# P1: Vendor Bill soft-cancel reverses commission JE
# ============================================================
def test_bill_soft_cancel_reverses_received_commission(admin, bank_account_id):
    """Full flow: create vendor + bill + payment (soft-cancel path) + receive
    commission, then cancel the bill → expect a reversal JE and the commission
    row to be marked 'reversed'."""
    today = datetime.now(timezone.utc).date().isoformat()
    v = requests.post(f"{API}/vendors", headers=admin,
                      json={"name": "REV_P1_VENDOR", "agency_type": "vendor"}).json()
    vid = v["id"]
    try:
        # 10% commission
        requests.patch(f"{API}/vendors/{vid}/commercial", headers=admin,
                       json={"applicable": True, "type": "percentage",
                             "percentage": 10})
        bill = requests.post(f"{API}/vendor-bills", headers=admin,
                             json={"vendor_id": vid, "bill_date": today,
                                   "items": [{"description": "x", "quantity": 1,
                                              "rate": 50000}],
                                   "tax_rate": 0, "tds_rate": 0}).json()
        bill_id = bill["id"]
        # Add a payment so hard-delete is blocked → soft cancel path
        requests.post(f"{API}/vendor-payments", headers=admin,
                      json={"vendor_id": vid, "amount": 10000,
                            "payment_date": today,
                            "payment_method": "bank_transfer",
                            "paid_from_account_id": bank_account_id,
                            "bill_ids": [bill_id]})
        # Receive commission (posts DR Bank / CR Income JE for ₹5000)
        r = requests.post(f"{API}/vendors/{vid}/commissions/receive",
                          headers=admin,
                          json={"amount": 5000, "received_date": today,
                                "bank_account_id": bank_account_id,
                                "payment_method": "bank_transfer"})
        assert r.status_code == 200
        original_je = r.json()["journal_entry_id"]

        # Sanity: commission row is 'received' with no reversal yet
        rows = requests.get(f"{API}/vendors/{vid}/commissions", headers=admin).json()
        row = next(x for x in rows if x["bill_id"] == bill_id)
        assert row["status"] == "received"
        assert not row.get("reversal_je_id")

        # Cancel the bill (soft-cancel because it has payments)
        r2 = requests.delete(f"{API}/vendor-bills/{bill_id}", headers=admin)
        assert r2.status_code == 200
        assert r2.json().get("cancelled") is True

        # Commission row should now be 'reversed' with a reversal_je_id
        rows = requests.get(f"{API}/vendors/{vid}/commissions", headers=admin).json()
        row = next(x for x in rows if x["bill_id"] == bill_id)
        assert row["status"] == "reversed", f"expected reversed, got {row['status']}"
        assert row.get("reversal_je_id")
        assert row["reversal_je_id"] != original_je

        # Reversal JE should be DR Income / CR Bank and balanced
        jes = requests.get(f"{API}/journal-entries",
                           headers=admin,
                           params={"source": "commission_reversal"}).json()
        rev_je = next(e for e in jes if e["id"] == row["reversal_je_id"])
        assert abs(sum(l["debit"] for l in rev_je["lines"])
                   - sum(l["credit"] for l in rev_je["lines"])) < 0.01
        # DR side must be an income account (the reversal debits income)
        dr_line = next(l for l in rev_je["lines"] if l["debit"] > 0)
        assert dr_line["account_type"] == "income"
        assert dr_line["debit"] == 5000

        # Idempotent: cancelling again does not create another reversal
        requests.delete(f"{API}/vendor-bills/{bill_id}", headers=admin)
        jes2 = requests.get(f"{API}/journal-entries",
                            headers=admin,
                            params={"source": "commission_reversal"}).json()
        matching = [e for e in jes2 if e.get("source_id") == row["id"]]
        assert len(matching) == 1

        # Commission ledger should exclude the reversed row from totals
        ledger = requests.get(f"{API}/vendors/{vid}/commission-ledger",
                              headers=admin).json()
        assert ledger["totals"]["total_earned"] == 0
        assert ledger["totals"]["total_received"] == 0
    finally:
        requests.delete(f"{API}/vendors/{vid}", headers=admin)


# ============================================================
# P2: Balance-Sheet imbalance detection + reconcile
# ============================================================
def test_balance_sheet_exposes_delta_and_reconciles(admin):
    bs = requests.get(f"{API}/accounting/reports/balance-sheet",
                      headers=admin).json()
    # New shape must include delta + unbalanced_journal_entries
    assert "delta" in bs
    assert "unbalanced_journal_entries" in bs
    assert isinstance(bs["unbalanced_journal_entries"], list)

    if bs["balanced"]:
        # Nothing to reconcile.
        r = requests.post(f"{API}/accounting/reports/balance-sheet/reconcile",
                          headers=admin)
        assert r.status_code == 200
        assert r.json()["adjusted"] is False
        return

    # Unbalanced → reconcile should adjust and re-check.
    r = requests.post(f"{API}/accounting/reports/balance-sheet/reconcile",
                      headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["adjusted"] is True
    assert d["adjustment_account_id"]

    bs2 = requests.get(f"{API}/accounting/reports/balance-sheet",
                       headers=admin).json()
    assert bs2["balanced"] is True
    assert abs(bs2["delta"]) < 0.01


# ============================================================
# P2: Logo upload via object storage
# ============================================================
def test_logo_upload_to_object_storage(admin):
    # 1×1 transparent PNG
    png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00"
        b"\x0bIDATx\x9cc\xfa\xcf\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00"
        b"\x00\x00IEND\xaeB`\x82"
    ).decode()
    data_url = f"data:image/png;base64,{png}"

    r = requests.post(f"{API}/org/current/logo", headers=admin,
                      json={"logo_data_url": data_url})
    assert r.status_code == 200, r.text
    j = r.json()
    # Response should indicate object-storage path, not the raw data URL.
    assert j["ok"] is True
    assert j["logo_url"].startswith("/api/org/logo/")
    assert j["storage"] and j["storage"]["path"]
    assert j["storage"]["mime"] == "image/png"

    # Org branding now points to the proxy URL.
    org = requests.get(f"{API}/org/current", headers=admin).json()
    assert org["branding"]["logo_url"] == j["logo_url"]

    # Public download works without auth.
    dl = requests.get(f"{BASE}{j['logo_url']}")
    assert dl.status_code == 200
    assert "image/png" in dl.headers.get("content-type", "")
    assert len(dl.content) > 0


def test_logo_upload_rejects_bad_mime(admin):
    """A text/plain data URL should be rejected."""
    bad = "data:text/plain;base64," + base64.b64encode(b"hello").decode()
    r = requests.post(f"{API}/org/current/logo", headers=admin,
                      json={"logo_data_url": bad})
    assert r.status_code == 400


def test_logo_upload_rejects_oversize(admin):
    """A > 2MB data URL should be rejected before the object-storage call."""
    huge = "data:image/png;base64," + "A" * 3_000_000
    r = requests.post(f"{API}/org/current/logo", headers=admin,
                      json={"logo_data_url": huge})
    assert r.status_code == 413
