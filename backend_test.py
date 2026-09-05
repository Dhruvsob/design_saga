"""Comprehensive backend testing for Design Saga ERP Accounting Module.

Tests all P1/P2/P3 features + edge cases requested by main agent.

Run with:
    python3 /app/backend_test.py
"""
import os
import sys
import json
import requests
import uuid
from datetime import date, timedelta

# Use public endpoint
BASE = "https://finance-corrections.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@designsaga.com"
ADMIN_PASSWORD = "Admin@123"
SUPERADMIN_EMAIL = "designsaga10@gmail.com"
SUPERADMIN_PASSWORD = "Admin@123"
ACCOUNTANT_EMAIL = "acct@test.com"
ACCOUNTANT_PASSWORD = "Acct@1234"


class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def login(self, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
        """Login and return session with Bearer token."""
        s = requests.Session()
        r = s.post(f"{BASE}/auth/login-password",
                   json={"identifier": email, "password": password})
        r.raise_for_status()
        body = r.json()
        tok = body["session_token"]
        s.headers["Authorization"] = f"Bearer {tok}"
        return s, body

    def run_test(self, name, test_func):
        """Run a single test and track results."""
        self.tests_run += 1
        print(f"\n{'='*60}")
        print(f"TEST {self.tests_run}: {name}")
        print('='*60)
        try:
            test_func()
            self.tests_passed += 1
            print(f"✅ PASS: {name}")
        except AssertionError as e:
            self.tests_failed += 1
            self.failures.append({"test": name, "error": str(e), "type": "assertion"})
            print(f"❌ FAIL: {name}")
            print(f"   Error: {e}")
        except Exception as e:
            self.tests_failed += 1
            self.failures.append({"test": name, "error": str(e), "type": "exception"})
            print(f"❌ ERROR: {name}")
            print(f"   Exception: {e}")
            import traceback
            traceback.print_exc()

    def print_summary(self):
        """Print final test summary."""
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print('='*60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failures:
            print(f"\n{'='*60}")
            print("FAILURES:")
            print('='*60)
            for i, f in enumerate(self.failures, 1):
                print(f"\n{i}. {f['test']}")
                print(f"   Type: {f['type']}")
                print(f"   Error: {f['error']}")
        
        return 0 if self.tests_failed == 0 else 1


# Initialize test runner
runner = TestRunner()


# ==================================================
# EDGE CASE TESTS (Critical)
# ==================================================

def test_edge_case_reverse_then_repay_no_duplicate():
    """Edge case (a): Reverse a JE, then re-mark invoice as paid.
    Should NOT create duplicate JE (idempotency check filters reversed=true)."""
    s, _ = runner.login()
    
    # Create client + invoice
    cli = s.post(f"{BASE}/clients", json={"name": f"EdgeClient-{uuid.uuid4().hex[:6]}"}).json()
    inv = s.post(f"{BASE}/invoices", json={
        "client_id": cli["id"], "client_name": cli["name"],
        "items": [{"description": "Test", "qty": 1, "rate": 5000}],
        "subtotal": 5000, "total": 5000, "issue_date": date.today().isoformat(),
    }).json()
    
    # Mark paid → creates JE
    r = s.patch(f"{BASE}/invoices/{inv['id']}/status", json={"status": "paid"})
    r.raise_for_status()
    inv_paid = r.json()
    je_id_1 = inv_paid["journal_id"]
    assert je_id_1, "First payment should create JE"
    
    # Reverse the JE
    r = s.post(f"{BASE}/journal-entries/{je_id_1}/reverse")
    r.raise_for_status()
    
    # Reload invoice → should be 'sent' again
    inv_after_reverse = s.get(f"{BASE}/invoices/{inv['id']}").json()
    assert inv_after_reverse["status"] == "sent", "Invoice should be 'sent' after reversal"
    assert not inv_after_reverse.get("journal_id"), "journal_id should be cleared"
    
    # Re-mark as paid → should create NEW JE (not duplicate)
    r = s.patch(f"{BASE}/invoices/{inv['id']}/status", json={"status": "paid"})
    r.raise_for_status()
    inv_repaid = r.json()
    je_id_2 = inv_repaid["journal_id"]
    assert je_id_2, "Second payment should create JE"
    assert je_id_2 != je_id_1, "Should be a NEW JE, not the reversed one"
    
    # Verify the new JE is NOT reversed
    je2 = s.get(f"{BASE}/journal-entries/{je_id_2}").json()
    assert not je2.get("reversed"), "New JE should not be marked as reversed"
    
    # Verify only ONE active (non-reversed) JE exists for this invoice
    all_jes = s.get(f"{BASE}/journal-entries?source=invoice_payment").json()
    active_jes = [j for j in all_jes if j.get("source_id") == inv["id"] and not j.get("reversed")]
    assert len(active_jes) == 1, f"Should have exactly 1 active JE, found {len(active_jes)}"
    
    print(f"   ✓ Idempotency check works: reversed JE filtered out, new JE created")


def test_edge_case_delete_linked_je_fails():
    """Edge case (b): DELETE on invoice_payment JE should 409 with 'linked transaction'."""
    s, _ = runner.login()
    
    # Create client + invoice + mark paid
    cli = s.post(f"{BASE}/clients", json={"name": f"DelClient-{uuid.uuid4().hex[:6]}"}).json()
    inv = s.post(f"{BASE}/invoices", json={
        "client_id": cli["id"], "client_name": cli["name"],
        "items": [{"description": "Test", "qty": 1, "rate": 3000}],
        "subtotal": 3000, "total": 3000, "issue_date": date.today().isoformat(),
    }).json()
    r = s.patch(f"{BASE}/invoices/{inv['id']}/status", json={"status": "paid"})
    r.raise_for_status()
    je_id = r.json()["journal_id"]
    
    # Try to DELETE the JE → should 409
    r = s.delete(f"{BASE}/journal-entries/{je_id}")
    assert r.status_code == 409, f"Expected 409, got {r.status_code}"
    assert "linked" in r.text.lower() or "reverse" in r.text.lower(), \
        f"Error message should mention 'linked' or 'reverse': {r.text}"
    
    print(f"   ✓ DELETE on linked JE correctly returns 409")


def test_edge_case_unbalanced_je_fails():
    """Edge case (c): POST unbalanced JE (debit != credit) should 400."""
    s, _ = runner.login()
    
    # Get two accounts
    accs = s.get(f"{BASE}/accounts").json()
    bank = next((a for a in accs if a.get("is_bank")), accs[0])
    income = next((a for a in accs if a["type"] == "income"), accs[1])
    
    # Try to post unbalanced JE
    r = s.post(f"{BASE}/journal-entries", json={
        "date": date.today().isoformat(),
        "narration": "Unbalanced test",
        "lines": [
            {"account_id": bank["id"], "debit": 1000, "credit": 0, "description": "DR"},
            {"account_id": income["id"], "debit": 0, "credit": 500, "description": "CR"},
        ]
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    assert "balanced" in r.text.lower() or "debit" in r.text.lower(), \
        f"Error should mention 'balanced': {r.text}"
    
    print(f"   ✓ Unbalanced JE correctly returns 400")


# ==================================================
# P1 FEATURE TESTS
# ==================================================

def test_p1_payment_reversal_cascades():
    """P1: Payment reversal cascades to invoice (status + journal_id cleared)."""
    s, _ = runner.login()
    
    cli = s.post(f"{BASE}/clients", json={"name": f"P1Client-{uuid.uuid4().hex[:6]}"}).json()
    inv = s.post(f"{BASE}/invoices", json={
        "client_id": cli["id"], "client_name": cli["name"],
        "items": [{"description": "Work", "qty": 1, "rate": 8000}],
        "subtotal": 8000, "total": 8000, "issue_date": date.today().isoformat(),
    }).json()
    
    # Mark paid
    r = s.patch(f"{BASE}/invoices/{inv['id']}/status", json={"status": "paid"})
    r.raise_for_status()
    inv_paid = r.json()
    assert inv_paid["status"] == "paid"
    assert inv_paid.get("journal_id")
    je_id = inv_paid["journal_id"]
    
    # Reverse
    s.post(f"{BASE}/journal-entries/{je_id}/reverse").raise_for_status()
    
    # Verify cascade
    inv_after = s.get(f"{BASE}/invoices/{inv['id']}").json()
    assert inv_after["status"] == "sent", f"Expected 'sent', got {inv_after['status']}"
    assert not inv_after.get("journal_id"), "journal_id should be null"
    assert not inv_after.get("paid_date"), "paid_date should be null"
    
    print(f"   ✓ Payment reversal cascades correctly")


def test_p1_milestone_reversal_cascades():
    """P1: Milestone payment reversal cascades to milestone."""
    s, _ = runner.login()
    
    cli = s.post(f"{BASE}/clients", json={"name": f"MSClient-{uuid.uuid4().hex[:6]}"}).json()
    proj = s.post(f"{BASE}/projects", json={
        "name": f"MSProj-{uuid.uuid4().hex[:6]}", "client_id": cli["id"],
        "budget": 50000, "engagement_type": "consultancy"
    }).json()
    ms = s.post(f"{BASE}/projects/{proj['id']}/milestones", json={
        "project_id": proj["id"], "name": "Advance", "amount": 10000,
        "due_date": date.today().isoformat(),
    }).json()
    
    # Mark paid
    r = s.patch(f"{BASE}/milestones/{ms['id']}", json={"status": "paid", "amount": 10000})
    r.raise_for_status()
    ms_paid = r.json()
    je_id = ms_paid.get("journal_id")
    assert je_id, "Milestone should have journal_id after paid"
    
    # Reverse
    s.post(f"{BASE}/journal-entries/{je_id}/reverse").raise_for_status()
    
    # Verify cascade
    all_ms = s.get(f"{BASE}/projects/{proj['id']}/milestones").json()
    ms_after = next((m for m in all_ms if m["id"] == ms["id"]), None)
    assert ms_after, "Milestone should still exist"
    assert ms_after["status"] == "pending", f"Expected 'pending', got {ms_after['status']}"
    assert not ms_after.get("journal_id"), "journal_id should be null"
    
    print(f"   ✓ Milestone reversal cascades correctly")


def test_p1_rbac_finance_permissions():
    """P1: Accounting endpoints require finance.* permissions."""
    # Seed accountant user
    from tests.test_accounting_audit_fixes import seed_non_admin_user_via_db
    seed_non_admin_user_via_db()
    
    s, _ = runner.login(ACCOUNTANT_EMAIL, ACCOUNTANT_PASSWORD)
    
    # Accountant (has finance.*) should be able to create account
    r = s.post(f"{BASE}/accounts", json={
        "name": f"TestAcct-{uuid.uuid4().hex[:6]}",
        "type": "expense",
    })
    assert r.status_code == 200, f"Accountant should create account, got {r.status_code}: {r.text}"
    
    # Accountant should be able to create income
    accs = s.get(f"{BASE}/accounts").json()
    bank = next((a for a in accs if a.get("is_bank")), None)
    income = next((a for a in accs if a["type"] == "income"), None)
    assert bank and income, "Need bank and income accounts"
    
    r = s.post(f"{BASE}/accounting/income", json={
        "amount": 1000, "date": date.today().isoformat(),
        "bank_account_id": bank["id"], "income_account_id": income["id"],
        "payment_method": "bank_transfer", "notes": "Test income"
    })
    assert r.status_code == 200, f"Accountant should create income, got {r.status_code}: {r.text}"
    
    print(f"   ✓ RBAC: Accountant can use finance.* endpoints")


def test_p1_commission_receipt_balanced():
    """P1: Commission receipt creates balanced JE with project_id + vendor_id."""
    s, _ = runner.login()
    
    # Create vendor
    v = s.post(f"{BASE}/vendors", json={
        "name": f"CommVendor-{uuid.uuid4().hex[:6]}", "agency_type": "supplier",
    }).json()
    
    # Set commission config
    s.patch(f"{BASE}/vendors/{v['id']}/commercial", json={
        "applicable": True, "type": "percentage", "percentage": 5,
    }).raise_for_status()
    
    # Create project + bill
    cli = s.post(f"{BASE}/clients", json={"name": f"CommClient-{uuid.uuid4().hex[:6]}"}).json()
    proj = s.post(f"{BASE}/projects", json={
        "name": f"CommProj-{uuid.uuid4().hex[:6]}", "client_id": cli["id"],
        "budget": 100000, "engagement_type": "turnkey"
    }).json()
    
    bill = s.post(f"{BASE}/vendor-bills", json={
        "vendor_id": v["id"], "project_id": proj["id"],
        "bill_number": f"B-{uuid.uuid4().hex[:6]}",
        "bill_date": date.today().isoformat(),
        "items": [{"description": "Test", "qty": 1, "rate": 20000}],
        "subtotal": 20000, "total": 20000,
    })
    assert bill.status_code == 200, bill.text
    
    # Get commission
    comms = s.get(f"{BASE}/vendors/{v['id']}/commissions").json()
    assert comms, "Commission should be auto-created"
    assert comms[0]["amount"] == 1000  # 5% of 20000
    
    # Receive commission
    accs = s.get(f"{BASE}/accounts").json()
    bank = next((a for a in accs if a.get("is_bank")), None)
    assert bank, "Need bank account"
    
    r = s.post(f"{BASE}/vendors/{v['id']}/commissions/receive", json={
        "amount": 1000, "received_date": date.today().isoformat(),
        "bank_account_id": bank["id"], "payment_method": "bank_transfer",
    })
    r.raise_for_status()
    settle = r.json()
    je_id = settle["journal_entry_id"]
    
    # Verify JE
    je = s.get(f"{BASE}/journal-entries/{je_id}").json()
    total_d = sum(l["debit"] for l in je["lines"])
    total_c = sum(l["credit"] for l in je["lines"])
    assert round(total_d, 2) == round(total_c, 2) == 1000, f"JE not balanced: DR={total_d} CR={total_c}"
    assert je.get("project_id") == proj["id"], "JE should have project_id"
    assert je.get("vendor_id") == v["id"], "JE should have vendor_id"
    assert je.get("source") == "commission_income", "JE source should be commission_income"
    
    print(f"   ✓ Commission receipt creates balanced JE with project + vendor")


def test_p1_loan_deletion_archives():
    """P1: Loan deletion reverses disbursement JE and archives loan."""
    s, _ = runner.login()
    
    accs = s.get(f"{BASE}/accounts").json()
    bank = next((a for a in accs if a.get("is_bank")), None)
    assert bank, "Need bank account"
    
    # Create loan
    r = s.post(f"{BASE}/loans", json={
        "lender_name": f"TestBank-{uuid.uuid4().hex[:6]}",
        "principal": 50000, "interest_rate_pa": 10, "tenure_months": 12,
        "start_date": date.today().isoformat(),
        "disbursement_account_id": bank["id"],
    })
    r.raise_for_status()
    loan = r.json()
    loan_id = loan["id"]
    disb_je_id = loan["disbursement_journal_id"]
    
    # Verify JE exists
    je = s.get(f"{BASE}/journal-entries/{disb_je_id}").json()
    assert je and je.get("total") == 50000
    
    # Delete loan
    r = s.delete(f"{BASE}/loans/{loan_id}")
    r.raise_for_status()
    body = r.json()
    assert body.get("archived") is True, "Loan should be archived"
    
    # JE should still exist but marked reversed
    je2 = s.get(f"{BASE}/journal-entries/{disb_je_id}").json()
    assert je2 is not None, "JE should not be hard-deleted"
    assert je2.get("reversed") is True, "JE should be marked reversed"
    assert je2.get("reversal_je_id"), "JE should have reversal_je_id"
    
    # Loan hidden from default list
    default_list = s.get(f"{BASE}/loans").json()
    assert loan_id not in [l["id"] for l in default_list], "Archived loan should be hidden"
    
    # Visible with include_archived
    inc_list = s.get(f"{BASE}/loans?include_archived=1").json()
    assert loan_id in [l["id"] for l in inc_list], "Archived loan should appear with include_archived=1"
    
    print(f"   ✓ Loan deletion archives + reverses JE")


def test_p1_opening_balances():
    """P1: Trial Balance and Balance Sheet include opening balances."""
    s, _ = runner.login()
    
    tb = s.get(f"{BASE}/accounting/reports/trial-balance").json()
    bs = s.get(f"{BASE}/accounting/reports/balance-sheet").json()
    
    # Trial balance should be balanced
    assert abs(tb["total_debit"] - tb["total_credit"]) < 0.01, \
        f"TB not balanced: DR={tb['total_debit']} CR={tb['total_credit']}"
    
    # Balance sheet should be balanced
    assert bs["balanced"], f"BS not balanced: delta={bs['delta']}"
    assert abs(bs["delta"]) < 0.01, f"BS delta too large: {bs['delta']}"
    
    print(f"   ✓ Trial Balance balanced (DR=CR={tb['total_debit']})")
    print(f"   ✓ Balance Sheet balanced (delta={bs['delta']})")


# ==================================================
# P2 FEATURE TESTS
# ==================================================

def test_p2_daybook_filters_pagination():
    """P2: Journal-entries endpoint supports pagination + filters."""
    s, _ = runner.login()
    
    # Test pagination
    r = s.get(f"{BASE}/journal-entries?limit=5&offset=0").json()
    assert isinstance(r, dict) and "items" in r, "Should return paginated response"
    assert r["limit"] == 5
    assert "total" in r and "offset" in r
    
    # Test backward-compat (no pagination)
    r = s.get(f"{BASE}/journal-entries").json()
    assert isinstance(r, list), "Default should return array"
    
    # Test filters
    r = s.get(f"{BASE}/journal-entries?source=invoice_payment&limit=10&offset=0").json()
    assert isinstance(r, dict) and "items" in r
    
    # Test search
    r = s.get(f"{BASE}/journal-entries?q=payment&limit=10&offset=0").json()
    assert isinstance(r, dict) and "items" in r
    
    print(f"   ✓ Daybook supports pagination + filters")


def test_p2_today_collections():
    """P2: Today's Collections includes invoice_payment/milestone_payment."""
    s, _ = runner.login()
    
    # Create invoice and mark paid today
    cli = s.post(f"{BASE}/clients", json={"name": f"TdyClient-{uuid.uuid4().hex[:6]}"}).json()
    inv = s.post(f"{BASE}/invoices", json={
        "client_id": cli["id"], "client_name": cli["name"],
        "items": [{"description": "Work", "qty": 1, "rate": 5555}],
        "subtotal": 5555, "total": 5555, "issue_date": date.today().isoformat(),
    }).json()
    s.patch(f"{BASE}/invoices/{inv['id']}/status", json={"status": "paid"}).raise_for_status()
    
    # Check dashboard
    d = s.get(f"{BASE}/accounting/dashboard").json()
    tc = d["kpis"]["today_collections"]
    assert tc >= 5555, f"today_collections {tc} should include 5555"
    
    print(f"   ✓ Today's Collections includes invoice_payment (total={tc})")


def test_p2_outstanding():
    """P2: Outstanding includes unpaid invoices + pending milestones."""
    s, _ = runner.login()
    
    # Create unpaid invoice
    cli = s.post(f"{BASE}/clients", json={"name": f"OutClient-{uuid.uuid4().hex[:6]}"}).json()
    inv = s.post(f"{BASE}/invoices", json={
        "client_id": cli["id"], "client_name": cli["name"],
        "items": [{"description": "Work", "qty": 1, "rate": 7777}],
        "subtotal": 7777, "total": 7777, "issue_date": date.today().isoformat(),
    }).json()
    # Don't mark as paid
    
    # Create pending milestone
    proj = s.post(f"{BASE}/projects", json={
        "name": f"OutProj-{uuid.uuid4().hex[:6]}", "client_id": cli["id"],
        "budget": 50000, "engagement_type": "consultancy"
    }).json()
    ms = s.post(f"{BASE}/projects/{proj['id']}/milestones", json={
        "project_id": proj["id"], "name": "Pending", "amount": 8888,
        "due_date": date.today().isoformat(),
    }).json()
    # Don't mark as paid
    
    # Check dashboard
    d = s.get(f"{BASE}/accounting/dashboard").json()
    outstanding = d["kpis"]["outstanding"]
    # Should include at least our test amounts
    assert outstanding >= (7777 + 8888), \
        f"Outstanding {outstanding} should include invoice (7777) + milestone (8888)"
    
    print(f"   ✓ Outstanding includes unpaid invoices + pending milestones (total={outstanding})")


# ==================================================
# P3 FEATURE TESTS
# ==================================================

def test_p3_hide_inactive_accounts():
    """P3: Inactive accounts hidden by default, visible with include_inactive=1."""
    s, _ = runner.login()
    
    # Create account
    acc = s.post(f"{BASE}/accounts", json={
        "name": f"TestInactive-{uuid.uuid4().hex[:6]}",
        "type": "expense",
    }).json()
    acc_id = acc["id"]
    
    # Verify it appears in default list
    default_list = s.get(f"{BASE}/accounts").json()
    assert acc_id in [a["id"] for a in default_list], "New account should appear in default list"
    
    # Soft delete (deactivate)
    s.delete(f"{BASE}/accounts/{acc_id}").raise_for_status()
    
    # Should NOT appear in default list
    default_list2 = s.get(f"{BASE}/accounts").json()
    assert acc_id not in [a["id"] for a in default_list2], "Inactive account should be hidden"
    
    # Should appear with include_inactive=1
    inc_list = s.get(f"{BASE}/accounts?include_inactive=1").json()
    assert acc_id in [a["id"] for a in inc_list], "Inactive account should appear with include_inactive=1"
    
    print(f"   ✓ Inactive accounts hidden by default, visible with include_inactive=1")


def test_p3_auto_account_codes():
    """P3: Auto account codes by type (expense→4xxx, income→3xxx, etc)."""
    s, _ = runner.login()
    
    # Create expense account without code
    exp = s.post(f"{BASE}/accounts", json={
        "name": f"AutoExp-{uuid.uuid4().hex[:6]}",
        "type": "expense",
    }).json()
    assert exp["code"].startswith("4"), f"Expense code should start with 4, got {exp['code']}"
    
    # Create income account without code
    inc = s.post(f"{BASE}/accounts", json={
        "name": f"AutoInc-{uuid.uuid4().hex[:6]}",
        "type": "income",
    }).json()
    assert inc["code"].startswith("3"), f"Income code should start with 3, got {inc['code']}"
    
    # Create liability account without code
    liab = s.post(f"{BASE}/accounts", json={
        "name": f"AutoLiab-{uuid.uuid4().hex[:6]}",
        "type": "liability",
    }).json()
    assert liab["code"].startswith("2"), f"Liability code should start with 2, got {liab['code']}"
    
    print(f"   ✓ Auto account codes work (expense={exp['code']}, income={inc['code']}, liability={liab['code']})")


def test_p3_commission_vendor_report():
    """P3: Commission vendor-wise report."""
    s, _ = runner.login()
    
    # Get commission dashboard
    r = s.get(f"{BASE}/commissions/dashboard")
    assert r.status_code == 200, f"Commission dashboard should work, got {r.status_code}"
    dash = r.json()
    assert "totals" in dash or "top_vendors" in dash, "Dashboard should have totals or top_vendors"
    
    # Get commission report (all)
    r = s.get(f"{BASE}/commissions/report")
    assert r.status_code == 200, f"Commission report should work, got {r.status_code}"
    
    print(f"   ✓ Commission vendor-wise report works")


# ==================================================
# GENERAL CORRECTNESS
# ==================================================

def test_general_all_jes_balanced():
    """General: All JEs should have DR = CR."""
    s, _ = runner.login()
    
    # Get all JEs
    all_jes = s.get(f"{BASE}/journal-entries?limit=500&offset=0").json()
    items = all_jes.get("items", []) if isinstance(all_jes, dict) else all_jes
    
    unbalanced = []
    for je in items:
        total_d = sum(l.get("debit", 0) for l in je.get("lines", []))
        total_c = sum(l.get("credit", 0) for l in je.get("lines", []))
        if abs(total_d - total_c) > 0.01:
            unbalanced.append({
                "id": je.get("id"),
                "date": je.get("date"),
                "narration": je.get("narration"),
                "debit": total_d,
                "credit": total_c,
                "diff": round(total_d - total_c, 2)
            })
    
    assert len(unbalanced) == 0, f"Found {len(unbalanced)} unbalanced JEs: {unbalanced[:5]}"
    
    print(f"   ✓ All {len(items)} JEs are balanced (DR = CR)")


# ==================================================
# COMPANY SETTINGS TESTS (Bug Fix: SuperAdmin org fetch)
# ==================================================

def test_company_settings_superadmin_org_current():
    """Company Settings: SuperAdmin can fetch /api/org/current."""
    s, _ = runner.login(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)
    
    r = s.get(f"{BASE}/org/current")
    assert r.status_code == 200, f"SuperAdmin should access /org/current, got {r.status_code}: {r.text}"
    
    org = r.json()
    assert org is not None, "SuperAdmin should get org data"
    # Should have branding (even if default)
    assert "branding" in org, "Org should have branding field"
    
    print(f"   ✓ SuperAdmin can fetch /org/current (org_id={org.get('org_id')})")


def test_company_settings_admin_org_current():
    """Company Settings: Admin can fetch /api/org/current."""
    s, _ = runner.login(ADMIN_EMAIL, ADMIN_PASSWORD)
    
    r = s.get(f"{BASE}/org/current")
    assert r.status_code == 200, f"Admin should access /org/current, got {r.status_code}: {r.text}"
    
    org = r.json()
    assert org is not None, "Admin should get org data"
    assert "branding" in org, "Org should have branding field"
    
    print(f"   ✓ Admin can fetch /org/current (org_id={org.get('org_id')})")


def test_company_settings_superadmin_master_data():
    """Company Settings: SuperAdmin can fetch /api/master-data."""
    s, _ = runner.login(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)
    
    r = s.get(f"{BASE}/master-data")
    assert r.status_code == 200, f"SuperAdmin should access /master-data, got {r.status_code}: {r.text}"
    
    data = r.json()
    assert "kinds" in data, "Master data should have 'kinds' field"
    assert "data" in data, "Master data should have 'data' field"
    
    print(f"   ✓ SuperAdmin can fetch /master-data (kinds={len(data.get('kinds', {}))})")


def test_company_settings_admin_master_data():
    """Company Settings: Admin can fetch /api/master-data."""
    s, _ = runner.login(ADMIN_EMAIL, ADMIN_PASSWORD)
    
    r = s.get(f"{BASE}/master-data")
    assert r.status_code == 200, f"Admin should access /master-data, got {r.status_code}: {r.text}"
    
    data = r.json()
    assert "kinds" in data, "Master data should have 'kinds' field"
    assert "data" in data, "Master data should have 'data' field"
    
    print(f"   ✓ Admin can fetch /master-data (kinds={len(data.get('kinds', {}))})")


# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":
    print("="*60)
    print("DESIGN SAGA ERP - ACCOUNTING MODULE TEST SUITE")
    print("="*60)
    print(f"Backend URL: {BASE}")
    print(f"Admin: {ADMIN_EMAIL}")
    print("="*60)
    
    # Edge cases (Critical)
    runner.run_test("Edge Case: Reverse then re-pay (no duplicate JE)", 
                    test_edge_case_reverse_then_repay_no_duplicate)
    runner.run_test("Edge Case: DELETE linked JE fails with 409", 
                    test_edge_case_delete_linked_je_fails)
    runner.run_test("Edge Case: Unbalanced JE fails with 400", 
                    test_edge_case_unbalanced_je_fails)
    
    # P1 features
    runner.run_test("P1: Payment reversal cascades to invoice", 
                    test_p1_payment_reversal_cascades)
    runner.run_test("P1: Milestone reversal cascades to milestone", 
                    test_p1_milestone_reversal_cascades)
    runner.run_test("P1: RBAC uses finance.* permissions", 
                    test_p1_rbac_finance_permissions)
    runner.run_test("P1: Commission receipt creates balanced JE", 
                    test_p1_commission_receipt_balanced)
    runner.run_test("P1: Loan deletion archives + reverses JE", 
                    test_p1_loan_deletion_archives)
    runner.run_test("P1: Opening balances in Trial Balance & Balance Sheet", 
                    test_p1_opening_balances)
    
    # P2 features
    runner.run_test("P2: Daybook filters + pagination", 
                    test_p2_daybook_filters_pagination)
    runner.run_test("P2: Today's Collections includes invoice_payment", 
                    test_p2_today_collections)
    runner.run_test("P2: Outstanding includes invoices + milestones", 
                    test_p2_outstanding)
    
    # P3 features
    runner.run_test("P3: Hide inactive accounts by default", 
                    test_p3_hide_inactive_accounts)
    runner.run_test("P3: Auto account codes by type", 
                    test_p3_auto_account_codes)
    runner.run_test("P3: Commission vendor-wise report", 
                    test_p3_commission_vendor_report)
    
    # General correctness
    runner.run_test("General: All JEs balanced (DR = CR)", 
                    test_general_all_jes_balanced)
    
    # Company Settings (Bug Fix)
    runner.run_test("Company Settings: SuperAdmin can fetch /org/current", 
                    test_company_settings_superadmin_org_current)
    runner.run_test("Company Settings: Admin can fetch /org/current", 
                    test_company_settings_admin_org_current)
    runner.run_test("Company Settings: SuperAdmin can fetch /master-data", 
                    test_company_settings_superadmin_master_data)
    runner.run_test("Company Settings: Admin can fetch /master-data", 
                    test_company_settings_admin_master_data)
    
    # Print summary and exit
    sys.exit(runner.print_summary())
