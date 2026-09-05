"""Tests for the 4 new finance features:
1) Recurring Expenses
2) Favorite Accounts
3) Vendor Commission Statement PDF
4) Bank Reconciliation

Run with:  python3 /app/tests/test_finance_extras.py
"""
import os, sys, uuid, io, requests
from datetime import date, timedelta, datetime

BASE = os.environ.get("API_BASE", "http://localhost:8001/api")


def login(email="admin@designsaga.com", password="Admin@123"):
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
# 1) RECURRING EXPENSES
# ==========================================================================
def test_recurring_create_and_run():
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    r = s.post(f"{BASE}/recurring-expenses", json={
        "name": f"Test-Rent-{uuid.uuid4().hex[:6]}",
        "amount": 12345, "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "frequency": "monthly", "day_of_month": 5,
    })
    assert r.status_code == 200, r.text
    rule = r.json()
    assert rule["next_run_date"] and rule["run_count"] == 0

    # Run now
    r = s.post(f"{BASE}/recurring-expenses/{rule['id']}/run-now")
    r.raise_for_status()
    body = r.json()
    assert body["journal"]["source"] == "recurring_expense"
    # Balanced?
    lines = body["journal"]["lines"]
    dr = sum(l["debit"] for l in lines)
    cr = sum(l["credit"] for l in lines)
    assert round(dr, 2) == round(cr, 2) == 12345
    # Advance
    reloaded = body["rule"]
    assert reloaded["run_count"] == 1
    assert reloaded["last_journal_id"] == body["journal"]["id"]

    # Run again same day → idempotent (should not create another JE for today)
    r = s.post(f"{BASE}/recurring-expenses/{rule['id']}/run-now")
    r.raise_for_status()
    body2 = r.json()
    # journal should be None (already posted for today)
    assert body2["journal"] is None, f"expected idempotent no-op, got {body2}"
    print("PASS: test_recurring_create_and_run")


def test_recurring_scan_endpoint():
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    # Create rule with next_run_date = today (default when start_date=today).
    r = s.post(f"{BASE}/recurring-expenses", json={
        "name": f"Test-Scan-{uuid.uuid4().hex[:6]}",
        "amount": 999, "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "frequency": "monthly",
    })
    r.raise_for_status()
    rid = r.json()["id"]

    resp = s.post(f"{BASE}/recurring-expenses/scan").json()
    assert "posted" in resp
    # After scan, the rule we just made should have run_count >= 1
    fresh = s.get(f"{BASE}/recurring-expenses").json()
    rule = next(x for x in fresh if x["id"] == rid)
    assert rule["run_count"] >= 1
    print("PASS: test_recurring_scan_endpoint")


