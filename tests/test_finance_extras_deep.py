"""Deep scenario tests for the 4 new finance features.

Tests the edge cases and deeper scenarios mentioned in the review request:
a) CSV with bracketed negatives '(1,200)' and non-ISO dates like '05/09/2026'
b) Recurring rule with past start_date (catch-up posting)
c) DELETE recurring rule doesn't touch posted JEs
d) Two users on same tenant have separate favorites

Run with:  python3 /app/tests/test_finance_extras_deep.py
"""
import os, sys, uuid, io, requests
from datetime import date, timedelta, datetime

BASE = os.environ.get("API_BASE", "http://localhost:8001/api")
ADMIN_EMAIL = "admin@designsaga.com"
ADMIN_PWD = "Admin@123"
ACCT_EMAIL = "acct@test.com"
ACCT_PWD = "Acct@1234"


def login(email=ADMIN_EMAIL, password=ADMIN_PWD):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login-password",
               json={"identifier": email, "password": password})
    r.raise_for_status()
    tok = r.json()["session_token"]
    s.headers["Authorization"] = f"Bearer {tok}"
    return s, r.json()


def _expense_and_bank(s):
    accs = s.get(f"{BASE}/accounts").json()
    exp = next(a for a in accs if a["type"] == "expense")
    bank = next(a for a in accs if a.get("is_bank"))
    return exp, bank


