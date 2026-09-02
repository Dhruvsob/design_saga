#!/usr/bin/env python3
"""
Test for employee_id collision bug fix in multi-tenant authentication.

BUG: employee_id is per-organisation (every org's first admin is DS0001), 
so it is NOT globally unique. The login endpoint used find_one() which 
always resolved to a single fixed user, so any OTHER tenant's admin 
logging in with their Employee ID + correct password was rejected.

FIX: The login endpoint now fetches ALL candidate users matching the 
identifier (email OR employee_id) and authenticates against whichever 
candidate's password verifies.

Test scenarios:
1. REGRESSION: Existing email logins still work
2. SETUP: Create TWO test orgs with colliding employee_ids (DS0001)
3. CORE FIX #1: Login with DS0001 + AlphaPass@123 => resolves to org A
4. CORE FIX #2: Login with DS0001 + BetaPass@456 => resolves to org B
5. CORE FIX #3: Login with DS0001 + wrong password => 401
6. EMAIL login for new admins also works
7. CLEANUP: Delete test orgs
"""
import requests
import sys
from typing import Optional, Dict, Any

BASE_URL = "https://erp-audit-polish.preview.emergentagent.com/api"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'

class EmployeeIDCollisionTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.sa_token: Optional[str] = None
        self.org_a_id: Optional[str] = None
        self.org_b_id: Optional[str] = None
        
    def log(self, msg: str, color: str = Colors.BLUE):
        print(f"{color}{msg}{Colors.END}")
        
    def test(self, name: str, method: str, endpoint: str, expected_status: int, 
             data: Optional[Dict] = None, token: Optional[str] = None, 
             description: str = "") -> tuple[bool, Dict[str, Any]]:
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            # Support both cookie and bearer token
            headers['Authorization'] = f'Bearer {token}'
        
        self.tests_run += 1
        print(f"\n{'='*80}")
        print(f"{Colors.CYAN}TEST #{self.tests_run}: {name}{Colors.END}")
        if description:
            print(f"Description: {description}")
        print(f"Method: {method} {endpoint}")
        if data:
            print(f"Payload: {data}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
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
                    return True, resp_json
                except Exception:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", Colors.RED)
                try:
                    error_detail = response.json()
                    print(f"   Response: {error_detail}")
                except Exception:
                    print(f"   Response: {response.text[:200]}")
                return False, {}
                
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAILED - Error: {str(e)}", Colors.RED)
            return False, {}
    
    def print_summary(self) -> int:
        print(f"\n{'='*80}")
        print(f"{'='*80}")
        print(f"{Colors.CYAN}EMPLOYEE_ID COLLISION FIX - TEST SUMMARY{Colors.END}")
        print(f"{'='*80}")
        print(f"Total Tests: {self.tests_run}")
        print(f"{Colors.GREEN}Passed: {self.tests_passed}{Colors.END}")
        print(f"{Colors.RED}Failed: {self.tests_failed}{Colors.END}")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"{'='*80}")
        return 0 if self.tests_failed == 0 else 1