def test_recurring_pause_and_delete():
    s, _ = login()
    exp, bank = _expense_and_bank(s)
    r = s.post(f"{BASE}/recurring-expenses", json={
        "name": f"Test-Pause-{uuid.uuid4().hex[:6]}",
        "amount": 100, "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"], "frequency": "monthly",
    })
    rid = r.json()["id"]

    r = s.patch(f"{BASE}/recurring-expenses/{rid}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False

    r = s.delete(f"{BASE}/recurring-expenses/{rid}")
    assert r.status_code == 200
    remaining = s.get(f"{BASE}/recurring-expenses").json()
    assert rid not in [x["id"] for x in remaining]
    print("PASS: test_recurring_pause_and_delete")


# ==========================================================================
# 2) FAVORITE ACCOUNTS
# ==========================================================================
def test_favorites_pin_unpin():
    s, _ = login()
    exp, _ = _expense_and_bank(s)
    # Start clean — remove if present
    s.delete(f"{BASE}/favorite-accounts/{exp['id']}")
    r = s.post(f"{BASE}/favorite-accounts", json={"account_id": exp["id"]})
    r.raise_for_status()
    assert exp["id"] in r.json()["account_ids"]
    # Duplicate — should stay stable
    r = s.post(f"{BASE}/favorite-accounts", json={"account_id": exp["id"]})
    assert r.json()["account_ids"].count(exp["id"]) == 1
    # List
    r = s.get(f"{BASE}/favorite-accounts").json()
    assert any(a["id"] == exp["id"] for a in r["accounts"])
    # Unpin
    r = s.delete(f"{BASE}/favorite-accounts/{exp['id']}").json()
    assert exp["id"] not in r["account_ids"]
    print("PASS: test_favorites_pin_unpin")


# ==========================================================================
# 3) VENDOR STATEMENT PDF
# ==========================================================================
def test_vendor_statement_pdf():
    s, _ = login()
    v = s.post(f"{BASE}/vendors", json={
        "name": f"PDFVendor-{uuid.uuid4().hex[:6]}", "agency_type": "supplier",
    }).json()
    r = s.get(f"{BASE}/vendors/{v['id']}/commission-statement.pdf")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF", "response is not a PDF"
    assert len(r.content) > 500, "PDF suspiciously small"
    print(f"PASS: test_vendor_statement_pdf ({len(r.content)} bytes)")


# ==========================================================================
# 4) BANK RECONCILIATION
# ==========================================================================
def test_bank_reconciliation_flow():
    s, _ = login()
    exp, bank = _expense_and_bank(s)

    # First post an expense JE we can auto-match against
    today = date.today().isoformat()
    unique = uuid.uuid4().hex[:6]
    je = s.post(f"{BASE}/accounting/expense", json={
        "date": today, "amount": 3210,
        "expense_account_id": exp["id"],
        "paid_from_account_id": bank["id"],
        "payment_method": "bank_transfer",
        "notes": f"AutoTest-{unique}",
    }).json()
    assert je.get("id"), f"expense JE failed {je}"

    # Now upload a bank CSV with exactly that amount
    csv = (
        "Date,Description,Debit,Credit,Reference\n"
        f"{today},TestExpense {unique},3210,,REF-{unique}\n"
        f"{today},Unmatched deposit {unique},,5555,DEP-{unique}\n"
    )
    files = {"file": (f"stmt-{unique}.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    r = s.post(f"{BASE}/bank-reconciliation/{bank['id']}/upload", files=files)
    r.raise_for_status()
    body = r.json()
    assert body["rows_saved"] == 2
    assert body["auto_matched"] >= 1, f"expected auto match, got {body}"

    # List rows
    rows = s.get(f"{BASE}/bank-reconciliation/{bank['id']}/rows").json()
    ours = [r for r in rows["rows"] if unique in (r.get("description") or "")]
    auto = [r for r in ours if r["status"] == "auto_matched"]
    unm = [r for r in ours if r["status"] == "unmatched"]
    assert auto, "no auto_matched row"
    assert unm, "no unmatched row"

    # Reconcile the auto-matched
    r = s.post(f"{BASE}/bank-reconciliation/rows/{auto[0]['id']}/reconcile")
    r.raise_for_status()

    # Create JE from the unmatched deposit
    income_acc = next(a for a in s.get(f"{BASE}/accounts").json() if a["type"] == "income")
    r = s.post(
        f"{BASE}/bank-reconciliation/rows/{unm[0]['id']}/create-je",
        json={"counterpart_account_id": income_acc["id"],
              "narration": "Bank test income"},
    )
    r.raise_for_status()
    new_je = r.json()["journal"]
    # Balanced?
    dr = sum(l["debit"] for l in new_je["lines"])
    cr = sum(l["credit"] for l in new_je["lines"])
    assert round(dr, 2) == round(cr, 2) == 5555

    # Verify row is now matched
    rows2 = s.get(f"{BASE}/bank-reconciliation/{bank['id']}/rows").json()
    unm_after = next(r for r in rows2["rows"] if r["id"] == unm[0]["id"])
    assert unm_after["status"] == "matched"
    assert unm_after["matched_journal_id"] == new_je["id"]

    print("PASS: test_bank_reconciliation_flow")


def test_bank_reconciliation_summary():
    s, _ = login()
    r = s.get(f"{BASE}/bank-reconciliation/summary").json()
    assert "accounts" in r
    # Every entry should have status counters
    for a in r["accounts"]:
        for k in ("unmatched", "matched", "auto_matched", "reconciled", "ignored"):
            assert k in a, f"missing counter {k}"
    print("PASS: test_bank_reconciliation_summary")


if __name__ == "__main__":
    tests = [
        test_recurring_create_and_run,
        test_recurring_scan_endpoint,
        test_recurring_pause_and_delete,
        test_favorites_pin_unpin,
        test_vendor_statement_pdf,
        test_bank_reconciliation_flow,
        test_bank_reconciliation_summary,
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
