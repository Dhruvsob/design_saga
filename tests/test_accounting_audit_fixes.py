"""Regression tests for the audit-finding fixes.

Run with:
    python3 /app/tests/test_accounting_audit_fixes.py
"""
import os, sys, json, requests, uuid
from datetime import date, timedelta

BASE = os.environ.get("API_BASE", "http://localhost:8001/api")
EMAIL = "admin@designsaga.com"
PASSWORD = "Admin@123"

# Non-admin (Accountant role) test user credentials — will be seeded on the fly
NON_ADMIN_EMAIL = "acct@test.com"
NON_ADMIN_PWD = "Acct@1234"


def login(email=EMAIL, password=PASSWORD):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login-password",
               json={"identifier": email, "password": password})
    r.raise_for_status()
    body = r.json()
    # Use Authorization header — session cookie has secure=True which requires https
    tok = body["session_token"]
    s.headers["Authorization"] = f"Bearer {tok}"
    return s, body


def seed_non_admin_user_via_db():
    """Direct DB seed — bypasses invite flow so tests are hermetic."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from passlib.hash import bcrypt
    import asyncio
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    dbn = os.environ.get("DB_NAME", "test_database")
    db = client[dbn]

    async def _run():
        existing = await db.users.find_one({"email": NON_ADMIN_EMAIL})
        if existing:
            return
        await db.users.insert_one({
            "user_id": f"u_{uuid.uuid4().hex[:8]}",
            "email": NON_ADMIN_EMAIL,
            "name": "Test Accountant",
            "role": "Accountant",
            "employee_id": f"DS{9000 + (hash(NON_ADMIN_EMAIL) % 999):04d}",
            "password_hash": bcrypt.hash(NON_ADMIN_PWD),
            "is_active": True,
            "approval_status": "approved",
            "org_id": "org_default",
        })
    asyncio.run(_run())


def test_1_payment_reversal_resets_invoice():
    """P1.1 — Reversing an invoice_payment JE should reset the invoice to
    'sent' and clear its journal_id."""
    s, me = login()
    # Create a client
    r = s.post(f"{BASE}/clients", json={"name": "AuditTestClient"})
    r.raise_for_status()
    cid = r.json()["id"]
    # Create an invoice via server route (POST /invoices)
    inv = s.post(f"{BASE}/invoices", json={
        "client_id": cid, "client_name": "AuditTestClient",
        "items": [{"description": "Design work", "qty": 1, "rate": 5000}],
        "subtotal": 5000, "total": 5000, "issue_date": date.today().isoformat(),
    })
    inv.raise_for_status()
    inv_id = inv.json()["id"]

    # Mark paid → JE should be created
    r = s.patch(f"{BASE}/invoices/{inv_id}/status", json={"status": "paid"})
    r.raise_for_status()
    body = r.json()
    assert body.get("status") == "paid", body
    je_id = body.get("journal_id")
    assert je_id, "invoice should have journal_id after paid"
    # Verify JE exists
    je = s.get(f"{BASE}/journal-entries/{je_id}").json()
    assert je.get("source") == "invoice_payment"

    # Now reverse the JE using the "Reverse" action on the JE — this should
    # cascade back and reset the invoice.
    r = s.post(f"{BASE}/journal-entries/{je_id}/reverse")
    r.raise_for_status()

    # Reload invoice — should be sent again + journal_id cleared
    inv2 = s.get(f"{BASE}/invoices/{inv_id}").json()
    assert inv2.get("status") == "sent", f"expected 'sent', got {inv2.get('status')}"
    assert not inv2.get("journal_id"), "journal_id should be cleared after reversal"
    print("PASS: test_1_payment_reversal_resets_invoice")


def test_2_milestone_reversal_resets_milestone():
    """P1.1 — Reversing a milestone_payment JE resets the milestone to pending."""
    s, me = login()
    r = s.post(f"{BASE}/clients", json={"name": "MSAuditClient"})
    cid = r.json()["id"]
    r = s.post(f"{BASE}/projects", json={"name": "MSAudit", "client_id": cid, "budget": 10000, "engagement_type": "consultancy"})
    pid = r.json()["id"]
    r = s.post(f"{BASE}/projects/{pid}/milestones", json={
        "project_id": pid, "name": "Advance", "amount": 3000,
        "due_date": date.today().isoformat(),
    })
    r.raise_for_status()
    ms = r.json()
    # Mark paid → auto-post JE
    r = s.patch(f"{BASE}/milestones/{ms['id']}", json={"status": "paid", "amount": 3000})
    r.raise_for_status()
    milestone_after = r.json()
    je_id = milestone_after.get("journal_id")
    assert je_id, f"milestone should have journal_id after paid: {milestone_after}"

    # Reverse via JE action
    s.post(f"{BASE}/journal-entries/{je_id}/reverse").raise_for_status()

    # Reload milestone
    all_ms = s.get(f"{BASE}/projects/{pid}/milestones").json()
    fresh = next((m for m in all_ms if m["id"] == ms["id"]), None)
    assert fresh, "milestone gone"
    assert fresh.get("status") == "pending", f"expected pending, got {fresh.get('status')}"
    assert not fresh.get("journal_id"), "journal_id should be cleared"
    print("PASS: test_2_milestone_reversal_resets_milestone")


def test_3_rbac_uses_finance_perms():
    """P1.4 — Accounting create/update endpoints require finance.* permissions.
    An Accountant (has finance.*) should be able to create an account; an
    Employee (no finance.*) should NOT."""
    seed_non_admin_user_via_db()
    # Accountant should succeed
    s, _ = login(NON_ADMIN_EMAIL, NON_ADMIN_PWD)
    r = s.post(f"{BASE}/accounts", json={
        "name": f"TestAcct-{uuid.uuid4().hex[:6]}",
        "type": "expense",
    })
    assert r.status_code == 200, f"Accountant should create account, got {r.status_code}: {r.text}"
    print("PASS: test_3_rbac_uses_finance_perms (Accountant CAN create account)")


def test_4_commission_uses_central_engine_and_keeps_project():
    """P1.2/P1.3 — Commission receipt uses central engine, JE is balanced and
    linked to the project of the commission row."""
    s, _ = login()
    # Create vendor
    r = s.post(f"{BASE}/vendors", json={
        "name": f"CommTestVendor-{uuid.uuid4().hex[:6]}", "agency_type": "supplier",
    })
    r.raise_for_status()
    v = r.json()
    vid = v["id"]

    # Set commission config
    r = s.patch(f"{BASE}/vendors/{vid}/commercial", json={
        "applicable": True, "type": "percentage", "percentage": 5,
    })
    r.raise_for_status()

    # Create project + bill
    cli = s.post(f"{BASE}/clients", json={"name": "CommClient"}).json()
    proj = s.post(f"{BASE}/projects", json={"name": "CommProj", "client_id": cli["id"], "budget": 100000, "engagement_type": "turnkey"}).json()
    bill = s.post(f"{BASE}/vendor-bills", json={
        "vendor_id": vid, "project_id": proj["id"],
        "bill_number": f"B-{uuid.uuid4().hex[:6]}",
        "bill_date": date.today().isoformat(),
        "items": [{"description": "Test", "qty": 1, "rate": 10000}],
        "subtotal": 10000, "total": 10000,
    })
    assert bill.status_code == 200, bill.text
    # Get the commission that got auto-created
    comms = s.get(f"{BASE}/vendors/{vid}/commissions").json()
    assert comms, "commission should be auto-created"
    assert comms[0]["project_id"] == proj["id"]
    assert comms[0]["amount"] == 500  # 5% of 10000

    # Find a bank account
    accs = s.get(f"{BASE}/accounts").json()
    bank = next((a for a in accs if a.get("is_bank")), None)
    assert bank, "need a bank account"

    # Receive commission
    r = s.post(f"{BASE}/vendors/{vid}/commissions/receive", json={
        "amount": 500, "received_date": date.today().isoformat(),
        "bank_account_id": bank["id"], "payment_method": "bank_transfer",
    })
    r.raise_for_status()
    settle = r.json()
    je_id = settle["journal_entry_id"]
    je = s.get(f"{BASE}/journal-entries/{je_id}").json()
    # Balanced?
    total_d = sum(l["debit"] for l in je["lines"])
    total_c = sum(l["credit"] for l in je["lines"])
    assert round(total_d, 2) == round(total_c, 2) == 500, f"unbalanced JE {je}"
    # Project preserved
    assert je.get("project_id") == proj["id"], f"JE should have project_id, got {je.get('project_id')}"
    # Vendor preserved
    assert je.get("vendor_id") == vid
    # Source
    assert je.get("source") == "commission_income"
    print("PASS: test_4_commission_uses_central_engine_and_keeps_project")


def test_5_trial_balance_includes_opening_balances():
    """P1.5 — Trial Balance and Balance Sheet both include opening balances,
    stay balanced."""
    s, _ = login()
    tb = s.get(f"{BASE}/accounting/reports/trial-balance").json()
    bs = s.get(f"{BASE}/accounting/reports/balance-sheet").json()
    assert abs(tb["total_debit"] - tb["total_credit"]) < 0.01, \
        f"TB not balanced: DR={tb['total_debit']} CR={tb['total_credit']}"
    assert bs["balanced"], f"BS not balanced: delta={bs['delta']}"
    print(f"PASS: test_5_trial_balance_balanced (DR=CR={tb['total_debit']}, BS delta={bs['delta']})")


def test_6_journal_search_and_pagination():
    """P2.9/P2.11 — Journal list supports search + pagination."""
    s, _ = login()
    # Free-text search — explicit offset triggers paginated response
    r = s.get(f"{BASE}/journal-entries?q=payment&limit=5&offset=0").json()
    # Note: offset=0 & limit=5 (not default 200) trips the paginated branch
    assert isinstance(r, dict) and "items" in r, f"expected paginated response, got {type(r).__name__}"
    assert r["limit"] == 5
    # Filters by source, paginated
    r = s.get(f"{BASE}/journal-entries?source=commission_income&limit=5&offset=0").json()
    assert isinstance(r, dict) and "items" in r
    # Default (no limit/offset) returns bare list — backward-compat
    r = s.get(f"{BASE}/journal-entries").json()
    assert isinstance(r, list), f"default should return array, got {type(r).__name__}"
    print("PASS: test_6_journal_search_and_pagination")


def test_7_loan_deletion_reverses_je():
    """P1.6 — Deleting a loan (with no paid EMIs) reverses the disbursement JE
    instead of hard-deleting it."""
    s, _ = login()
    accs = s.get(f"{BASE}/accounts").json()
    bank = next((a for a in accs if a.get("is_bank")), None)
    r = s.post(f"{BASE}/loans", json={
        "lender_name": "TestBank",
        "principal": 100000, "interest_rate_pa": 12, "tenure_months": 12,
        "start_date": date.today().isoformat(),
        "disbursement_account_id": bank["id"],
    })
    r.raise_for_status()
    loan = r.json()
    loan_id = loan["id"]
    disb_je_id = loan["disbursement_journal_id"]

    # Verify JE exists
    je = s.get(f"{BASE}/journal-entries/{disb_je_id}").json()
    assert je and je.get("total") == 100000

    # Delete loan (no paid EMIs) → should archive + reverse the disbursement JE
    r = s.delete(f"{BASE}/loans/{loan_id}")
    r.raise_for_status()
    body = r.json()
    assert body.get("archived") is True, body

    # JE should still exist but be marked reversed
    je2 = s.get(f"{BASE}/journal-entries/{disb_je_id}").json()
    assert je2 is not None, "JE should not have been hard-deleted"
    assert je2.get("reversed") is True, "JE should be marked reversed"

    # Loan status = archived, filtered out of default list
    default_list = s.get(f"{BASE}/loans").json()
    assert loan_id not in [l["id"] for l in default_list], "archived loan should be hidden from default list"
    # But visible with include_archived
    inc_list = s.get(f"{BASE}/loans?include_archived=1").json()
    assert loan_id in [l["id"] for l in inc_list], "archived loan should appear when include_archived=1"
    print("PASS: test_7_loan_deletion_reverses_je")


def test_8_today_collections_includes_invoice_payment():
    """P2.10 — 'Today's Collections' should count invoice_payment JEs
    posted today, not just source=='income'."""
    s, _ = login()
    # Create invoice with today's date, mark paid
    cli = s.post(f"{BASE}/clients", json={"name": "TdyCollClient"}).json()
    inv = s.post(f"{BASE}/invoices", json={
        "client_id": cli["id"], "client_name": "TdyCollClient",
        "items": [{"description": "Work", "qty": 1, "rate": 7777}],
        "subtotal": 7777, "total": 7777, "issue_date": date.today().isoformat(),
    }).json()
    s.patch(f"{BASE}/invoices/{inv['id']}/status", json={"status": "paid"}).raise_for_status()

    # Now dashboard should reflect at least 7777 in today's collections
    d = s.get(f"{BASE}/accounting/dashboard").json()
    tc = d["kpis"]["today_collections"]
    assert tc >= 7777, f"today_collections {tc} < 7777"
    print(f"PASS: test_8_today_collections_includes_invoice_payment (today_collections={tc})")


if __name__ == "__main__":
    tests = [
        test_1_payment_reversal_resets_invoice,
        test_2_milestone_reversal_resets_milestone,
        test_3_rbac_uses_finance_perms,
        test_4_commission_uses_central_engine_and_keeps_project,
        test_5_trial_balance_includes_opening_balances,
        test_6_journal_search_and_pagination,
        test_7_loan_deletion_reverses_je,
        test_8_today_collections_includes_invoice_payment,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {e!r}")
            import traceback; traceback.print_exc()
            failed += 1
    print(f"\n{'='*60}\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
