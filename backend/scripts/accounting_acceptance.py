"""Accounting acceptance fixtures (FINAL_BUSINESS_LOGIC_VERIFICATION.md).

Creates a fresh, empty QA workspace through the real API on a LOCAL stack
and runs the five synthetic cases from the release brief, comparing the
ERP's reports with figures worked out by hand below (not by the code under
test). Refuses any non-local target. Prints one line per check and writes a
JSON summary next to the script's output path when OUT is set.

Fixture: workspace starts with zero balances; cash basis (the product
default: an invoice is a document, income is booked when money arrives);
zero GST/TDS; Indian financial year April-March, dates in IST.

    PROBE_BASE=http://127.0.0.1:4174 QA_SUPERADMIN_EMAIL=... QA_PASSWORD=... \
    QA_PIN=... python scripts/accounting_acceptance.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from urllib.parse import urlparse

import httpx

BASE = os.environ.get("PROBE_BASE", "http://127.0.0.1:4174").rstrip("/")
if urlparse(BASE).hostname not in {"127.0.0.1", "localhost"}:
    sys.exit("accounting_acceptance refuses non-local targets")
OWNER = os.environ["QA_SUPERADMIN_EMAIL"]
PASSWORD = os.environ["QA_PASSWORD"]
PIN = os.environ["QA_PIN"]
RESULTS: list[dict] = []


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, headers={"Origin": BASE}, timeout=60)


def ok(res: httpx.Response, *codes: int) -> dict | list:
    if res.status_code not in (codes or (200, 201)):
        raise RuntimeError(f"{res.request.method} {res.request.url.path} -> {res.status_code}: {res.text[:300]}")
    return res.json() if res.content else {}


def login(identifier: str) -> httpx.Client:
    c = client()
    ok(c.post("/api/auth/login-password", json={"identifier": identifier, "password": PASSWORD}))
    status = ok(c.get("/api/auth/pin/status"))
    if status.get("setup_required"):
        ok(c.post("/api/auth/pin/setup", json={"pin": PIN}))
    elif status.get("locked"):
        ok(c.post("/api/auth/pin/unlock", json={"pin": PIN}))
    return c


def check(case: str, what: str, expected, observed, tol: float = 0.005) -> None:
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        passed = abs(float(expected) - float(observed)) <= tol
    else:
        passed = expected == observed
    RESULTS.append({"case": case, "check": what, "expected": expected,
                    "observed": observed, "pass": passed})
    print(f"{'PASS' if passed else 'FAIL'}  [{case}] {what}: expected {expected}, observed {observed}")


def new_workspace() -> httpx.Client:
    stamp = format(int(time.time() * 1000), "x")[-8:]
    admin_email = f"acct-{stamp}@qa.example.com"
    owner = login(OWNER)
    org = ok(owner.post("/api/platform/orgs", json={
        "name": f"Accounting Fixture {stamp}", "admin_email": admin_email,
        "admin_name": "Fixture Admin", "business_mode": "hybrid"}))
    token = str(org.get("invite_path", "")).replace("/invite/", "")
    with client() as c:
        ok(c.post("/api/auth/invite/accept", json={"token": token, "password": PASSWORD}))
    owner.close()
    admin = login(admin_email)
    if not ok(admin.get("/api/accounts")):
        ok(admin.post("/api/accounting/seed-coa"))
    print(f"workspace {org.get('org_id') or org.get('org', {}).get('org_id')} admin {admin_email}")
    return admin


def accounts(c) -> dict:
    return {a["name"]: a for a in ok(c.get("/api/accounts"))}


def balance(c, name: str, as_of: str | None = None) -> float:
    acc = accounts(c).get(name)
    if not acc:
        return 0.0
    params = {"to_date": as_of} if as_of else {}
    led = ok(c.get(f"/api/accounting/ledger/account/{acc['id']}", params=params))
    for key in ("closing_balance", "closing", "balance"):
        if isinstance(led, dict) and key in led:
            return round(float(led[key]), 2)
    rows = led.get("rows") or led.get("entries") or [] if isinstance(led, dict) else led
    return round(float(rows[-1].get("balance", 0)) if rows else 0.0, 2)


def pl_totals(c, **params) -> dict:
    pl = ok(c.get("/api/accounting/reports/pl", params=params))
    income = pl.get("total_income", pl.get("income_total"))
    expense = pl.get("total_expense", pl.get("total_expenses", pl.get("expense_total")))
    net = pl.get("net_profit", pl.get("net"))
    return {"income": round(float(income or 0), 2), "expense": round(float(expense or 0), 2),
            "net": round(float(net or 0), 2)}


def trial_balance_ok(c, case: str, **params) -> None:
    tb = ok(c.get("/api/accounting/reports/trial-balance", params=params))
    dr = tb.get("total_debit", tb.get("debit_total"))
    cr = tb.get("total_credit", tb.get("credit_total"))
    check(case, f"trial balance debits = credits {params or ''}".strip(), round(float(dr or 0), 2), round(float(cr or 0), 2))


def balance_sheet_ok(c, case: str, **params) -> None:
    bs = ok(c.get("/api/accounting/reports/balance-sheet", params=params))
    assets = bs.get("total_assets")
    liab_eq = bs.get("total_liabilities_and_equity", bs.get("liabilities_and_equity_total"))
    if liab_eq is None and "total_liabilities" in bs:
        liab_eq = float(bs.get("total_liabilities") or 0) + float(bs.get("total_equity") or 0)
    check(case, f"balance sheet assets = liabilities + equity {params or ''}".strip(),
          round(float(assets or 0), 2), round(float(liab_eq or 0), 2))


def case_loan(c) -> None:
    case = "loan"
    bank = accounts(c)["Bank - Primary"]["id"]
    before = balance(c, "Bank - Primary")
    pl0 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    ok(c.post("/api/accounting/non-operating", json={
        "kind": "money_received", "date": "2026-06-10", "amount": 500000,
        "bank_account_id": bank, "party_name": "Fixture Lender", "reference": "Loan agreement"}))
    ok(c.post("/api/accounting/non-operating", json={
        "kind": "repayment_paid", "date": "2026-07-10", "amount": 100000,
        "bank_account_id": bank, "party_name": "Fixture Lender"}))
    too_much = c.post("/api/accounting/non-operating", json={
        "kind": "repayment_paid", "date": "2026-07-11", "amount": 400000.01,
        "bank_account_id": bank, "party_name": "Fixture Lender"})
    check(case, "repaying more than the balance is refused", 409, too_much.status_code)
    check(case, "net bank movement", 400000, round(balance(c, "Bank - Primary") - before, 2))
    check(case, "lender ledger (liability) outstanding", 400000, balance(c, "Loan from - Fixture Lender"))
    pl1 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "operating profit unchanged by principal", pl0["net"], pl1["net"])
    interest = next((a for a in ok(c.get("/api/accounts"))
                     if a["type"] == "expense" and "interest" in a["name"].lower()), None)
    if interest is None:
        interest = ok(c.post("/api/accounts", json={"name": "Interest Paid", "type": "expense"}))
    ok(c.post("/api/accounting/expense", json={
        "date": "2026-07-10", "amount": 5000, "expense_account_id": interest["id"],
        "paid_from_account_id": bank, "reference": "Loan interest July"}))
    pl2 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "interest is an expense (P&L down by 5,000)", round(pl1["net"] - 5000, 2), pl2["net"])
    check(case, "interest does not reduce the loan", 400000, balance(c, "Loan from - Fixture Lender"))
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)


def case_invoice(c) -> None:
    case = "invoice"
    acc = accounts(c)
    bank = acc["Bank - Primary"]["id"]
    income = next(a for a in acc.values() if a["type"] == "income" and "consult" in a["name"].lower())
    cl = ok(c.post("/api/clients", json={"name": f"Fixture Client {uuid.uuid4().hex[:5]}"}))
    project = ok(c.post("/api/projects", json={
        "name": f"Fixture Residence {uuid.uuid4().hex[:5]}", "client_id": cl["id"],
        "project_type": "Residential", "engagement_type": "consultancy"}))
    pid = project.get("id") or project.get("project", {}).get("id")
    inv = ok(c.post("/api/invoices", json={
        "client_id": cl["id"], "project_id": pid, "doc_type": "invoice", "status": "draft",
        "tax_rate": 0, "items": [{"description": "Design fee - concept", "quantity": 1, "rate": 100000}]}))
    check(case, "invoice total", 100000, inv["total"])
    ok(c.patch(f"/api/invoices/{inv['id']}/status", json={"status": "sent"}))
    pl0 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    due = ok(c.post("/api/accounting/receivables", json={
        "invoice_id": inv["id"], "name": f"Invoice {inv['number']}", "amount": 100000,
        "due_date": "2026-08-15", "income_account_id": income["id"]}))
    before = balance(c, "Bank - Primary")
    key = f"fixture-{uuid.uuid4().hex}"
    body = {"source_type": "other_receivable", "source_id": due["id"], "amount": 40000,
            "date": "2026-08-20", "bank_account_id": bank, "payment_method": "upi",
            "reference": inv["number"]}
    ok(c.post("/api/accounting/collections/receive", json=body, headers={"Idempotency-Key": key}))
    retry = c.post("/api/accounting/collections/receive", json=body, headers={"Idempotency-Key": key})
    check(case, "retry with the same key accepted without a new posting", True, retry.status_code in (200, 201, 409))
    check(case, "bank receipt", 40000, round(balance(c, "Bank - Primary") - before, 2))
    rows = ok(c.get("/api/accounting/receivables"))
    rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
    row = next(r for r in rows if r.get("id") == due["id"])
    outstanding = row.get("outstanding", row.get("balance", float(row.get("amount", 0)) - float(row.get("received_amount", 0))))
    check(case, "outstanding on Collections Due", 60000, round(float(outstanding), 2))
    pl1 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "cash basis: income booked = cash received (one sale, not two)", 40000, round(pl1["income"] - pl0["income"], 2))
    jes = ok(c.get("/api/journal-entries", params={"limit": 500, "client_id": cl["id"]}))
    jes = jes.get("items", jes) if isinstance(jes, dict) else jes
    live = [j for j in jes if not j.get("reversed") and not str(j.get("source", "")).endswith("_reversal")]
    check(case, "postings for this client after a retried receipt", 1, len(live))
    led = ok(c.get(f"/api/accounting/ledger/client/{cl['id']}"))
    received = led.get("total_received", led.get("received", led.get("total_credit")))
    if received is not None:
        check(case, "client ledger received", 40000, round(float(received), 2))
    pled = ok(c.get(f"/api/accounting/ledger/project/{pid}"))
    pin = pled.get("income", pled.get("total_income", pled.get("received")))
    if pin is not None:
        check(case, "project ledger income", 40000, round(float(pin), 2))
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)


def case_commission(c) -> None:
    case = "commission"
    bank = accounts(c)["Bank - Primary"]["id"]
    vendor = ok(c.post("/api/vendors", json={"name": f"Fixture Stone Supplier {uuid.uuid4().hex[:5]}"}))
    vid = vendor.get("id") or vendor.get("vendor", {}).get("id")
    pl0 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    planned = ok(c.post(f"/api/vendors/{vid}/commissions", json={
        "amount": 25000, "due_date": "2026-09-30", "recognition": "planned",
        "reference": "Client bought Rs 5,00,000 of stone directly from the supplier"}))
    cid = planned.get("id") or planned.get("commission", {}).get("id")
    check(case, "planned commission posts nothing", pl0["income"], pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")["income"])
    ok(c.post("/api/accounting/collections/receive", headers={"Idempotency-Key": f"fx-{uuid.uuid4().hex}"}, json={
        "source_type": "vendor_commission", "source_id": cid, "amount": 10000, "date": "2026-10-05",
        "bank_account_id": bank, "payment_method": "bank_transfer"}))
    rows = ok(c.get(f"/api/vendors/{vid}/commissions"))
    rows = rows if isinstance(rows, list) else next(v for v in rows.values() if isinstance(v, list))
    row = next(r for r in rows if r["id"] == cid)
    check(case, "commission collected", 10000, row.get("received_amount"))
    check(case, "commission outstanding", 15000, round(25000 - float(row.get("received_amount") or 0), 2))
    pl1 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "firm income = commission received, not the Rs 5,00,000 purchase", 10000, round(pl1["income"] - pl0["income"], 2))
    trial_balance_ok(c, case)


def case_gold_and_personal(c) -> None:
    case = "gold"
    bank = accounts(c)["Bank - Primary"]["id"]
    before = balance(c, "Bank - Primary")
    pl0 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    ok(c.post("/api/accounting/non-operating", json={
        "kind": "gold_purchase", "date": "2026-09-01", "amount": 200000,
        "bank_account_id": bank, "notes": "20 g at Rs 10,000/g"}))
    check(case, "gold carried as an asset", 200000, balance(c, "Investments - Gold"))
    ok(c.post("/api/accounting/non-operating", json={
        "kind": "owner_withdrawal", "date": "2026-09-02", "amount": 15000,
        "bank_account_id": bank, "notes": "Owner's home electricity bill"}))
    # Owner Drawings is an equity account (credit-normal), so a withdrawal
    # shows as a negative balance: it reduces the owner's equity.
    check(case, "personal bill goes to Owner Drawings (reduces equity)", -15000, balance(c, "Owner Drawings"))
    check(case, "bank down by gold + personal bill", -215000, round(balance(c, "Bank - Primary") - before, 2))
    pl1 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "neither touches profit", pl0["net"], pl1["net"])
    # Partial sale: the ERP has no investment register (quantity, partial sale,
    # realised gain). Recorded here as the accountant would, by journal:
    # sell 10 g for Rs 1,20,000; carrying value of 10 g = Rs 1,00,000; gain Rs 20,000.
    acc = accounts(c)
    gain = acc.get("Gain on Sale of Investments") or ok(c.post("/api/accounts", json={
        "name": "Gain on Sale of Investments", "type": "income"}))
    ok(c.post("/api/journal-entries", json={
        "date": "2026-10-15", "narration": "Sold 10 g gold (half of holding)",
        "lines": [
            {"account_id": bank, "debit": 120000, "credit": 0},
            {"account_id": acc["Investments - Gold"]["id"], "debit": 0, "credit": 100000},
            {"account_id": gain["id"], "debit": 0, "credit": 20000},
        ]}))
    check(case, "gold carrying value after selling half", 100000, balance(c, "Investments - Gold"))
    pl2 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "realised gain in P&L", 20000, round(pl2["income"] - pl1["income"], 2))
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)


def case_year_end(c) -> None:
    case = "year-end"
    acc = accounts(c)
    bank = acc["Bank - Primary"]["id"]
    income = next(a for a in acc.values() if a["type"] == "income" and "consult" in a["name"].lower())
    ok(c.post("/api/accounting/income", json={
        "date": "2026-03-31", "amount": 11000, "income_account_id": income["id"],
        "bank_account_id": bank, "reference": "FY 2025-26 last day"}))
    ok(c.post("/api/accounting/income", json={
        "date": "2026-04-01", "amount": 7000, "income_account_id": income["id"],
        "bank_account_id": bank, "reference": "FY 2026-27 first day"}))
    prev = pl_totals(c, fy="2025-26")
    check(case, "31 March lands in FY 2025-26 only", 11000, prev["income"])
    cur_first = pl_totals(c, from_date="2026-04-01", to_date="2026-04-01")
    check(case, "1 April lands in FY 2026-27", 7000, cur_first["income"])
    opening = balance(c, "Bank - Primary", as_of="2026-03-31")
    closing = balance(c, "Bank - Primary", as_of="2027-03-31")
    cf = ok(c.get("/api/accounting/reports/cash-flow", params={"fy": "2026-27"}))
    cf_open = cf.get("opening_cash", cf.get("opening_balance", cf.get("opening")))
    cf_close = cf.get("closing_cash", cf.get("closing_balance", cf.get("closing")))
    cf_net = cf.get("net_change", cf.get("net_cash_flow", cf.get("net")))
    check(case, "bank opening on 1 April = closing on 31 March", 11000, opening)
    if cf_open is not None and cf_close is not None and cf_net is not None:
        check(case, "cash flow: opening + net = closing", round(float(cf_open) + float(cf_net), 2), round(float(cf_close), 2))
    else:
        RESULTS.append({"case": case, "check": "cash-flow keys", "expected": "opening/net/closing",
                        "observed": sorted(cf.keys()) if isinstance(cf, dict) else type(cf).__name__, "pass": None})
        print("INFO  cash-flow keys:", sorted(cf.keys()) if isinstance(cf, dict) else cf)
    check(case, "FY 2026-27 bank closing (as of 31 Mar 2027)", closing, balance(c, "Bank - Primary"))
    trial_balance_ok(c, case, fy="2025-26")
    trial_balance_ok(c, case, fy="2026-27")
    balance_sheet_ok(c, case, fy="2026-27")


def case_cash_deposit(c) -> None:
    """Owner, 2026-11-23: Rs 2,00,000 cash in hand, Rs 50,000 deposited into SBI."""
    case = "cash-deposit"
    acc = accounts(c)
    cash = acc["Cash"]["id"]
    sbi = acc.get("SBI Bank") or ok(c.post("/api/accounts", json={
        "name": "SBI Bank", "type": "asset", "is_bank": True}))
    ok(c.post("/api/accounting/non-operating", json={
        "kind": "owner_investment", "date": "2026-11-01", "amount": 200000,
        "bank_account_id": cash, "notes": "Cash in hand brought in"}))
    cash0, sbi0 = balance(c, "Cash"), balance(c, "SBI Bank")
    pl0 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    out = ok(c.post("/api/accounting/non-operating", json={
        "kind": "own_transfer", "date": "2026-11-23", "amount": 50000,
        "bank_account_id": cash, "to_account_id": sbi["id"], "reference": "Deposit slip 1123"}))
    check(case, "narration names the deposit", "Cash deposited into SBI Bank",
          out["journal"]["narration"].split(" - ")[0])
    check(case, "cash down by 50,000", -50000, round(balance(c, "Cash") - cash0, 2))
    check(case, "SBI up by 50,000", 50000, round(balance(c, "SBI Bank") - sbi0, 2))
    check(case, "profit unchanged", pl0["net"], pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")["net"])
    over = c.post("/api/accounting/non-operating", json={
        "kind": "own_transfer", "date": "2026-11-23", "amount": round(balance(c, "Cash") + 0.01, 2),
        "bank_account_id": cash, "to_account_id": sbi["id"]})
    check(case, "depositing more cash than in hand is refused", 409, over.status_code)
    same = c.post("/api/accounting/non-operating", json={
        "kind": "own_transfer", "date": "2026-11-23", "amount": 10,
        "bank_account_id": cash, "to_account_id": cash})
    check(case, "same account on both sides is refused", 400, same.status_code)
    ok(c.post("/api/accounting/non-operating", json={
        "kind": "own_transfer", "date": "2026-11-23", "amount": 5000,
        "bank_account_id": sbi["id"], "to_account_id": cash}))
    check(case, "cash withdrawn from SBI comes back to cash", -5000 + 50000, round(balance(c, "SBI Bank") - sbi0, 2))
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)


def main() -> None:
    admin = new_workspace()
    for fn in (case_loan, case_invoice, case_commission, case_gold_and_personal, case_year_end,
               case_cash_deposit):
        try:
            fn(admin)
        except Exception as exc:  # keep going so one gap does not hide the rest
            RESULTS.append({"case": fn.__name__, "check": "ran to completion", "expected": "no error",
                            "observed": str(exc)[:300], "pass": False})
            print(f"ERROR [{fn.__name__}] {exc}")
    failed = [r for r in RESULTS if r["pass"] is False]
    print(f"\n{len(RESULTS)} checks, {len(failed)} failed")
    out = os.environ.get("OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(RESULTS, fh, indent=2)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
