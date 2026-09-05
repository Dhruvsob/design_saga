"""
Vendor Commission Management pytest suite (v2.4)

Covers:
- COA seed contains commission income accounts
- PATCH /vendors/{id}/commercial (percentage / fixed / slab)
- Auto-compute commission on bill create + update
- Delete bill cascades (drop pending / cancel received)
- min_purchase gate + effective_from/to window
- POST /vendors/{id}/commissions/receive → balanced JE, FIFO settlement, unallocated advance
- RBAC (finance.create for receive; vendors.read for list)
- Ledger reconciliation, dashboard, report + CSV
- Regression on vendor/bill/PL endpoints
"""
import os
import io
import csv
import pytest
import requests
from datetime import datetime, timezone

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN_TOK = "stable_testtok_do_not_delete"
PM_TOK = None  # ProjectManager token, resolved lazily via password login


def _h(tok=ADMIN_TOK):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin():
    return _h()


@pytest.fixture(scope="module")
def pm_token():
    r = requests.post(f"{API}/auth/login-password",
                      json={"identifier": "pmanager@ds.co", "password": "Test@1234"})
    if r.status_code != 200:
        pytest.skip("pmanager login failed")
    # try common shapes
    d = r.json()
    tok = d.get("session_token") or d.get("token") or (d.get("user") or {}).get("session_token")
    if not tok:
        # cookie-based? try /auth/me via cookie
        pytest.skip(f"no token in login response: {d}")
    return tok


@pytest.fixture(scope="module")
def bank_account_id(admin):
    r = requests.get(f"{API}/accounts", headers=admin)
    assert r.status_code == 200, r.text
    accts = r.json()
    for a in accts:
        if a.get("type") in ("bank", "cash") or "bank" in (a.get("name") or "").lower():
            return a["id"]
    # fallback: first account
    return accts[0]["id"]


@pytest.fixture(scope="module")
def vendor_id(admin):
    """Create a fresh test vendor for the entire module."""
    r = requests.post(f"{API}/vendors", headers=admin,
                      json={"name": "TEST_COMM_ACME", "agency_type": "vendor",
                            "category": "furniture", "email": "t@acme.co"})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    yield vid
    # cleanup: soft delete
    requests.delete(f"{API}/vendors/{vid}", headers=admin)


def _create_bill(vid, admin, qty=2, rate=25000, tax=18, tds=1, bill_date=None):
    bill_date = bill_date or datetime.now(timezone.utc).date().isoformat()
    r = requests.post(f"{API}/vendor-bills", headers=admin,
                      json={"vendor_id": vid,
                            "bill_date": bill_date,
                            "items": [{"description": "x", "quantity": qty, "rate": rate}],
                            "tax_rate": tax, "tds_rate": tds})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------- 1. COA seed ----------------------
def test_coa_has_commission_income_accounts(admin):
    r = requests.get(f"{API}/accounts", headers=admin)
    assert r.status_code == 200
    names = {a["name"] for a in r.json() if (a.get("type") == "income")}
    for expect in ("Vendor Commission Income", "Referral Income", "Incentive Income"):
        assert expect in names, f"{expect} missing from COA income accounts. Got: {names}"


# ---------------------- 2. Commercial config PATCH/GET ----------------------
def test_patch_commercial_percentage(admin, vendor_id):
    r = requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                       json={"applicable": True, "type": "percentage", "percentage": 10})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["recomputed_bills"] >= 0

    g = requests.get(f"{API}/vendors/{vendor_id}", headers=admin).json()
    assert g["commission"]["type"] == "percentage"
    assert g["commission"]["percentage"] == 10
    assert g["commission"]["applicable"] is True


# ---------------------- 3. Auto commission on bill create ----------------------
def test_bill_create_auto_commission_percentage(admin, vendor_id):
    bill = _create_bill(vendor_id, admin, qty=2, rate=25000, tax=18, tds=1)
    assert bill["subtotal"] == 50000
    r = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin)
    rows = [x for x in r.json() if x["bill_id"] == bill["id"]]
    assert len(rows) == 1
    row = rows[0]
    assert row["purchase_amount"] == 50000
    assert row["amount"] == 5000
    assert row["status"] == "pending"
    # keep bill id for later tests via module cache
    pytest.pct_bill_id = bill["id"]


# ---------------------- 4. Fixed / Slab types ----------------------
def test_fixed_type(admin, vendor_id):
    r = requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                       json={"applicable": True, "type": "fixed", "fixed_amount": 2000})
    assert r.status_code == 200
    rows = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin).json()
    row = next(x for x in rows if x["bill_id"] == pytest.pct_bill_id)
    assert row["amount"] == 2000


def test_slab_type(admin, vendor_id):
    r = requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                       json={"applicable": True, "type": "slab",
                             "slabs": [{"min_purchase": 0, "max_purchase": 100000,
                                        "percentage": 3}]})
    assert r.status_code == 200
    rows = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin).json()
    row = next(x for x in rows if x["bill_id"] == pytest.pct_bill_id)
    assert row["amount"] == 1500  # 50000 * 3%