def main():
    tester = EmployeeIDCollisionTester()
    
    print(f"\n{'='*80}")
    print(f"{Colors.CYAN}EMPLOYEE_ID COLLISION BUG FIX TEST{Colors.END}")
    print(f"Base URL: {BASE_URL}")
    print(f"{'='*80}\n")
    
    # ============================================================
    # SECTION 1: REGRESSION - Existing email logins still work
    # ============================================================
    tester.log("\n🔐 SECTION 1: REGRESSION - Existing Email Logins", Colors.YELLOW)
    
    # Test 1: Existing tenant A admin login (email)
    success, resp = tester.test(
        "Existing Tenant A Admin Login (Email)",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "admin@ateliervista.com", "password": "Studio@2026Pass"},
        description="Verify existing email login still works for Atelier Vista"
    )
    
    if success and resp:
        user = resp.get('user', {})
        org_id = user.get('org_id')
        email = user.get('email')
        if email == 'admin@ateliervista.com' and org_id == 'org_0b3c8fa4c93c':
            tester.log(f"   ✓ Correct user returned: {email}, org_id: {org_id}", Colors.GREEN)
        else:
            tester.log(f"   ✗ Unexpected user: {email}, org_id: {org_id}", Colors.RED)
    
    # Test 2: Existing tenant B admin login (email)
    success, resp = tester.test(
        "Existing Tenant B Admin Login (Email)",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "admin@buildcraft.com", "password": "Studio@2026Pass"},
        description="Verify existing email login still works for BuildCraft"
    )
    
    if success and resp:
        user = resp.get('user', {})
        org_id = user.get('org_id')
        email = user.get('email')
        if email == 'admin@buildcraft.com' and org_id == 'org_9debf8d3d3dc':
            tester.log(f"   ✓ Correct user returned: {email}, org_id: {org_id}", Colors.GREEN)
        else:
            tester.log(f"   ✗ Unexpected user: {email}, org_id: {org_id}", Colors.RED)
    
    # Test 3: Wrong password should fail
    success, resp = tester.test(
        "Existing Admin - Wrong Password (Should Fail)",
        "POST", "/auth/login-password",
        401,
        data={"identifier": "admin@ateliervista.com", "password": "WrongPassword123"},
        description="Verify wrong password returns 401 Invalid credentials"
    )
    
    # ============================================================
    # SECTION 2: SETUP - Create test orgs with colliding employee_ids
    # ============================================================
    tester.log("\n🏗️  SECTION 2: SETUP - Create Test Orgs", Colors.YELLOW)
    
    # Test 4: SuperAdmin login
    success, resp = tester.test(
        "SuperAdmin Login",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "designsaga10@gmail.com", "password": "SuperAdmin@2026"},
        description="Login as SuperAdmin to create test orgs"
    )
    
    if success and resp:
        tester.sa_token = resp.get('session_token')
        tester.log(f"   ✓ SuperAdmin token obtained", Colors.GREEN)
    else:
        tester.log(f"   ✗ Failed to get SuperAdmin token - cannot proceed", Colors.RED)
        return tester.print_summary()
    
    # Test 5: Create Test Org A (ZZ Collision OrgA)
    success, resp = tester.test(
        "Create Test Org A",
        "POST", "/platform/orgs",
        200,
        data={
            "name": "ZZ Collision OrgA",
            "admin_email": "colltest_a@example.com",
            "admin_name": "Coll A",
            "admin_password": "AlphaPass@123",
            "business_mode": "hybrid"
        },
        token=tester.sa_token,
        description="Create test org A with admin employee_id DS0001"
    )
    
    if success and resp:
        org_data = resp.get('org', {})
        tester.org_a_id = org_data.get('org_id')
        admin_uid = resp.get('admin_user_id')
        tester.log(f"   ✓ Org A created: {tester.org_a_id}, admin: {admin_uid}", Colors.GREEN)
    else:
        tester.log(f"   ✗ Failed to create Org A - cannot proceed", Colors.RED)
        return tester.print_summary()
    
    # Test 6: Create Test Org B (ZZ Collision OrgB)
    success, resp = tester.test(
        "Create Test Org B",
        "POST", "/platform/orgs",
        200,
        data={
            "name": "ZZ Collision OrgB",
            "admin_email": "colltest_b@example.com",
            "admin_name": "Coll B",
            "admin_password": "BetaPass@456",
            "business_mode": "hybrid"
        },
        token=tester.sa_token,
        description="Create test org B with admin employee_id DS0001 (collision!)"
    )
    
    if success and resp:
        org_data = resp.get('org', {})
        tester.org_b_id = org_data.get('org_id')
        admin_uid = resp.get('admin_user_id')
        tester.log(f"   ✓ Org B created: {tester.org_b_id}, admin: {admin_uid}", Colors.GREEN)
    else:
        tester.log(f"   ✗ Failed to create Org B - cannot proceed", Colors.RED)
        return tester.print_summary()
    
    # ============================================================
    # SECTION 3: CORE FIX - Employee ID collision resolves correctly
    # ============================================================
    tester.log("\n🎯 SECTION 3: CORE FIX - Employee ID Collision Resolution", Colors.YELLOW)
    
    # Test 7: CORE FIX #1 - Login with DS0001 + AlphaPass@123 => Org A
    success, resp = tester.test(
        "CORE FIX #1: DS0001 + AlphaPass@123 => Org A",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "DS0001", "password": "AlphaPass@123"},
        description="Employee ID DS0001 with Org A password should resolve to Org A admin"
    )
    
    if success and resp:
        user = resp.get('user', {})
        email = user.get('email')
        org_id = user.get('org_id')
        employee_id = user.get('employee_id')
        
        if email == 'colltest_a@example.com' and org_id == tester.org_a_id:
            tester.log(f"   ✓ CORRECT: Resolved to Org A admin", Colors.GREEN)
            tester.log(f"     Email: {email}, Org: {org_id}, Employee ID: {employee_id}", Colors.GREEN)
        else:
            tester.log(f"   ✗ WRONG: Expected Org A admin, got {email} from {org_id}", Colors.RED)
    
    # Test 8: CORE FIX #2 - Login with DS0001 + BetaPass@456 => Org B
    success, resp = tester.test(
        "CORE FIX #2: DS0001 + BetaPass@456 => Org B",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "DS0001", "password": "BetaPass@456"},
        description="Employee ID DS0001 with Org B password should resolve to Org B admin"
    )
    
    if success and resp:
        user = resp.get('user', {})
        email = user.get('email')
        org_id = user.get('org_id')
        employee_id = user.get('employee_id')
        
        if email == 'colltest_b@example.com' and org_id == tester.org_b_id:
            tester.log(f"   ✓ CORRECT: Resolved to Org B admin", Colors.GREEN)
            tester.log(f"     Email: {email}, Org: {org_id}, Employee ID: {employee_id}", Colors.GREEN)
        else:
            tester.log(f"   ✗ WRONG: Expected Org B admin, got {email} from {org_id}", Colors.RED)
    
    # Test 9: CORE FIX #3 - Login with DS0001 + wrong password => 401
    success, resp = tester.test(
        "CORE FIX #3: DS0001 + Wrong Password => 401",
        "POST", "/auth/login-password",
        401,
        data={"identifier": "DS0001", "password": "TotallyWrong@000"},
        description="Employee ID DS0001 with wrong password should return 401"
    )
    
    if success:
        tester.log(f"   ✓ Correctly rejected wrong password", Colors.GREEN)
    
    # ============================================================
    # SECTION 4: EMAIL LOGIN - New admins can also login via email
    # ============================================================
    tester.log("\n📧 SECTION 4: EMAIL LOGIN - New Admins", Colors.YELLOW)
    
    # Test 10: Org A admin login via email
    success, resp = tester.test(
        "Org A Admin - Email Login",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "colltest_a@example.com", "password": "AlphaPass@123"},
        description="Org A admin should be able to login via email"
    )
    
    if success and resp:
        user = resp.get('user', {})
        org_id = user.get('org_id')
        if org_id == tester.org_a_id:
            tester.log(f"   ✓ Email login successful for Org A", Colors.GREEN)
        else:
            tester.log(f"   ✗ Wrong org returned: {org_id}", Colors.RED)
    
    # Test 11: Org B admin login via email
    success, resp = tester.test(
        "Org B Admin - Email Login",
        "POST", "/auth/login-password",
        200,
        data={"identifier": "colltest_b@example.com", "password": "BetaPass@456"},
        description="Org B admin should be able to login via email"
    )
    
    if success and resp:
        user = resp.get('user', {})
        org_id = user.get('org_id')
        if org_id == tester.org_b_id:
            tester.log(f"   ✓ Email login successful for Org B", Colors.GREEN)
        else:
            tester.log(f"   ✗ Wrong org returned: {org_id}", Colors.RED)
    
    # ============================================================
    # SECTION 5: CLEANUP - Delete test orgs
    # ============================================================
    tester.log("\n🧹 SECTION 5: CLEANUP - Delete Test Orgs", Colors.YELLOW)
    
    # Test 12: Delete Org A
    if tester.org_a_id:
        success, resp = tester.test(
            "Delete Test Org A",
            "DELETE", f"/platform/orgs/{tester.org_a_id}?purge=true",
            200,
            token=tester.sa_token,
            description="Hard delete Org A and all its data"
        )
        
        if success and resp.get('purged'):
            tester.log(f"   ✓ Org A purged successfully", Colors.GREEN)
        elif success:
            tester.log(f"   ⚠ Org A deactivated but not purged", Colors.YELLOW)
    
    # Test 13: Delete Org B
    if tester.org_b_id:
        success, resp = tester.test(
            "Delete Test Org B",
            "DELETE", f"/platform/orgs/{tester.org_b_id}?purge=true",
            200,
            token=tester.sa_token,
            description="Hard delete Org B and all its data"
        )
        
        if success and resp.get('purged'):
            tester.log(f"   ✓ Org B purged successfully", Colors.GREEN)
        elif success:
            tester.log(f"   ⚠ Org B deactivated but not purged", Colors.YELLOW)
    
    # Print final summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