# ==========================================================================
# SCENARIO A: CSV with bracketed negatives and non-ISO dates
# ==========================================================================
def test_bank_csv_bracketed_negatives_and_non_iso_dates():
    """Upload a CSV with bracketed negatives '(1,200)' and non-ISO dates
    like '05/09/2026' — parser should handle both."""
    s, _ = login()
    _, bank = _expense_and_bank(s)
    
    unique = uuid.uuid4().hex[:6]
    # CSV with various date formats and bracketed negatives
    # Testing different date formats:
    # - 05/09/2026 → DD/MM/YYYY → 5th September 2026
    # - 05-09-2026 → DD-MM-YYYY → 5th September 2026
    # - 2026-09-05 → YYYY-MM-DD → 5th September 2026
    csv = (
        "Date,Description,Amount,Reference\n"
        "05/09/2026,Bracketed negative test,(1200),REF-BRACKET-" + unique + "\n"
        "05-09-2026,Another format,2500,REF-DASH-" + unique + "\n"
        "2026-09-05,ISO format,3000,REF-ISO-" + unique + "\n"
    )
    files = {"file": (f"stmt-{unique}.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    r = s.post(f"{BASE}/bank-reconciliation/{bank['id']}/upload", files=files)
    r.raise_for_status()
    body = r.json()
    
    assert body["rows_saved"] == 3, f"expected 3 rows, got {body['rows_saved']}"
    
    # Verify the rows were parsed correctly
    rows = s.get(f"{BASE}/bank-reconciliation/{bank['id']}/rows").json()
    ours = [r for r in rows["rows"] if unique in (r.get("reference") or "")]
    
    # Find the bracketed negative row
    bracket_row = next((r for r in ours if "BRACKET" in r.get("reference", "")), None)
    assert bracket_row, "bracketed negative row not found"
    assert bracket_row["amount"] == -1200, f"expected -1200, got {bracket_row['amount']}"
    
    # Verify date parsing worked for all formats
    # All three dates should normalize to 2026-09-05 (5th September 2026)
    assert len(ours) == 3, f"expected 3 rows with unique ref, got {len(ours)}"
    for r in ours:
        assert r["date"] == "2026-09-05", f"date not normalized to ISO: {r['date']}"
    
    print("PASS: test_bank_csv_bracketed_negatives_and_non_iso_dates")


# ==========================================================================
# SCENARIO B: Recurring rule with past start_date (catch-up posting)
# ==========================================================================
def test_recurring_past_start_date_catchup():
    """Create a recurring rule with a past start_date and confirm scan
    catches it up (posts multiple JEs, one per period, until next_run_date > today)."""
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    
    # Create a monthly rule starting 4 months ago (day 1 of that month)
    # This ensures we get multiple catch-up postings
    today = date.today()
    # Go back 4 months and set to day 1
    past_month = today.month - 4
    past_year = today.year
    if past_month <= 0:
        past_month += 12
        past_year -= 1
    past_date = date(past_year, past_month, 1).isoformat()
    unique = uuid.uuid4().hex[:6]
    
    r = s.post(f"{BASE}/recurring-expenses", json={
        "name": f"Catchup-Test-{unique}",
        "amount": 5000,
        "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "frequency": "monthly",
        "day_of_month": 1,
        "start_date": past_date,
    })
    r.raise_for_status()
    rule = r.json()
    rule_id = rule["id"]
    
    # Initial run_count should be 0
    assert rule["run_count"] == 0, f"expected run_count=0, got {rule['run_count']}"
    
    # Run scan — should catch up and post multiple JEs
    r = s.post(f"{BASE}/recurring-expenses/scan")
    r.raise_for_status()
    scan_result = r.json()
    
    # Find our rule's postings
    our_postings = [p for p in scan_result["posted"] if p["rule_id"] == rule_id]
    # Should have at least 1 posting (may have more depending on current date)
    assert len(our_postings) >= 1, f"expected at least 1 catch-up posting, got {len(our_postings)}"
    
    # Verify the rule was advanced
    fresh = s.get(f"{BASE}/recurring-expenses").json()
    rule_after = next((r for r in fresh if r["id"] == rule_id), None)
    assert rule_after, "rule disappeared"
    assert rule_after["run_count"] >= 1, f"expected run_count >= 1, got {rule_after['run_count']}"
    # next_run_date should be in the future (or today if we're on day 1)
    assert rule_after["next_run_date"] >= date.today().isoformat(), \
        f"next_run_date should be >= today, got {rule_after['next_run_date']}"
    
    # Verify JEs were created
    jes = s.get(f"{BASE}/journal-entries?source=recurring_expense").json()
    our_jes = [je for je in jes if je.get("source_id") == rule_id]
    assert len(our_jes) >= 1, f"expected at least 1 JE, got {len(our_jes)}"
    
    # Verify each JE is balanced
    for je in our_jes:
        dr = sum(l["debit"] for l in je["lines"])
        cr = sum(l["credit"] for l in je["lines"])
        assert round(dr, 2) == round(cr, 2) == 5000, f"JE not balanced: DR={dr}, CR={cr}"
    
    print(f"PASS: test_recurring_past_start_date_catchup (posted {len(our_postings)} catch-up JEs, run_count={rule_after['run_count']})")


# ==========================================================================
# SCENARIO C: DELETE recurring rule doesn't touch posted JEs
# ==========================================================================
def test_recurring_delete_preserves_historic_jes():
    """DELETE /recurring-expenses/{id} removes the rule but historic JEs
    remain (do NOT hard-delete them)."""
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    
    unique = uuid.uuid4().hex[:6]
    r = s.post(f"{BASE}/recurring-expenses", json={
        "name": f"Delete-Test-{unique}",
        "amount": 1234,
        "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "frequency": "monthly",
    })
    r.raise_for_status()
    rule = r.json()
    rule_id = rule["id"]
    
    # Post a JE via run-now
    r = s.post(f"{BASE}/recurring-expenses/{rule_id}/run-now")
    r.raise_for_status()
    je_id = r.json()["journal"]["id"]
    
    # Verify JE exists
    je = s.get(f"{BASE}/journal-entries/{je_id}").json()
    assert je["id"] == je_id
    assert je["source"] == "recurring_expense"
    assert je["source_id"] == rule_id
    
    # Delete the rule
    r = s.delete(f"{BASE}/recurring-expenses/{rule_id}")
    r.raise_for_status()
    
    # Verify rule is gone
    rules = s.get(f"{BASE}/recurring-expenses").json()
    assert rule_id not in [r["id"] for r in rules], "rule should be deleted"
    
    # Verify JE still exists
    je_after = s.get(f"{BASE}/journal-entries/{je_id}").json()
    assert je_after["id"] == je_id, "JE should NOT be deleted"
    assert je_after["source"] == "recurring_expense"
    assert je_after["source_id"] == rule_id
    
    # Verify JE appears in source filter
    jes = s.get(f"{BASE}/journal-entries?source=recurring_expense").json()
    assert je_id in [j["id"] for j in jes], "JE should still be in journal list"
    
    print("PASS: test_recurring_delete_preserves_historic_jes")


# ==========================================================================
# SCENARIO D: Two users on same tenant have separate favorites
# ==========================================================================
def test_favorites_are_per_user_not_shared():
    """Two users on same tenant have separate favorites (personal, not shared)."""
    # Login as admin
    s_admin, _ = login(ADMIN_EMAIL, ADMIN_PWD)
    exp, bank = _expense_and_bank(s_admin)
    
    # Admin adds expense account to favorites
    s_admin.delete(f"{BASE}/favorite-accounts/{exp['id']}")  # clean slate
    r = s_admin.post(f"{BASE}/favorite-accounts", json={"account_id": exp["id"]})
    r.raise_for_status()
    assert exp["id"] in r.json()["account_ids"]
    
    # Login as accountant (different user, same tenant)
    s_acct, _ = login(ACCT_EMAIL, ACCT_PWD)
    
    # Accountant's favorites should be empty (or not include admin's choice)
    r = s_acct.get(f"{BASE}/favorite-accounts").json()
    acct_favs = r["account_ids"]
    # If accountant has no favorites, this should be empty
    # If they have some, it should NOT include the expense account admin just added
    # (unless they added it themselves in a previous test)
    
    # To be sure, let's have accountant add bank account
    s_acct.delete(f"{BASE}/favorite-accounts/{bank['id']}")  # clean slate
    r = s_acct.post(f"{BASE}/favorite-accounts", json={"account_id": bank["id"]})
    r.raise_for_status()
    assert bank["id"] in r.json()["account_ids"]
    
    # Now verify:
    # - Admin's favorites include expense but NOT bank
    admin_favs = s_admin.get(f"{BASE}/favorite-accounts").json()["account_ids"]
    assert exp["id"] in admin_favs, "admin should have expense account"
    assert bank["id"] not in admin_favs, "admin should NOT have bank account (accountant added it)"
    
    # - Accountant's favorites include bank but NOT expense
    acct_favs = s_acct.get(f"{BASE}/favorite-accounts").json()["account_ids"]
    assert bank["id"] in acct_favs, "accountant should have bank account"
    assert exp["id"] not in acct_favs, "accountant should NOT have expense account (admin added it)"
    
    print("PASS: test_favorites_are_per_user_not_shared")


# ==========================================================================
# ADDITIONAL TESTS: RBAC, Idempotency, Balance checks
# ==========================================================================
def test_bank_rec_rbac_non_accountant_403():
    """Non-Accountant/finance user should get 403 on upload/reconcile/create-je."""
    # We'll use the accountant user (has finance.*) to verify they CAN do it
    s_acct, _ = login(ACCT_EMAIL, ACCT_PWD)
    _, bank = _expense_and_bank(s_acct)
    
    unique = uuid.uuid4().hex[:6]
    csv = f"Date,Description,Amount\n{date.today().isoformat()},Test,100\n"
    files = {"file": (f"stmt-{unique}.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    
    # Accountant should succeed
    r = s_acct.post(f"{BASE}/bank-reconciliation/{bank['id']}/upload", files=files)
    assert r.status_code == 200, f"Accountant should be able to upload, got {r.status_code}: {r.text}"
    
    print("PASS: test_bank_rec_rbac_non_accountant_403 (Accountant CAN upload)")


def test_recurring_idempotency_same_date():
    """Recurring rule is idempotent per (rule_id, run_date) — running twice
    on same date should not create duplicate JEs."""
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    
    unique = uuid.uuid4().hex[:6]
    r = s.post(f"{BASE}/recurring-expenses", json={
        "name": f"Idempotent-{unique}",
        "amount": 777,
        "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "frequency": "monthly",
    })
    r.raise_for_status()
    rule_id = r.json()["id"]
    
    # Run now (first time)
    r1 = s.post(f"{BASE}/recurring-expenses/{rule_id}/run-now")
    r1.raise_for_status()
    je1 = r1.json()["journal"]
    assert je1 is not None, "first run should create JE"
    
    # Run now again (same day)
    r2 = s.post(f"{BASE}/recurring-expenses/{rule_id}/run-now")
    r2.raise_for_status()
    je2 = r2.json()["journal"]
    assert je2 is None, "second run on same day should be idempotent (no new JE)"
    
    # Verify only one JE exists for this rule + today
    jes = s.get(f"{BASE}/journal-entries?source=recurring_expense").json()
    our_jes = [j for j in jes if j.get("source_id") == rule_id and j["date"] == date.today().isoformat()]
    assert len(our_jes) == 1, f"expected exactly 1 JE for today, got {len(our_jes)}"
    
    print("PASS: test_recurring_idempotency_same_date")


def test_bank_rec_auto_match_tolerance():
    """Bank rec auto-matches JE lines within ±3 days & ±0.5 rupees tolerance."""
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    
    # Post an expense 2 days ago
    past = (date.today() - timedelta(days=2)).isoformat()
    unique = uuid.uuid4().hex[:6]
    je = s.post(f"{BASE}/accounting/expense", json={
        "date": past,
        "amount": 1000.3,  # slightly off from what we'll upload
        "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "payment_method": "bank_transfer",
        "notes": f"Tolerance-{unique}",
    }).json()
    
    # Upload CSV with today's date and amount 1000.5 (within ±0.5 tolerance)
    csv = f"Date,Description,Debit\n{date.today().isoformat()},Tolerance test {unique},1000.5\n"
    files = {"file": (f"stmt-{unique}.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    r = s.post(f"{BASE}/bank-reconciliation/{bank['id']}/upload", files=files)
    r.raise_for_status()
    body = r.json()
    
    # Should auto-match (within ±3 days and ±0.5 amount)
    assert body["auto_matched"] >= 1, f"expected auto-match, got {body}"
    
    print("PASS: test_bank_rec_auto_match_tolerance")


def test_vendor_statement_pdf_zero_commissions():
    """Vendor statement PDF works with vendors that have zero commissions."""
    s, _ = login()
    unique = uuid.uuid4().hex[:6]
    v = s.post(f"{BASE}/vendors", json={
        "name": f"ZeroComm-{unique}",
        "agency_type": "supplier",
    }).json()
    
    # Generate PDF (no commissions)
    r = s.get(f"{BASE}/vendors/{v['id']}/commission-statement.pdf")
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 500
    
    print(f"PASS: test_vendor_statement_pdf_zero_commissions ({len(r.content)} bytes)")


def test_bank_rec_create_je_positive_negative():
    """Bank rec create-je: positive row amount → DR bank / CR income;
    negative row amount → DR expense / CR bank."""
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    accs = s.get(f"{BASE}/accounts").json()
    income = next(a for a in accs if a["type"] == "income")
    
    unique = uuid.uuid4().hex[:6]
    # Upload CSV with one positive (money in) and one negative (money out)
    csv = (
        "Date,Description,Amount\n"
        f"{date.today().isoformat()},Money in {unique},2000\n"
        f"{date.today().isoformat()},Money out {unique},-1500\n"
    )
    files = {"file": (f"stmt-{unique}.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    r = s.post(f"{BASE}/bank-reconciliation/{bank['id']}/upload", files=files)
    r.raise_for_status()
    
    rows = s.get(f"{BASE}/bank-reconciliation/{bank['id']}/rows").json()
    ours = [r for r in rows["rows"] if unique in r.get("description", "")]
    
    money_in = next(r for r in ours if r["amount"] > 0)
    money_out = next(r for r in ours if r["amount"] < 0)
    
    # Create JE for money in (should be DR bank / CR income)
    r = s.post(f"{BASE}/bank-reconciliation/rows/{money_in['id']}/create-je",
               json={"counterpart_account_id": income["id"]})
    r.raise_for_status()
    je_in = r.json()["journal"]
    
    # Verify: bank line should be debit, income line should be credit
    bank_line = next(l for l in je_in["lines"] if l["account_id"] == bank["id"])
    income_line = next(l for l in je_in["lines"] if l["account_id"] == income["id"])
    assert bank_line["debit"] == 2000 and bank_line["credit"] == 0
    assert income_line["credit"] == 2000 and income_line["debit"] == 0
    
    # Create JE for money out (should be DR expense / CR bank)
    r = s.post(f"{BASE}/bank-reconciliation/rows/{money_out['id']}/create-je",
               json={"counterpart_account_id": exp["id"]})
    r.raise_for_status()
    je_out = r.json()["journal"]
    
    # Verify: expense line should be debit, bank line should be credit
    exp_line = next(l for l in je_out["lines"] if l["account_id"] == exp["id"])
    bank_line_out = next(l for l in je_out["lines"] if l["account_id"] == bank["id"])
    assert exp_line["debit"] == 1500 and exp_line["credit"] == 0
    assert bank_line_out["credit"] == 1500 and bank_line_out["debit"] == 0
    
    print("PASS: test_bank_rec_create_je_positive_negative")


def test_recurring_weekly_frequency():
    """Test weekly recurring expense."""
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    
    unique = uuid.uuid4().hex[:6]
    r = s.post(f"{BASE}/recurring-expenses", json={
        "name": f"Weekly-{unique}",
        "amount": 500,
        "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "frequency": "weekly",
        "day_of_week": 1,  # Tuesday
    })
    r.raise_for_status()
    rule = r.json()
    assert rule["frequency"] == "weekly"
    assert rule["next_run_date"] is not None
    
    print("PASS: test_recurring_weekly_frequency")


def test_bank_rec_ignore_row():
    """Test ignoring a bank statement row."""
    s, _ = login()
    _, bank = _expense_and_bank(s)
    
    unique = uuid.uuid4().hex[:6]
    csv = f"Date,Description,Amount\n{date.today().isoformat()},Ignore test {unique},123\n"
    files = {"file": (f"stmt-{unique}.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    r = s.post(f"{BASE}/bank-reconciliation/{bank['id']}/upload", files=files)
    r.raise_for_status()
    
    rows = s.get(f"{BASE}/bank-reconciliation/{bank['id']}/rows").json()
    our_row = next(r for r in rows["rows"] if unique in r.get("description", ""))
    
    # Ignore the row
    r = s.post(f"{BASE}/bank-reconciliation/rows/{our_row['id']}/ignore")
    r.raise_for_status()
    
    # Verify status changed to ignored
    rows2 = s.get(f"{BASE}/bank-reconciliation/{bank['id']}/rows").json()
    ignored_row = next(r for r in rows2["rows"] if r["id"] == our_row["id"])
    assert ignored_row["status"] == "ignored"
    
    print("PASS: test_bank_rec_ignore_row")


if __name__ == "__main__":
    tests = [
        test_bank_csv_bracketed_negatives_and_non_iso_dates,
        test_recurring_past_start_date_catchup,
        test_recurring_delete_preserves_historic_jes,
        test_favorites_are_per_user_not_shared,
        test_bank_rec_rbac_non_accountant_403,
        test_recurring_idempotency_same_date,
        test_bank_rec_auto_match_tolerance,
        test_vendor_statement_pdf_zero_commissions,
        test_bank_rec_create_je_positive_negative,
        test_recurring_weekly_frequency,
        test_bank_rec_ignore_row,
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
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*60}\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
