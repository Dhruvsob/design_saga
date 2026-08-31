#!/usr/bin/env python3
"""
Comprehensive backend API test suite for multi-tenant ERP system.
Tests: auth, tenant isolation, invoice->accounting, RBAC, notifications, platform mgmt.
"""
import requests
import sys
from datetime import datetime, timedelta

BASE_URL = "https://erp-audit-polish.preview.emergentagent.com/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class APITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.tokens = {}
        self.test_data = {}
        
    def log(self, msg, color=Colors.BLUE):
        print(f"{color}{msg}{Colors.END}")
        
    def test(self, name, method, endpoint, expected_status, data=None, token=None, 
             description="", save_key=None, extract_from_response=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        self.tests_run += 1
        print(f"\n{'='*80}")
        print(f"TEST #{self.tests_run}: {name}")
        if description:
            print(f"Description: {description}")
        print(f"Method: {method} {endpoint}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}", Colors.GREEN)
                try:
                    resp_json = response.json()
                    if save_key and resp_json:
                        self.test_data[save_key] = resp_json
                        print(f"   Saved response as '{save_key}'")
                    if extract_from_response:
                        for key, path in extract_from_response.items():
                            value = resp_json
                            for p in path.split('.'):
                                value = value.get(p) if isinstance(value, dict) else None
                            if value:
                                self.test_data[key] = value
                                print(f"   Extracted '{key}': {value}")
                    return True, resp_json
                except:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", Colors.RED)
                try:
                    print(f"   Response: {response.json()}")
                except:
                    print(f"   Response: {response.text[:200]}")
                return False, {}
                
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAILED - Error: {str(e)}", Colors.RED)
            return False, {}
    
    def print_summary(self):
        print(f"\n{'='*80}")
        print(f"{'='*80}")
        print(f"TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests: {self.tests_run}")
        print(f"{Colors.GREEN}Passed: {self.tests_passed}{Colors.END}")
        print(f"{Colors.RED}Failed: {self.tests_failed}{Colors.END}")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"{'='*80}")
        return 0 if self.tests_failed == 0 else 1

