"""Phase C — Accounting deep upgrade.

Covers:
- Financial Year helpers + `/accounting/fy/list`
- FY / date-range params on P&L, Trial Balance, Balance Sheet, Cash Flow
- Unified per-entity ledgers (client/vendor/employee/project) with running balance
- Dashboard Validation admin-only diff report
- Income/Expense JEs carry client/vendor/employee links
"""
import os
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
def bank_id(admin):
    for a in requests.get(f"{API}/accounts", headers=admin).json():
        if a.get("is_bank") or a.get("name") == "Cash":
            return a["id"]
    pytest.skip("no bank account")


@pytest.fixture(scope="module")
def income_acc(admin):
    for a in requests.get(f"{API}/accounts", headers=admin).json():
        if a.get("type") == "income":
            return a["id"]
    pytest.skip("no income account")


# ---------------------------------------------------------------
# 1. FY list endpoint
# ---------------------------------------------------------------
def test_fy_list(admin):
    r = requests.get(f"{API}/accounting/fy/list", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert "current" in d
    assert isinstance(d["choices"], list) and len(d["choices"]) >= 5
    curr = [c for c in d["choices"] if c["is_current"]]
    assert len(curr) == 1
    # Each choice has label / from / to
    assert all({"label", "from", "to"} <= set(c) for c in d["choices"])


# ---------------------------------------------------------------
# 2. Reports honour FY / date-range
# ---------------------------------------------------------------
def test_pl_with_fy(admin):
    r = requests.get(f"{API}/accounting/reports/pl?fy=2025-26", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["from"] == "2025-04-01" and d["to"] == "2026-03-31"
    assert d["period_label"] == "FY 2025-26"


def test_pl_with_custom_range(admin):
    r = requests.get(f"{API}/accounting/reports/pl?from_date=2025-01-01&to_date=2025-12-31",
                     headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["from"] == "2025-01-01" and d["to"] == "2025-12-31"


def test_balance_sheet_with_fy(admin):
    r = requests.get(f"{API}/accounting/reports/balance-sheet?fy=2025-26", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["as_of"] == "2026-03-31"


def test_cash_flow_with_fy(admin):
    r = requests.get(f"{API}/accounting/reports/cash-flow?fy=2025-26", headers=admin)
    assert r.status_code == 200


def test_trial_balance_with_fy(admin):
    r = requests.get(f"{API}/accounting/reports/trial-balance?fy=2025-26", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["as_of"] == "2026-03-31"


# ---------------------------------------------------------------
# 3. Income endpoint accepts employee_id + vendor_id
# ---------------------------------------------------------------
def test_income_carries_all_entities(admin, bank_id, income_acc):
    """POST /accounting/income now supports vendor_id + employee_id and
    the resulting JE keeps those fields for entity ledger lookups."""
    today = datetime.now(timezone.utc).date().isoformat()

    # Grab any existing employee for the link (may not have one on fresh DB)
    emps = requests.get(f"{API}/employees", headers=admin).json()
    emp_id = emps[0]["id"] if emps else None
    vendors = requests.get(f"{API}/vendors", headers=admin).json()
    vid = vendors[0]["id"] if vendors else None

    payload = {
        "date": today, "amount": 1234.0,
        "income_account_id": income_acc, "bank_account_id": bank_id,
        "payment_method": "cash", "notes": "phase-c-entity-tag test",
    }
    if emp_id: payload["employee_id"] = emp_id
    if vid: payload["vendor_id"] = vid

    r = requests.post(f"{API}/accounting/income", headers=admin, json=payload)
    assert r.status_code == 200, r.text
    je = r.json()
    if emp_id: assert je.get("employee_id") == emp_id
    if vid: assert je.get("vendor_id") == vid


# ---------------------------------------------------------------
# 4. Per-entity ledger: opening + inflow + outflow + closing + running balance
# ---------------------------------------------------------------
def test_client_ledger_structure(admin):
    clients = requests.get(f"{API}/clients", headers=admin).json()
    if not clients:
        pytest.skip("no clients")
    cid = clients[0]["id"]
    r = requests.get(f"{API}/accounting/ledger/client/{cid}?fy=2025-26",
                     headers=admin)
    assert r.status_code == 200
    d = r.json()
    # New enterprise shape
    assert {"opening_balance", "inflow", "outflow", "closing_balance",
            "net_movement", "entries", "period"} <= set(d)
    assert d["entity_type"] == "client"
    # Period label reflects the FY we asked for
    assert d["period"]["label"] == "FY 2025-26"
    # Every entry has running balance + inflow/outflow split
    for e in d["entries"]:
        assert "balance" in e and "inflow" in e and "outflow" in e


def test_vendor_ledger_shape(admin):
    vendors = requests.get(f"{API}/vendors", headers=admin).json()
    if not vendors:
        pytest.skip("no vendors")
    vid = vendors[0]["id"]
    r = requests.get(f"{API}/accounting/ledger/vendor/{vid}", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["entity_type"] == "vendor"
    assert "closing_balance" in d


def test_employee_ledger_shape(admin):
    emps = requests.get(f"{API}/employees", headers=admin).json()
    if not emps:
        pytest.skip("no employees")
    eid = emps[0]["id"]
    r = requests.get(f"{API}/accounting/ledger/employee/{eid}", headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["entity_type"] == "employee"


def test_project_ledger_includes_pl(admin):
    projs = requests.get(f"{API}/projects", headers=admin).json()
    if not projs:
        pytest.skip("no projects")
    pid = projs[0]["id"]
    r = requests.get(f"{API}/accounting/ledger/project/{pid}", headers=admin)
    assert r.status_code == 200
    d = r.json()
    # Project ledger also has revenue / expense / profit + milestones
    assert {"revenue", "expense", "profit", "milestones"} <= set(d)


def test_ledger_running_balance_math(admin, bank_id, income_acc):
    """opening + inflow - outflow == closing (rounded 2dp)."""
    clients = requests.get(f"{API}/clients", headers=admin).json()
    if not clients:
        pytest.skip("no clients")
    cid = clients[0]["id"]
    # Post an income tagged to this client so there's at least one entry
    today = datetime.now(timezone.utc).date().isoformat()
    requests.post(f"{API}/accounting/income", headers=admin, json={
        "date": today, "amount": 5000.0,
        "income_account_id": income_acc, "bank_account_id": bank_id,
        "client_id": cid, "payment_method": "cash",
    })
    r = requests.get(f"{API}/accounting/ledger/client/{cid}", headers=admin)
    d = r.json()
    expected_close = round(d["opening_balance"] + d["inflow"] - d["outflow"], 2)
    assert abs(expected_close - d["closing_balance"]) < 0.01


# ---------------------------------------------------------------
# 5. Dashboard Validation — admin-only diff report
# ---------------------------------------------------------------
def test_validation_report(admin):
    r = requests.get(f"{API}/accounting/dashboard/validation?fy=2025-26",
                     headers=admin)
    assert r.status_code == 200
    d = r.json()
    # Shape asserts
    assert {"accounting", "legacy", "difference", "diagnostics",
            "recommendation", "period"} <= set(d)
    assert "income" in d["accounting"]
    assert "match_within_1pc" in d["difference"]
    # Recommendation text should be present and non-empty
    assert isinstance(d["recommendation"], str) and len(d["recommendation"]) > 5


def test_validation_forbidden_for_non_admin():
    """Pending user (`newbie_tok`) should get 403."""
    r = requests.get(f"{API}/accounting/dashboard/validation",
                     headers=_h("newbie_tok"))
    assert r.status_code in (403, 401)
