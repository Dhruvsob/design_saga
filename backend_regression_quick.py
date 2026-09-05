#!/usr/bin/env python3
"""
Quick backend regression test for Round 2 - Frontend focused testing.
Tests only the 3 critical backend APIs mentioned in review request.
"""
import requests
import sys

BASE_URL = "https://erp-audit-polish.preview.emergentagent.com/api"

def test_login_password():
    """Test POST /api/auth/login-password for all 4 accounts"""
    print("\n" + "="*80)
    print("BACKEND REGRESSION - LOGIN PASSWORD")
    print("="*80)
    
    accounts = [
        ("SuperAdmin", "designsaga10@gmail.com", "SuperAdmin@2026"),
        ("Org A Admin", "admin@ateliervista.com", "Studio@2026Pass"),
        ("Org A Employee", "emp@ateliervista.com", "Studio@2026Pass"),
        ("Org B Admin", "admin@buildcraft.com", "Studio@2026Pass"),
    ]
    
    tokens = {}
    all_passed = True
    
    for name, email, password in accounts:
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login-password",
                json={"identifier": email, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get("session_token")
                tokens[name] = token
                print(f"✅ {name} login: SUCCESS (token: {token[:20]}...)")
            else:
                print(f"❌ {name} login: FAILED - Status {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                all_passed = False
        except Exception as e:
            print(f"❌ {name} login: ERROR - {str(e)}")
            all_passed = False
    
    return all_passed, tokens

def test_isolation_check(sa_token):
    """Test GET /api/platform/isolation-check as superadmin"""
    print("\n" + "="*80)
    print("BACKEND REGRESSION - ISOLATION CHECK")
    print("="*80)
    
    try:
        response = requests.get(
            f"{BASE_URL}/platform/isolation-check",
            headers={"Authorization": f"Bearer {sa_token}"},
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            if status == "PASS":
                print(f"✅ Isolation check: PASS")
                print(f"   Collections checked: {data.get('collections_checked')}")
                print(f"   Organizations: {data.get('organisations')}")
                return True
            else:
                print(f"❌ Isolation check: FAILED")
                print(f"   Problems: {data.get('problems')}")
                return False
        else:
            print(f"❌ Isolation check: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Isolation check: ERROR - {str(e)}")
        return False

def test_trial_balance(org_admin_token):
    """Test GET /api/accounting/reports/trial-balance as org admin"""
    print("\n" + "="*80)
    print("BACKEND REGRESSION - TRIAL BALANCE")
    print("="*80)
    
    try:
        response = requests.get(
            f"{BASE_URL}/accounting/reports/trial-balance",
            headers={"Authorization": f"Bearer {org_admin_token}"},
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            total_debit = data.get("total_debit", 0)
            total_credit = data.get("total_credit", 0)
            delta = abs(total_debit - total_credit)
            
            if delta < 0.01:
                print(f"✅ Trial balance: BALANCED")
                print(f"   Total Debit: ₹{total_debit:,.2f}")
                print(f"   Total Credit: ₹{total_credit:,.2f}")
                print(f"   Delta: ₹{delta:.2f}")
                return True
            else:
                print(f"❌ Trial balance: NOT BALANCED")
                print(f"   Total Debit: ₹{total_debit:,.2f}")
                print(f"   Total Credit: ₹{total_credit:,.2f}")
                print(f"   Delta: ₹{delta:.2f}")
                return False
        else:
            print(f"❌ Trial balance: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Trial balance: ERROR - {str(e)}")
        return False

def main():
    print("\n" + "="*80)
    print("BACKEND REGRESSION TEST - ROUND 2")
    print("Testing 3 critical APIs before frontend testing")
    print("="*80)
    
    # Test 1: Login for all accounts
    login_passed, tokens = test_login_password()
    
    # Test 2: Isolation check (if superadmin token available)
    isolation_passed = False
    if "SuperAdmin" in tokens:
        isolation_passed = test_isolation_check(tokens["SuperAdmin"])
    else:
        print("\n⚠️  Skipping isolation check - no superadmin token")
    
    # Test 3: Trial balance (if org admin token available)
    trial_balance_passed = False
    if "Org A Admin" in tokens:
        trial_balance_passed = test_trial_balance(tokens["Org A Admin"])
    else:
        print("\n⚠️  Skipping trial balance - no org admin token")
    
    # Summary
    print("\n" + "="*80)
    print("BACKEND REGRESSION SUMMARY")
    print("="*80)
    print(f"Login (4 accounts): {'✅ PASS' if login_passed else '❌ FAIL'}")
    print(f"Isolation check: {'✅ PASS' if isolation_passed else '❌ FAIL'}")
    print(f"Trial balance: {'✅ PASS' if trial_balance_passed else '❌ FAIL'}")
    
    all_passed = login_passed and isolation_passed and trial_balance_passed
    print(f"\nOverall: {'✅ ALL BACKEND TESTS PASSED' if all_passed else '❌ SOME BACKEND TESTS FAILED'}")
    print("="*80)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