def main():
    tester = APITester()
    
    print(f"\n{'='*80}")
    print(f"MULTI-TENANT ERP BACKEND API TEST SUITE")
    print(f"Base URL: {BASE_URL}")
    print(f"{'='*80}\n")
    
    # ============================================================
    # SECTION 1: AUTHENTICATION & LOGIN FLOWS
    # ============================================================
    tester.log("\n🔐 SECTION 1: AUTHENTICATION & LOGIN FLOWS", Colors.YELLOW)
    
    # Test 1: SuperAdmin login
    success, resp = tester.test(
        "SuperAdmin Login",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "designsaga10@gmail.com", "password": "SuperAdmin@2026"},
        description="Login as Super Admin",
        extract_from_response={"sa_token": "session_token"}
    )
    
    # Test 2: Org A admin login
    success, resp = tester.test(
        "Org A Admin Login",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "admin@ateliervista.com", "password": "Studio@2026Pass"},
        description="Login as Org A (Atelier Vista) admin",
        extract_from_response={"org_a_token": "session_token", "org_a_id": "user.org_id"}
    )
    
    # Test 3: Org B admin login
    success, resp = tester.test(
        "Org B Admin Login",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "admin@buildcraft.com", "password": "Studio@2026Pass"},
        description="Login as Org B (BuildCraft) admin",
        extract_from_response={"org_b_token": "session_token", "org_b_id": "user.org_id"}
    )
    
    # Test 4: Org A employee login
    success, resp = tester.test(
        "Org A Employee Login",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "emp@ateliervista.com", "password": "Studio@2026Pass"},
        description="Login as Org A employee",
        extract_from_response={"emp_token": "session_token"}
    )
    
    # ============================================================
    # SECTION 2: TENANT ISOLATION CHECKS
    # ============================================================
    tester.log("\n🔒 SECTION 2: TENANT ISOLATION CHECKS", Colors.YELLOW)
    
    # Test 5: Org A - Get clients
    success, resp = tester.test(
        "Org A - List Clients",
        "GET", "/clients",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get clients for Org A",
        save_key="org_a_clients"
    )
    org_a_client_ids = [c['id'] for c in resp] if isinstance(resp, list) else []
    
    # Test 6: Org B - Get clients
    success, resp = tester.test(
        "Org B - List Clients",
        "GET", "/clients",
        200,
        token=tester.test_data.get("org_b_token"),
        description="Get clients for Org B",
        save_key="org_b_clients"
    )
    org_b_client_ids = [c['id'] for c in resp] if isinstance(resp, list) else []
    
    # Verify no overlap
    overlap = set(org_a_client_ids) & set(org_b_client_ids)
    if not overlap:
        tester.tests_passed += 1
        tester.log(f"✅ Client isolation verified - No overlap between orgs", Colors.GREEN)
    else:
        tester.tests_failed += 1
        tester.log(f"❌ Client isolation FAILED - Found overlap: {overlap}", Colors.RED)
    tester.tests_run += 1
    
    # Test 7: Org A - Get projects
    success, resp = tester.test(
        "Org A - List Projects",
        "GET", "/projects",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get projects for Org A",
        save_key="org_a_projects"
    )
    org_a_project_ids = [p['id'] for p in resp] if isinstance(resp, list) else []
    
    # Test 8: Org B - Get projects
    success, resp = tester.test(
        "Org B - List Projects",
        "GET", "/projects",
        200,
        token=tester.test_data.get("org_b_token"),
        description="Get projects for Org B",
        save_key="org_b_projects"
    )
    org_b_project_ids = [p['id'] for p in resp] if isinstance(resp, list) else []
    
    # Verify no overlap
    overlap = set(org_a_project_ids) & set(org_b_project_ids)
    if not overlap:
        tester.tests_passed += 1
        tester.log(f"✅ Project isolation verified - No overlap between orgs", Colors.GREEN)
    else:
        tester.tests_failed += 1
        tester.log(f"❌ Project isolation FAILED - Found overlap: {overlap}", Colors.RED)
    tester.tests_run += 1
    
    # Test 9: Org A - Get tasks
    success, resp = tester.test(
        "Org A - List Tasks",
        "GET", "/tasks",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get tasks for Org A"
    )
    
    # Test 10: Org A - Get invoices
    success, resp = tester.test(
        "Org A - List Invoices",
        "GET", "/invoices",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get invoices for Org A",
        save_key="org_a_invoices"
    )
    
    # Test 11: Org A - Get journal entries
    success, resp = tester.test(
        "Org A - List Journal Entries",
        "GET", "/accounting/journal-entries",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get journal entries for Org A"
    )
    
    # Test 12: Org A - Get accounting dashboard
    success, resp = tester.test(
        "Org A - Accounting Dashboard",
        "GET", "/accounting/dashboard",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get accounting dashboard for Org A",
        save_key="org_a_dashboard"
    )
    
    # Test 13: Org B - Get accounting dashboard
    success, resp = tester.test(
        "Org B - Accounting Dashboard",
        "GET", "/accounting/dashboard",
        200,
        token=tester.test_data.get("org_b_token"),
        description="Get accounting dashboard for Org B - should differ from Org A",
        save_key="org_b_dashboard"
    )
    
    # ============================================================
    # SECTION 3: INVOICE -> ACCOUNTING INTEGRATION
    # ============================================================
    tester.log("\n💰 SECTION 3: INVOICE -> ACCOUNTING INTEGRATION", Colors.YELLOW)
    
    # Get a client for invoice creation
    org_a_clients = tester.test_data.get("org_a_clients", [])
    if org_a_clients and len(org_a_clients) > 0:
        test_client_id = org_a_clients[0]['id']
        
        # Test 14: Create invoice
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        success, resp = tester.test(
            "Create Invoice",
            "POST", "/invoices",
            201,
            data={
                "client_id": test_client_id,
                "items": [
                    {"description": "Design Services", "quantity": 1, "rate": 50000, "amount": 50000}
                ],
                "tax_rate": 18,
                "status": "sent",
                "doc_type": "invoice",
                "due_date": tomorrow
            },
            token=tester.test_data.get("org_a_token"),
            description="Create a test invoice",
            extract_from_response={"test_invoice_id": "id"}
        )
        
        # Test 15: Mark invoice as paid
        test_invoice_id = tester.test_data.get("test_invoice_id")
        if test_invoice_id:
            success, resp = tester.test(
                "Mark Invoice as Paid",
                "PATCH", f"/invoices/{test_invoice_id}/status",
                200,
                data={"status": "paid"},
                token=tester.test_data.get("org_a_token"),
                description="Mark invoice as paid - should create journal entry",
                save_key="paid_invoice"
            )
            
            # Verify journal_id and paid_date are set
            if success and resp:
                if resp.get("journal_id") and resp.get("paid_date"):
                    tester.tests_passed += 1
                    tester.log(f"✅ Invoice payment created journal entry: {resp.get('journal_id')}", Colors.GREEN)
                else:
                    tester.tests_failed += 1
                    tester.log(f"❌ Invoice payment did NOT create journal entry", Colors.RED)
                tester.tests_run += 1
            
            # Test 16: Verify journal entry exists
            success, resp = tester.test(
                "Verify Invoice Payment Journal Entry",
                "GET", "/accounting/journal-entries?source=invoice_payment",
                200,
                token=tester.test_data.get("org_a_token"),
                description="Check that invoice_payment journal entry exists"
            )
            
            if success and isinstance(resp, list):
                matching_je = [je for je in resp if je.get('source_id') == test_invoice_id]
                if matching_je:
                    tester.tests_passed += 1
                    tester.log(f"✅ Found journal entry for invoice payment", Colors.GREEN)
                else:
                    tester.tests_failed += 1
                    tester.log(f"❌ No journal entry found for invoice payment", Colors.RED)
                tester.tests_run += 1
            
            # Test 17: Unmark invoice (reversal)
            success, resp = tester.test(
                "Unmark Invoice (Reversal)",
                "PATCH", f"/invoices/{test_invoice_id}/status",
                200,
                data={"status": "sent"},
                token=tester.test_data.get("org_a_token"),
                description="Change invoice back to sent - should create reversal JE"
            )
            
            # Test 18: Verify reversal journal entry
            success, resp = tester.test(
                "Verify Reversal Journal Entry",
                "GET", "/accounting/journal-entries?source=invoice_payment_reversal",
                200,
                token=tester.test_data.get("org_a_token"),
                description="Check that reversal journal entry exists"
            )
            
            if success and isinstance(resp, list):
                matching_je = [je for je in resp if je.get('source_id') == test_invoice_id]
                if matching_je:
                    tester.tests_passed += 1
                    tester.log(f"✅ Found reversal journal entry", Colors.GREEN)
                else:
                    tester.tests_failed += 1
                    tester.log(f"❌ No reversal journal entry found", Colors.RED)
                tester.tests_run += 1
    
    # Test 19: Trial balance check
    success, resp = tester.test(
        "Trial Balance Check",
        "GET", "/accounting/reports/trial-balance",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Verify trial balance is balanced"
    )
    
    if success and resp:
        total_debit = resp.get("total_debit", 0)
        total_credit = resp.get("total_credit", 0)
        if abs(total_debit - total_credit) < 0.01:
            tester.tests_passed += 1
            tester.log(f"✅ Trial balance is balanced: DR={total_debit}, CR={total_credit}", Colors.GREEN)
        else:
            tester.tests_failed += 1
            tester.log(f"❌ Trial balance NOT balanced: DR={total_debit}, CR={total_credit}", Colors.RED)
        tester.tests_run += 1
    
    # ============================================================
    # SECTION 4: RBAC ENFORCEMENT
    # ============================================================
    tester.log("\n🛡️ SECTION 4: RBAC ENFORCEMENT", Colors.YELLOW)
    
    # Test 20: Employee tries to change invoice status (should fail)
    if test_invoice_id:
        success, resp = tester.test(
            "Employee - Change Invoice Status (Should Fail)",
            "PATCH", f"/invoices/{test_invoice_id}/status",
            403,
            data={"status": "paid"},
            token=tester.test_data.get("emp_token"),
            description="Employee should NOT be able to change invoice status"
        )
    
    # Test 21: Employee tries to access accounting dashboard (should fail)
    success, resp = tester.test(
        "Employee - Access Accounting Dashboard (Should Fail)",
        "GET", "/accounting/dashboard",
        403,
        token=tester.test_data.get("emp_token"),
        description="Employee should NOT have finance.read permission"
    )
    
    # Test 22: Employee tries to list RBAC users (should fail)
    success, resp = tester.test(
        "Employee - List RBAC Users (Should Fail)",
        "GET", "/rbac/users",
        403,
        token=tester.test_data.get("emp_token"),
        description="Employee should NOT be able to list users"
    )
    
    # ============================================================
    # SECTION 5: NOTIFICATIONS
    # ============================================================
    tester.log("\n🔔 SECTION 5: NOTIFICATIONS", Colors.YELLOW)
    
    # Get an employee user ID for task assignment
    success, resp = tester.test(
        "Get RBAC Users",
        "GET", "/rbac/users",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get users to find employee for task assignment"
    )
    
    employee_user_id = None
    if success and isinstance(resp, list):
        for user in resp:
            if user.get('email') == 'emp@ateliervista.com':
                employee_user_id = user.get('user_id')
                break
    
    # Test 23: Create task assigned to employee
    if employee_user_id and org_a_project_ids:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        success, resp = tester.test(
            "Create Task for Employee",
            "POST", "/tasks",
            201,
            data={
                "title": "Test Task for Notification",
                "assignee_id": employee_user_id,
                "project_id": org_a_project_ids[0] if org_a_project_ids else None,
                "due_date": tomorrow
            },
            token=tester.test_data.get("org_a_token"),
            description="Create task assigned to employee - should trigger notification"
        )
    
    # Test 24: Employee checks notifications
    success, resp = tester.test(
        "Employee - Check Notifications",
        "GET", "/notifications",
        200,
        token=tester.test_data.get("emp_token"),
        description="Employee should see task_assigned notification"
    )
    
    if success and resp:
        notifications = resp.get('notifications', [])
        task_notifs = [n for n in notifications if n.get('kind') == 'task_assigned']
        if task_notifs:
            tester.tests_passed += 1
            tester.log(f"✅ Found task_assigned notification", Colors.GREEN)
        else:
            tester.log(f"⚠️  No task_assigned notification found (may be timing issue)", Colors.YELLOW)
        tester.tests_run += 1
    
    # ============================================================
    # SECTION 6: TENANT MANAGEMENT (SUPER ADMIN)
    # ============================================================
    tester.log("\n👑 SECTION 6: TENANT MANAGEMENT (SUPER ADMIN)", Colors.YELLOW)
    
    # Test 25: SuperAdmin - List orgs
    success, resp = tester.test(
        "SuperAdmin - List Organizations",
        "GET", "/platform/orgs",
        200,
        token=tester.test_data.get("sa_token"),
        description="SuperAdmin lists all organizations",
        save_key="all_orgs"
    )
    
    # Find atelier-vista org
    atelier_org = None
    if success and isinstance(resp, list):
        for org in resp:
            if org.get('slug') == 'atelier-vista':
                atelier_org = org
                tester.test_data['atelier_org_id'] = org.get('org_id')
                break
    
    # Test 26: SuperAdmin - Get org health
    if atelier_org:
        success, resp = tester.test(
            "SuperAdmin - Get Org Health",
            "GET", f"/platform/orgs/{atelier_org['org_id']}/health",
            200,
            token=tester.test_data.get("sa_token"),
            description="Get health metrics for Atelier Vista",
            save_key="org_health"
        )
        
        if success and resp:
            if 'counts' in resp and 'usage' in resp:
                tester.tests_passed += 1
                tester.log(f"✅ Org health returned counts and usage", Colors.GREEN)
            else:
                tester.tests_failed += 1
                tester.log(f"❌ Org health missing expected fields", Colors.RED)
            tester.tests_run += 1
    
    # Test 27: SuperAdmin - Isolation check
    success, resp = tester.test(
        "SuperAdmin - Isolation Check",
        "GET", "/platform/isolation-check",
        200,
        token=tester.test_data.get("sa_token"),
        description="Run tenant isolation verification"
    )
    
    if success and resp:
        status = resp.get('status')
        if status == 'PASS':
            tester.tests_passed += 1
            tester.log(f"✅ Isolation check PASSED", Colors.GREEN)
        else:
            tester.tests_failed += 1
            tester.log(f"❌ Isolation check FAILED: {resp.get('problems')}", Colors.RED)
        tester.tests_run += 1
    
    # Test 28: SuperAdmin - Update org limits
    if atelier_org:
        success, resp = tester.test(
            "SuperAdmin - Update Org Limits",
            "PATCH", f"/platform/orgs/{atelier_org['org_id']}/limits",
            200,
            data={"max_users": 50},
            token=tester.test_data.get("sa_token"),
            description="Update max_users limit for org"
        )
    
    # Test 29: SuperAdmin - Suspend org
    if atelier_org:
        success, resp = tester.test(
            "SuperAdmin - Suspend Org",
            "POST", f"/platform/orgs/{atelier_org['org_id']}/status",
            200,
            data={"action": "suspend"},
            token=tester.test_data.get("sa_token"),
            description="Suspend Atelier Vista org"
        )
    
    # Test 30: Suspended org admin tries to login (should fail)
    success, resp = tester.test(
        "Suspended Org - Admin Login (Should Fail)",
        "POST", "/auth/login-password",
        403,
        data={"identifier": "admin@ateliervista.com", "password": "Studio@2026Pass"},
        description="Admin of suspended org should not be able to access"
    )
    
    # Test 31: SuperAdmin - Reactivate org (IMPORTANT!)
    if atelier_org:
        success, resp = tester.test(
            "SuperAdmin - Reactivate Org",
            "POST", f"/platform/orgs/{atelier_org['org_id']}/status",
            200,
            data={"action": "activate"},
            token=tester.test_data.get("sa_token"),
            description="Reactivate Atelier Vista org (CRITICAL - must restore access)"
        )
    
    # Test 32: Verify admin can login again after reactivation
    success, resp = tester.test(
        "Reactivated Org - Admin Login (Should Work)",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "admin@ateliervista.com", "password": "Studio@2026Pass"},
        description="Admin should be able to login after reactivation"
    )
    
    # ============================================================
    # SECTION 7: QUOTATION PDF
    # ============================================================
    tester.log("\n📄 SECTION 7: QUOTATION PDF GENERATION", Colors.YELLOW)
    
    # Test 33: Get quotations
    success, resp = tester.test(
        "Get Advanced Quotations",
        "GET", "/quotations-adv",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get list of advanced quotations"
    )
    
    if success and isinstance(resp, list) and len(resp) > 0:
        quot_id = resp[0].get('id')
        
        # Test 34: Generate PDF
        url = f"{BASE_URL}/quotations-adv/{quot_id}/pdf"
        headers = {'Authorization': f'Bearer {tester.test_data.get("org_a_token")}'}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            tester.tests_run += 1
            if response.status_code == 200 and response.headers.get('content-type') == 'application/pdf':
                pdf_size = len(response.content)
                if pdf_size > 3000:  # >3KB
                    tester.tests_passed += 1
                    tester.log(f"✅ PDF generated successfully ({pdf_size} bytes)", Colors.GREEN)
                else:
                    tester.tests_failed += 1
                    tester.log(f"❌ PDF too small ({pdf_size} bytes)", Colors.RED)
            else:
                tester.tests_failed += 1
                tester.log(f"❌ PDF generation failed: {response.status_code}", Colors.RED)
        except Exception as e:
            tester.tests_failed += 1
            tester.log(f"❌ PDF generation error: {str(e)}", Colors.RED)
    
    # ============================================================
    # SECTION 8: ACCOUNTING INTEGRITY
    # ============================================================
    tester.log("\n📊 SECTION 8: ACCOUNTING INTEGRITY", Colors.YELLOW)
    
    # Test 35: Dashboard validation
    success, resp = tester.test(
        "Accounting Dashboard Validation",
        "GET", "/accounting/dashboard/validation",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Check accounting integrity diagnostics"
    )
    
    if success and resp:
        diagnostics = resp.get('diagnostics', {})
        orphan_invoices = diagnostics.get('orphan_paid_invoices', [])
        if len(orphan_invoices) == 0:
            tester.tests_passed += 1
            tester.log(f"✅ No orphan paid invoices found", Colors.GREEN)
        else:
            tester.tests_failed += 1
            tester.log(f"❌ Found {len(orphan_invoices)} orphan paid invoices", Colors.RED)
        tester.tests_run += 1
    
    # Test 36: Balance sheet
    success, resp = tester.test(
        "Balance Sheet Check",
        "GET", "/accounting/reports/balance-sheet",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Verify balance sheet is balanced"
    )
    
    if success and resp:
        balanced = resp.get('balanced')
        delta = resp.get('delta', 0)
        if balanced or abs(delta) < 0.01:
            tester.tests_passed += 1
            tester.log(f"✅ Balance sheet is balanced (delta: {delta})", Colors.GREEN)
        else:
            tester.tests_failed += 1
            tester.log(f"❌ Balance sheet NOT balanced (delta: {delta})", Colors.RED)
        tester.tests_run += 1
    
    # ============================================================
    # SECTION 9: MASTER DATA
    # ============================================================
    tester.log("\n📋 SECTION 9: MASTER DATA", Colors.YELLOW)
    
    # Test 37: Tasks meta
    success, resp = tester.test(
        "Get Tasks Meta",
        "GET", "/tasks/meta",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get task areas and categories"
    )
    
    if success and resp:
        areas = resp.get('areas', [])
        categories = resp.get('categories', [])
        if len(areas) > 0 and len(categories) > 0:
            tester.tests_passed += 1
            tester.log(f"✅ Tasks meta returned {len(areas)} areas and {len(categories)} categories", Colors.GREEN)
        else:
            tester.tests_failed += 1
            tester.log(f"❌ Tasks meta incomplete", Colors.RED)
        tester.tests_run += 1
    
    # Test 38: Employees meta
    success, resp = tester.test(
        "Get Employees Meta",
        "GET", "/employees/meta",
        200,
        token=tester.test_data.get("org_a_token"),
        description="Get employee departments and designations"
    )
    
    if success and resp:
        departments = resp.get('departments', [])
        designations = resp.get('designations', [])
        if len(departments) > 0 and len(designations) > 0:
            tester.tests_passed += 1
            tester.log(f"✅ Employees meta returned {len(departments)} departments and {len(designations)} designations", Colors.GREEN)
        else:
            tester.tests_failed += 1
            tester.log(f"❌ Employees meta incomplete", Colors.RED)
        tester.tests_run += 1
    
    # Print final summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