# ---------------------- 5. Bill PATCH recomputes ----------------------
def test_bill_patch_recomputes_commission(admin, vendor_id):
    # switch back to 10% percentage
    requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                   json={"applicable": True, "type": "percentage", "percentage": 10})
    r = requests.patch(f"{API}/vendor-bills/{pytest.pct_bill_id}", headers=admin,
                       json={"items": [{"description": "x", "quantity": 1, "rate": 25000}]})
    assert r.status_code == 200, r.text
    assert r.json()["subtotal"] == 25000
    rows = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin).json()
    row = next(x for x in rows if x["bill_id"] == pytest.pct_bill_id)
    assert row["amount"] == 2500


# ---------------------- 6. Delete bill drops commission ----------------------
def test_delete_bill_drops_commission(admin, vendor_id):
    b = _create_bill(vendor_id, admin, qty=1, rate=10000)  # 10% => 1000
    rows = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin).json()
    assert any(x["bill_id"] == b["id"] for x in rows)
    r = requests.delete(f"{API}/vendor-bills/{b['id']}", headers=admin)
    assert r.status_code == 200
    rows = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin).json()
    assert not any(x["bill_id"] == b["id"] for x in rows)


# ---------------------- 7. min_purchase gate ----------------------
def test_min_purchase_gate(admin, vendor_id):
    r = requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                       json={"applicable": True, "type": "percentage",
                             "percentage": 10, "min_purchase": 100000})
    assert r.status_code == 200
    # existing 25000 bill should NOT have commission now
    rows = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin).json()
    assert not any(x["bill_id"] == pytest.pct_bill_id for x in rows)
    # restore
    requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                   json={"applicable": True, "type": "percentage", "percentage": 10})


# ---------------------- 8. effective_from window ----------------------
def test_effective_from_future(admin, vendor_id):
    r = requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                       json={"applicable": True, "type": "percentage",
                             "percentage": 10, "effective_from": "2099-01-01"})
    assert r.status_code == 200
    rows = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=admin).json()
    # No commissions in future window
    assert all(x.get("status") == "cancelled" or x["bill_id"] != pytest.pct_bill_id
               for x in rows) or len([x for x in rows if x["bill_id"] == pytest.pct_bill_id]) == 0
    # restore
    requests.patch(f"{API}/vendors/{vendor_id}/commercial", headers=admin,
                   json={"applicable": True, "type": "percentage", "percentage": 10})


# ---------------------- 9. Receive → JE + PL ----------------------
def test_receive_commission_creates_je(admin, vendor_id, bank_account_id):
    today = datetime.now(timezone.utc).date().isoformat()
    # ensure pct bill has 2500 pending commission
    r = requests.post(f"{API}/vendors/{vendor_id}/commissions/receive", headers=admin,
                      json={"amount": 2500, "received_date": today,
                            "bank_account_id": bank_account_id,
                            "payment_method": "bank_transfer"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["journal_entry_id"]
    assert d["unallocated"] < 0.5
    pytest.first_je = d["journal_entry_id"]

    # JE search
    jes = requests.get(f"{API}/journal-entries",
                       headers=admin,
                       params={"vendor_id": vendor_id,
                               "source": "commission_income"}).json()
    assert isinstance(jes, list) and len(jes) >= 1
    je = next(x for x in jes if x["id"] == d["journal_entry_id"])
    assert len(je["lines"]) == 2
    debit = sum(l["debit"] for l in je["lines"])
    credit = sum(l["credit"] for l in je["lines"])
    assert abs(debit - credit) < 0.01
    assert abs(debit - 2500) < 0.01
    # find bank + commission income lines
    names = {l["account_name"] for l in je["lines"]}
    assert "Vendor Commission Income" in names

    # P&L includes it
    pl = requests.get(f"{API}/accounting/reports/pl", headers=admin).json()
    inc_lines_str = str(pl)
    assert "Vendor Commission Income" in inc_lines_str


# ---------------------- 10. RBAC receive ----------------------
def test_receive_rbac_pm_forbidden(pm_token, vendor_id, bank_account_id):
    today = datetime.now(timezone.utc).date().isoformat()
    r = requests.post(f"{API}/vendors/{vendor_id}/commissions/receive",
                      headers=_h(pm_token),
                      json={"amount": 100, "received_date": today,
                            "bank_account_id": bank_account_id,
                            "payment_method": "bank_transfer"})
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


# ---------------------- 11. FIFO settlement + unallocated ----------------------
def test_fifo_and_unallocated(admin, bank_account_id):
    # fresh vendor with two bills each ₹50000 subtotal → 10% → 5000 commission each
    v = requests.post(f"{API}/vendors", headers=admin,
                      json={"name": "TEST_FIFO_VENDOR", "agency_type": "vendor"}).json()
    vid = v["id"]
    try:
        requests.patch(f"{API}/vendors/{vid}/commercial", headers=admin,
                       json={"applicable": True, "type": "percentage", "percentage": 10})
        b1 = _create_bill(vid, admin, qty=1, rate=50000, tax=0, tds=0,
                          bill_date="2025-01-01")
        b2 = _create_bill(vid, admin, qty=1, rate=50000, tax=0, tds=0,
                          bill_date="2025-02-01")
        today = datetime.now(timezone.utc).date().isoformat()
        # Pay 7000 → A fully(5000) + B partial(2000)
        r = requests.post(f"{API}/vendors/{vid}/commissions/receive", headers=admin,
                          json={"amount": 7000, "received_date": today,
                                "bank_account_id": bank_account_id,
                                "payment_method": "bank_transfer"})
        assert r.status_code == 200, r.text
        rows = {x["bill_id"]: x for x in
                requests.get(f"{API}/vendors/{vid}/commissions", headers=admin).json()}
        assert rows[b1["id"]]["status"] == "received"
        assert rows[b2["id"]]["status"] == "invoiced"
        assert abs(rows[b2["id"]]["received_amount"] - 2000) < 0.01

        # Pay 3000 → B fully received
        r2 = requests.post(f"{API}/vendors/{vid}/commissions/receive", headers=admin,
                           json={"amount": 3000, "received_date": today,
                                 "bank_account_id": bank_account_id,
                                 "payment_method": "bank_transfer"})
        assert r2.status_code == 200
        rows = {x["bill_id"]: x for x in
                requests.get(f"{API}/vendors/{vid}/commissions", headers=admin).json()}
        assert rows[b2["id"]]["status"] == "received"

        # Overpayment → unallocated
        r3 = requests.post(f"{API}/vendors/{vid}/commissions/receive", headers=admin,
                           json={"amount": 100000, "received_date": today,
                                 "bank_account_id": bank_account_id,
                                 "payment_method": "bank_transfer"})
        assert r3.status_code == 200
        assert abs(r3.json()["unallocated"] - 100000) < 0.01  # nothing pending
    finally:
        requests.delete(f"{API}/vendors/{vid}", headers=admin)


# ---------------------- 12. Ledger reconciliation ----------------------
def test_commission_ledger_reconciles(admin, vendor_id):
    r = requests.get(f"{API}/vendors/{vendor_id}/commission-ledger", headers=admin)
    assert r.status_code == 200
    t = r.json()["totals"]
    assert abs((t["total_earned"] - t["total_received"]) - t["pending"]) < 0.01


# ---------------------- 13. Dashboard ----------------------
def test_dashboard(admin):
    r = requests.get(f"{API}/commissions/dashboard", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert "totals" in d and "top_vendors" in d and "by_project" in d
    assert len(d["top_vendors"]) <= 10
    assert len(d["by_project"]) <= 20
    for k in ("total_earned", "total_received", "pending", "this_month"):
        assert k in d["totals"]


# ---------------------- 14. Report + CSV ----------------------
def test_report_and_csv(admin, vendor_id):
    r = requests.get(f"{API}/commissions/report", headers=admin,
                     params={"vendor_id": vendor_id})
    assert r.status_code == 200
    d = r.json()
    assert d["totals"]["count"] == len(d["rows"])

    r2 = requests.get(f"{API}/commissions/report.csv", headers=admin,
                      params={"vendor_id": vendor_id})
    assert r2.status_code == 200
    assert "text/csv" in r2.headers.get("content-type", "")
    assert "attachment" in r2.headers.get("content-disposition", "")
    assert "filename=" in r2.headers.get("content-disposition", "")
    lines = r2.text.splitlines()
    assert lines[0].startswith("bill_date,vendor,bill_number")


# ---------------------- 15. Regression ----------------------
def test_regression_endpoints(admin):
    for path in ("/vendors", "/vendor-bills",
                 "/accounting/reports/balance-sheet",
                 "/accounting/reports/cash-flow",
                 "/notifications"):
        r = requests.get(f"{API}{path}", headers=admin)
        assert r.status_code == 200, f"{path} regressed → {r.status_code} {r.text[:200]}"


# ---------------------- 16. RBAC read (client forbidden) ----------------------
def test_client_role_forbidden_on_read(admin, vendor_id):
    """Skip if we can't easily create a Client user — check spec-defined behavior."""
    # Create a client user
    import time as _t
    uniq = f"client_{int(_t.time())}"
    reg = requests.post(f"{API}/auth/register", headers=admin,
                        json={"email": f"{uniq}@ds.co", "password": "Test@1234",
                              "name": "Client Test", "role": "Client"})
    if reg.status_code not in (200, 201):
        pytest.skip(f"cannot register client user: {reg.status_code} {reg.text}")
    # Approve if needed
    login = requests.post(f"{API}/auth/login-password",
                          json={"identifier": f"{uniq}@ds.co", "password": "Test@1234"})
    if login.status_code != 200:
        pytest.skip(f"cannot login client user: {login.text}")
    d = login.json()
    tok = d.get("session_token") or d.get("token")
    if not tok:
        pytest.skip("no token")
    r = requests.get(f"{API}/vendors/{vendor_id}/commissions", headers=_h(tok))
    assert r.status_code == 403
