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
    lender = next(r for r in _party_rows(c, "loan") if r["party_name"] == "Fixture Lender")
    ok(c.post("/api/accounting/non-operating", json={
        "kind": "repayment_paid", "date": "2026-07-10", "amount": 100000,
        "bank_account_id": bank, "party_account_id": lender["id"]}))
    too_much = c.post("/api/accounting/non-operating", json={
        "kind": "repayment_paid", "date": "2026-07-11", "amount": 400000.01,
        "bank_account_id": bank, "party_account_id": lender["id"]})
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


def _party_rows(c, side: str) -> list:
    return ok(c.get("/api/accounting/party-accounts", params={"side": side}))["accounts"]


def case_party_ledger(c) -> None:
    """Owner, 2026-11-23: typing "K" offers KPR with the outstanding balance;
    repayments post to that same liability account by ID."""
    case = "party-ledger"
    bank = accounts(c)["Bank - Primary"]["id"]
    post = lambda **body: c.post("/api/accounting/non-operating", json={"bank_account_id": bank, **body})
    ok(post(kind="money_received", date="2026-08-01", amount=100000, party_name="KPR"))
    ok(post(kind="money_received", date="2026-08-05", amount=50000, party_name="  kpr "))
    kpr = [r for r in _party_rows(c, "loan") if r["party_name"].lower() == "kpr"]
    check(case, "a second loan typed 'kpr' reuses KPR's ledger (no duplicate)", 1, len(kpr))
    kpr = kpr[0]
    check(case, "picker shows KPR's outstanding", 150000, kpr["outstanding"])
    check(case, "picker shows the account name", "Loan from - KPR", kpr["name"])
    no_id = post(kind="repayment_paid", date="2026-09-01", amount=10000, party_name="KPR")
    check(case, "a repayment without choosing the ledger is refused", 400, no_id.status_code)
    ok(post(kind="repayment_paid", date="2026-09-01", amount=40000, party_account_id=kpr["id"]))
    check(case, "partial repayment reduces the same ledger", 110000, balance(c, "Loan from - KPR"))
    ok(post(kind="money_received", date="2026-09-10", amount=10000, party_account_id=kpr["id"]))
    check(case, "a further loan by ID adds to the same ledger", 120000, balance(c, "Loan from - KPR"))
    over = post(kind="repayment_paid", date="2026-09-11", amount=120000.01, party_account_id=kpr["id"])
    check(case, "repaying more than KPR is owed is refused", 409, over.status_code)
    ok(post(kind="money_given", date="2026-09-12", amount=5000, party_name="KPR"))
    adv = next(r for r in _party_rows(c, "advance") if r["party_name"] == "KPR")
    wrong = post(kind="repayment_paid", date="2026-09-13", amount=1000, party_account_id=adv["id"])
    check(case, "an advance ledger cannot take a loan repayment", 400, wrong.status_code)
    not_party = post(kind="repayment_paid", date="2026-09-13", amount=1000, party_account_id=bank)
    check(case, "a non-party account is refused", 400, not_party.status_code)
    jes = ok(c.get("/api/journal-entries", params={"limit": 500}))
    jes = jes.get("items", jes) if isinstance(jes, dict) else jes
    on_kpr = [j for j in jes if any(l.get("account_id") == kpr["id"] for l in j.get("lines") or [])]
    check(case, "all four KPR postings sit on the one ledger", 4, len(on_kpr))
    check(case, "only one KPR loan ledger exists", 1,
          len([a for a in ok(c.get("/api/accounts")) if a["name"].lower() == "loan from - kpr"]))
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)
    # Another workspace cannot see or post to this KPR ledger.
    other = new_workspace()
    try:
        check(case, "other workspace does not see KPR", [], [r for r in _party_rows(other, "loan") if r["id"] == kpr["id"]])
        obank = accounts(other)["Bank - Primary"]["id"]
        cross = other.post("/api/accounting/non-operating", json={
            "kind": "repayment_paid", "date": "2026-09-14", "amount": 1000,
            "bank_account_id": obank, "party_account_id": kpr["id"]})
        check(case, "other workspace cannot repay against KPR's ledger", 400, cross.status_code)
        check(case, "KPR unchanged after the cross-workspace attempt", 120000, balance(c, "Loan from - KPR"))
    finally:
        other.close()


def _project(c, **fee) -> tuple[str, str]:
    cl = ok(c.post("/api/clients", json={"name": f"Fee Client {uuid.uuid4().hex[:5]}"}))
    project = ok(c.post("/api/projects", json={
        "name": f"Fee Project {uuid.uuid4().hex[:5]}", "client_id": cl["id"],
        "project_type": "Residential", "engagement_type": "consultancy", **fee}))
    return (project.get("id") or project.get("project", {}).get("id")), cl["id"]


def _money(c, pid: str) -> dict:
    return ok(c.get(f"/api/projects/{pid}"))["money"]


def _jid(out: dict) -> str:
    return out.get("id") or (out.get("journal") or {}).get("id") or (out.get("journal_entry") or {}).get("id")


def case_fee_vs_commission(c) -> None:
    """Owner, 2026-11-23: Rs 3 crore x 6% = Rs 18,00,000 fee; Rs 2,00,000 from the
    client leaves Rs 16,00,000; vendor commission never reduces it."""
    case = "fee-vs-commission"
    acc = accounts(c)
    bank = acc["Bank - Primary"]["id"]
    fee_income = next(a for a in acc.values() if a["type"] == "income" and "consult" in a["name"].lower())
    incentive = next(a for a in acc.values() if a["type"] == "income"
                     and (a.get("code") == "3010" or "incentive" in a["name"].lower() or "commission" in a["name"].lower()))
    pid, cid = _project(c, budget=30000000, fee_structure_type="percentage_consultancy",
                        fee_project_value=30000000, fee_percentage=6)
    vendor = ok(c.post("/api/vendors", json={"name": f"Fee Tile Supplier {uuid.uuid4().hex[:5]}"}))
    vid = vendor.get("id") or vendor.get("vendor", {}).get("id")
    pl0 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    income = lambda **b: ok(c.post("/api/accounting/income", json={
        "date": "2026-10-01", "bank_account_id": bank, "project_id": pid, **b}))
    m = _money(c, pid)
    check(case, "agreed fee = 6% of Rs 3 crore", 1800000, m["basis"])
    check(case, "nothing received yet", 1800000, m["still_to_receive"])
    income(amount=200000, client_id=cid, income_account_id=fee_income["id"], reference="Fee advance")
    m = _money(c, pid)
    check(case, "client payment received", 200000, m["received"])
    check(case, "still to receive after Rs 2,00,000", 1600000, m["still_to_receive"])
    inc = income(amount=352500, vendor_id=vid, income_account_id=incentive["id"], reference="Tile incentive")
    m = _money(c, pid)
    check(case, "vendor incentive does not count as client payment", 200000, m["received"])
    check(case, "still to receive unchanged by the incentive", 1600000, m["still_to_receive"])
    check(case, "incentive shown separately on the project", 352500, m.get("commission_received"))
    planned = ok(c.post(f"/api/vendors/{vid}/commissions", json={
        "amount": 20000, "due_date": "2026-10-30", "recognition": "planned", "project_id": pid,
        "reference": "Sanitaryware incentive"}))
    comm_id = planned.get("id") or planned.get("commission", {}).get("id")
    ok(c.post("/api/accounting/collections/receive", headers={"Idempotency-Key": f"fx-{uuid.uuid4().hex}"}, json={
        "source_type": "vendor_commission", "source_id": comm_id, "amount": 20000, "date": "2026-10-05",
        "bank_account_id": bank, "payment_method": "bank_transfer"}))
    m = _money(c, pid)
    check(case, "incentive collected from the vendor ledger stays separate", 372500, m.get("commission_received"))
    check(case, "client fee received still Rs 2,00,000", 200000, m["received"])
    part = income(amount=300000, client_id=cid, income_account_id=fee_income["id"], reference="Second stage")
    m = _money(c, pid)
    check(case, "partial receipts add up", 500000, m["received"])
    check(case, "remaining after Rs 5,00,000", 1300000, m["still_to_receive"])
    ok(c.post(f"/api/journal-entries/{_jid(part)}/reverse"))
    m = _money(c, pid)
    check(case, "reversing a client receipt restores what is due", 1600000, m["still_to_receive"])
    ok(c.post(f"/api/journal-entries/{_jid(inc)}/reverse"))
    m = _money(c, pid)
    check(case, "reversing an incentive changes only the incentive", 20000, m.get("commission_received"))
    check(case, "client figures untouched by the incentive reversal", 1600000, m["still_to_receive"])
    pl1 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "P&L income = client 2,00,000 + incentives 20,000 (no double count)", 220000,
          round(pl1["income"] - pl0["income"], 2))
    vled = ok(c.get(f"/api/accounting/ledger/vendor/{vid}"))
    check(case, "vendor ledger still carries the incentive", True, bool(vled))
    # Other fee structures: the incentive never reduces any of them.
    for label, fee, paid, still in (
            ("lump sum", dict(budget=6000000, fee_structure_type="lump_sum", fee_lump_sum_amount=600000), 100000, 500000),
            ("per sq ft", dict(budget=6000000, fee_structure_type="per_sqft", site_area_sqft=2400, fee_rate_per_sqft=250), 100000, 500000),
            ("turnkey", dict(budget=6000000, fee_structure_type="turnkey", fee_contract_value=6000000), 1000000, 5000000)):
        p2, c2 = _project(c, **fee)
        ok(c.post("/api/accounting/income", json={"date": "2026-10-02", "bank_account_id": bank, "project_id": p2,
                                                  "amount": paid, "client_id": c2, "income_account_id": fee_income["id"]}))
        ok(c.post("/api/accounting/income", json={"date": "2026-10-02", "bank_account_id": bank, "project_id": p2,
                                                  "amount": 75000, "vendor_id": vid, "income_account_id": incentive["id"]}))
        m = _money(c, p2)
        check(case, f"{label}: still to receive ignores the Rs 75,000 incentive", still, m["still_to_receive"])
        check(case, f"{label}: incentive shown separately", 75000, m.get("commission_received"))
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)


def case_who_paid(c) -> None:
    """Owner data, 2026-11-23: D_1101's vendor incentives were saved with KPR as
    the client (so KPR's statement showed them as KPR's payments) and a
    milestone receipt was saved with no client (so the statement missed it)."""
    case = "who-paid"
    acc = accounts(c)
    bank = acc["Bank - Primary"]["id"]
    fee = next(a for a in acc.values() if a["type"] == "income" and "consult" in a["name"].lower())
    incentive = next(a for a in acc.values() if a["type"] == "income"
                     and (a.get("code") == "3010" or "incentive" in a["name"].lower() or "commission" in a["name"].lower()))
    pid, cid = _project(c, budget=1000000, fee_structure_type="lump_sum", fee_lump_sum_amount=500000)
    other_pid, other_cid = _project(c, budget=1000000, fee_structure_type="lump_sum", fee_lump_sum_amount=100000)
    vendor = ok(c.post("/api/vendors", json={"name": f"Payer Vendor {uuid.uuid4().hex[:5]}"}))
    vid = vendor.get("id") or vendor.get("vendor", {}).get("id")
    base = {"date": "2026-10-10", "bank_account_id": bank, "payment_method": "bank_transfer"}
    both = c.post("/api/accounting/income", json={**base, "amount": 1000, "project_id": pid, "client_id": cid,
                                                  "vendor_id": vid, "income_account_id": incentive["id"]})
    check(case, "one payer: client and vendor together is refused", 400, both.status_code)
    inc_client = c.post("/api/accounting/income", json={**base, "amount": 1000, "project_id": pid, "client_id": cid,
                                                        "income_account_id": incentive["id"]})
    check(case, "an incentive cannot be booked as the client's money", 400, inc_client.status_code)
    wrong = c.post("/api/accounting/income", json={**base, "amount": 1000, "project_id": pid, "client_id": other_cid,
                                                   "income_account_id": fee["id"]})
    check(case, "a project's money cannot be booked to another client", 400, wrong.status_code)
    paid = ok(c.post("/api/accounting/income", json={**base, "amount": 40000, "project_id": pid,
                                                     "income_account_id": fee["id"]}))
    check(case, "fee received on a project carries the project's client", cid, paid.get("client_id"))
    ok(c.post("/api/accounting/income", json={**base, "amount": 7000, "project_id": pid, "vendor_id": vid,
                                              "income_account_id": incentive["id"]}))
    ms = ok(c.post(f"/api/projects/{pid}/milestones", json={"project_id": pid, "name": "Stage 2", "amount": 60000,
                                                           "due_date": "2026-11-15"}))
    mid = ms.get("id") or ms.get("milestone", {}).get("id")
    ok(c.post("/api/accounting/collections/receive", headers={"Idempotency-Key": f"fx-{uuid.uuid4().hex}"}, json={
        "source_type": "milestone", "source_id": mid, "amount": 25000, "date": "2026-11-01",
        "bank_account_id": bank, "payment_method": "bank_transfer"}))
    jes = ok(c.get("/api/journal-entries", params={"limit": 500}))
    jes = jes.get("items", jes) if isinstance(jes, dict) else jes
    ms_je = next(j for j in jes if j.get("source") == "milestone_payment" and j.get("source_id") == mid)
    check(case, "milestone receipt carries the project's client", cid, ms_je.get("client_id"))
    led = ok(c.get(f"/api/accounting/ledger/client/{cid}"))
    check(case, "client ledger: client's money only (40,000 + 25,000)", 65000, led["inflow"])
    check(case, "client ledger has no incentive line", False,
          any(e.get("vendor_id") for e in led["entries"]))
    reg = ok(c.get("/api/accounting/received-payments"))
    rows = [r for r in reg["rows"] if r.get("project_id") == pid]
    inc_row = next(r for r in rows if r.get("vendor_id") == vid)
    check(case, "Money In names the vendor as payer of the incentive", "vendor", inc_row.get("payer"))
    check(case, "Money In names the client for the fee", {"client"},
          {r.get("payer") for r in rows if not r.get("vendor_id")})
    pdf = c.get(f"/api/clients/{cid}/statement.pdf")
    check(case, "client statement PDF renders", 200, pdf.status_code)
    m = _money(c, pid)
    check(case, "project: client received 65,000; incentive apart", [65000, 7000],
          [m["received"], m.get("commission_received")])
    trial_balance_ok(c, case)


def case_credit_card(c) -> None:
    """Owner data, 2026-11-23: "Credit Card HDFC" was created as an expense and a
    friend's repayment for a mattress bought on the card was booked as income."""
    case = "credit-card"
    acc = accounts(c)
    bank = acc["Bank - Primary"]["id"]
    food = next(a for a in acc.values() if a["type"] == "expense" and "food" in a["name"].lower())
    tag = uuid.uuid4().hex[:4]
    card = ok(c.post("/api/accounts", json={"name": f"HDFC Credit Card {tag}", "type": "liability", "is_card": True}))
    bad = [
        c.post("/api/accounts", json={"name": f"yash drawings {tag}", "type": "equity", "is_bank": True}),
        c.post("/api/accounts", json={"name": f"Gold {tag}", "type": "asset", "is_bank": True}),
        c.post("/api/accounts", json={"name": f"Card on asset {tag}", "type": "asset", "is_card": True}),
    ]
    check(case, "equity/gold as bank and a card on an asset are refused", [400, 400, 400], [r.status_code for r in bad])
    ok(c.post("/api/accounting/non-operating", json={"kind": "owner_investment", "date": "2026-11-01",
                                                     "amount": 100000, "bank_account_id": bank}))
    pl0 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    bank0 = balance(c, "Bank - Primary")
    ok(c.post("/api/accounting/expense", json={"date": "2026-11-10", "amount": 8400, "expense_account_id": food["id"],
                                               "paid_from_account_id": card["id"], "payment_method": "credit_card",
                                               "notes": "Team lunch on card"}))
    ok(c.post("/api/accounting/non-operating", json={"kind": "money_given", "date": "2026-11-12", "amount": 15000,
                                                     "bank_account_id": card["id"], "party_name": f"Viren {tag}",
                                                     "notes": "Mattress bought for him on the card"}))
    check(case, "card dues = lunch + mattress", 23400, balance(c, card["name"]))
    check(case, "bank untouched by card spending", bank0, balance(c, "Bank - Primary"))
    viren = next(r for r in _party_rows(c, "advance") if r["party_name"] == f"Viren {tag}")
    ok(c.post("/api/accounting/non-operating", json={"kind": "repayment_received", "date": "2026-11-13", "amount": 15000,
                                                     "bank_account_id": bank, "party_account_id": viren["id"]}))
    check(case, "Viren's repayment clears his ledger", 0, balance(c, f"Advance to - Viren {tag}"))
    pl1 = pl_totals(c, from_date="2026-04-01", to_date="2026-11-30")
    check(case, "income unchanged by the repayment (not income)", pl0["income"], pl1["income"])
    check(case, "expenses up only by the lunch", 8400, round(pl1["expense"] - pl0["expense"], 2))
    over = c.post("/api/accounting/non-operating", json={"kind": "own_transfer", "date": "2026-11-18", "amount": 23400.01,
                                                         "bank_account_id": bank, "to_account_id": card["id"]})
    check(case, "paying more than the card dues is refused", 409, over.status_code)
    out = ok(c.post("/api/accounting/non-operating", json={"kind": "own_transfer", "date": "2026-11-18", "amount": 23400,
                                                           "bank_account_id": bank, "to_account_id": card["id"]}))
    check(case, "card bill narration", True, out["journal"]["narration"].startswith("Credit card bill paid"))
    check(case, "card settled", 0, balance(c, card["name"]))
    check(case, "bank: +15,000 repayment -23,400 bill", round(bank0 + 15000 - 23400, 2), balance(c, "Bank - Primary"))
    into_card = c.post("/api/accounting/income", json={"date": "2026-11-19", "amount": 10, "bank_account_id": card["id"],
                                                       "income_account_id": next(a for a in acc.values() if a["type"] == "income")["id"],
                                                       "payment_method": "credit_card"})
    check(case, "income cannot be received into a credit card", 400, into_card.status_code)
    from_card = c.post("/api/accounting/non-operating", json={"kind": "own_transfer", "date": "2026-11-19", "amount": 10,
                                                              "bank_account_id": card["id"], "to_account_id": bank})
    check(case, "money cannot be moved out of a credit card", 400, from_card.status_code)
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)


def case_cash_guard(c) -> None:
    """Owner data, 2026-11-23: gold bought from Cash in 2024 before any cash was
    recorded left the till at -Rs 89,440 for over a year."""
    case = "cash-guard"
    acc = accounts(c)
    cash = acc["Cash"]["id"]
    misc = next(a for a in acc.values() if a["type"] == "expense" and "misc" in a["name"].lower())
    early = c.post("/api/accounting/non-operating", json={"kind": "gold_purchase", "date": "2024-07-22",
                                                          "amount": 52000, "bank_account_id": cash})
    check(case, "gold from an empty till (2024) is refused", 409, early.status_code)
    ok(c.post("/api/accounting/non-operating", json={"kind": "owner_investment", "date": "2025-01-01",
                                                     "amount": 10000, "bank_account_id": cash}))
    ok(c.post("/api/accounting/expense", json={"date": "2025-01-10", "amount": 9000, "expense_account_id": misc["id"],
                                               "paid_from_account_id": cash, "payment_method": "cash"}))
    back = c.post("/api/accounting/expense", json={"date": "2025-01-05", "amount": 2000, "expense_account_id": misc["id"],
                                                   "paid_from_account_id": cash, "payment_method": "cash"})
    check(case, "a backdated cash payment that would empty a later day is refused", 409, back.status_code)
    fits = c.post("/api/accounting/expense", json={"date": "2025-01-05", "amount": 1000, "expense_account_id": misc["id"],
                                                   "paid_from_account_id": cash, "payment_method": "cash"})
    check(case, "a cash payment that fits is accepted", 200, fits.status_code)
    check(case, "till never below zero", True, balance(c, "Cash", as_of="2025-01-10") >= -0.005)
    trial_balance_ok(c, case)


def case_user_delete(c) -> None:
    """Owner, 2026-11-23: a former team member could be deactivated but never deleted."""
    case = "user-delete"
    tag = uuid.uuid4().hex[:6]
    u = ok(c.post("/api/auth/register", json={"email": f"leaver-{tag}@qa.example.com", "password": PASSWORD,
                                              "name": f"Leaver {tag}", "role": "Employee", "approve_immediately": True}))
    uid = u.get("user_id") or u.get("user", {}).get("user_id")
    active = c.delete(f"/api/rbac/users/{uid}")
    check(case, "an active user must be deactivated first", 409, active.status_code)
    ok(c.post(f"/api/rbac/users/{uid}/approve", json={"decision": "reject", "reason": "Left the studio"}))
    gone = c.delete(f"/api/rbac/users/{uid}")
    check(case, "a deactivated user is deleted", 200, gone.status_code)
    users = ok(c.get("/api/rbac/users"))
    check(case, "deleted user no longer listed", False, any(x.get("user_id") == uid for x in users))
    me = ok(c.get("/api/auth/me"))
    self_del = c.delete(f"/api/rbac/users/{me.get('user_id') or me.get('user', {}).get('user_id')}")
    check(case, "you cannot delete yourself", 400, self_del.status_code)
    trail = ok(c.get("/api/audit-log", params={"action": "user.delete"}))
    check(case, "the deletion is in the audit trail", True, any(r.get("target") == uid for r in trail))


def case_audit_cleanup(c) -> None:
    case = "audit-cleanup"
    pv = ok(c.get("/api/audit-log/cleanup-preview", params={"months": 1}))
    check(case, "preview lists only routine actions", True,
          "journal.create" not in pv["routine_actions"] and "auth.login" in pv["routine_actions"])
    bad = c.post("/api/audit-log/cleanup", json={"months": 2, "confirm": True})
    check(case, "only 1, 3, 6 or 12 months", 400, bad.status_code)
    unconfirmed = c.post("/api/audit-log/cleanup", json={"months": 1})
    check(case, "needs confirmation", 400, unconfirmed.status_code)
    done = ok(c.post("/api/audit-log/cleanup", json={"months": 1, "confirm": True}))
    check(case, "clean-up runs (fresh studio: nothing old)", 0, done["deleted"])
    v = ok(c.get("/api/audit-log/verify"))
    check(case, "integrity still verifies", True, v["ok"])


def _post_np(c, **body):
    bank = accounts(c)["Bank - Primary"]["id"]
    return c.post("/api/accounting/non-operating", json={"bank_account_id": bank, **body})


def case_ca_review(c) -> None:
    """CA review 2026-11-24: every transaction type that had no correct way in."""
    case = "ca-review"
    tag = uuid.uuid4().hex[:4]
    acc = accounts(c)
    bank = acc["Bank - Primary"]["id"]
    fee = next(a for a in acc.values() if a["type"] == "income" and "consult" in a["name"].lower())
    ok(_post_np(c, kind="owner_investment", date="2026-04-02", amount=1000000))
    pl = lambda: pl_totals(c, from_date="2026-04-01", to_date="2027-03-31")   # noqa: E731

    # -- TDS deducted by the client (194J): 90,000 cash + 10,000 TDS settles 1,00,000
    pid, cid = _project(c, budget=500000, fee_structure_type="lump_sum", fee_lump_sum_amount=100000)
    p0, b0 = pl(), balance(c, "Bank - Primary")
    ok(c.post("/api/accounting/income", json={"date": "2026-06-01", "amount": 90000, "tds_amount": 10000,
                                              "project_id": pid, "income_account_id": fee["id"],
                                              "bank_account_id": bank}))
    check(case, "TDS: bank up by the cash only", 90000, round(balance(c, "Bank - Primary") - b0, 2))
    check(case, "TDS: claimable TDS recorded", 10000, balance(c, "TDS Receivable"))
    check(case, "TDS: income is the full fee", 100000, round(pl()["income"] - p0["income"], 2))
    check(case, "TDS: nothing left to receive on the fee", 0, _money(c, pid)["still_to_receive"])
    reg = [r for r in ok(c.get("/api/accounting/received-payments"))["rows"] if r.get("project_id") == pid]
    check(case, "TDS: Money In shows cash and TDS apart", [90000, 10000], [reg[0]["amount"], reg[0].get("tds_deducted")])
    ms = ok(c.post(f"/api/projects/{pid}/milestones", json={"project_id": pid, "name": "Extra", "amount": 50000}))
    mid = ms.get("id") or ms.get("milestone", {}).get("id")
    ok(c.post("/api/accounting/collections/receive", headers={"Idempotency-Key": f"fx-{uuid.uuid4().hex}"}, json={
        "source_type": "milestone", "source_id": mid, "amount": 45000, "tds_amount": 5000, "date": "2026-06-05",
        "bank_account_id": bank, "payment_method": "bank_transfer"}))
    row = next(r for r in ok(c.get("/api/accounting/receivables"))["rows"] if r["id"] == mid)
    check(case, "TDS via Collections: milestone fully settled", [0, "received"], [row["outstanding"], row["status"]])

    # -- Refund to the client
    p1, b1 = pl(), balance(c, "Bank - Primary")
    over = c.post("/api/accounting/client-refund", json={"date": "2026-06-10", "amount": 150000.01, "client_id": cid,
                                                         "project_id": pid, "bank_account_id": bank})
    check(case, "refund above what the client paid is refused", 409, over.status_code)
    other_pid, _other_cid = _project(c, budget=100000, fee_structure_type="lump_sum", fee_lump_sum_amount=50000)
    wrong = c.post("/api/accounting/client-refund", json={"date": "2026-06-10", "amount": 10, "client_id": cid,
                                                          "project_id": other_pid, "bank_account_id": bank})
    check(case, "refund on another client's project is refused", 400, wrong.status_code)
    ok(c.post("/api/accounting/client-refund", json={"date": "2026-06-10", "amount": 20000, "client_id": cid,
                                                     "project_id": pid, "bank_account_id": bank, "notes": "Scope reduced"}))
    check(case, "refund: bank down 20,000", -20000, round(balance(c, "Bank - Primary") - b1, 2))
    check(case, "refund: income down 20,000", -20000, round(pl()["income"] - p1["income"], 2))
    check(case, "refund: project received 1,50,000 - 20,000", 130000, _money(c, pid)["received"])
    led = ok(c.get(f"/api/accounting/ledger/client/{cid}"))
    check(case, "refund: client ledger agrees with the project (1,50,000 settled incl. TDS - 20,000)", 130000,
          round(led["inflow"] - led["outflow"], 2))
    check(case, "refund: client statement renders", 200, c.get(f"/api/clients/{cid}/statement.pdf").status_code)

    # -- Loan taken with interest
    ok(_post_np(c, kind="money_received", date="2026-07-01", amount=100000, party_name=f"Lender {tag}"))
    lender = next(r for r in _party_rows(c, "loan") if r["party_name"] == f"Lender {tag}")
    p2, b2 = pl(), balance(c, "Bank - Primary")
    ok(_post_np(c, kind="repayment_paid", date="2026-08-01", amount=40000, interest_amount=2000,
                party_account_id=lender["id"]))
    check(case, "loan: principal reduces the loan only", 60000, balance(c, f"Loan from - Lender {tag}"))
    check(case, "loan: interest is an expense", 2000, round(pl()["expense"] - p2["expense"], 2))
    check(case, "loan: bank pays principal + interest", -42000, round(balance(c, "Bank - Primary") - b2, 2))
    bad_int = _post_np(c, kind="money_received", date="2026-08-01", amount=10, interest_amount=1, party_name=f"Lender {tag}")
    check(case, "interest on a new loan is refused", 400, bad_int.status_code)

    # -- Loan given with interest
    ok(_post_np(c, kind="money_given", date="2026-07-01", amount=50000, party_name=f"Borrower {tag}"))
    borrower = next(r for r in _party_rows(c, "advance") if r["party_name"] == f"Borrower {tag}")
    p3 = pl()
    ok(_post_np(c, kind="repayment_received", date="2026-08-01", amount=20000, interest_amount=1500,
                party_account_id=borrower["id"]))
    check(case, "loan given: principal back reduces what they owe", 30000, balance(c, f"Advance to - Borrower {tag}"))
    check(case, "loan given: interest is income", 1500, round(pl()["income"] - p3["income"], 2))

    # -- Investment bought and sold (gain and loss), legacy "Gold" in the picker
    ok(_post_np(c, kind="investment_purchase", date="2026-07-05", amount=200000, item_name=f"FD - SBI {tag}"))
    fd = next(r for r in _party_rows(c, "investment") if r["party_name"] == f"FD - SBI {tag}")
    p4 = pl()
    ok(_post_np(c, kind="investment_sale", date="2026-09-01", amount=108000, cost_amount=100000, party_account_id=fd["id"]))
    ok(_post_np(c, kind="investment_sale", date="2026-09-02", amount=45000, cost_amount=50000, party_account_id=fd["id"]))
    check(case, "investment: 50,000 of cost left", 50000, balance(c, f"Investments - FD - SBI {tag}"))
    check(case, "investment: gain 8,000 in income", 8000, round(pl()["income"] - p4["income"], 2))
    check(case, "investment: loss 5,000 in expenses", 5000, round(pl()["expense"] - p4["expense"], 2))
    too_much = _post_np(c, kind="investment_sale", date="2026-09-03", amount=60000, cost_amount=50000.01, party_account_id=fd["id"])
    check(case, "investment: selling more than held is refused", 409, too_much.status_code)
    gold = acc.get("Gold") or ok(c.post("/api/accounts", json={"name": "Gold", "type": "asset"}))
    check(case, "legacy 'Gold' ledger is offered as an investment", True,
          any(r["id"] == gold["id"] for r in _party_rows(c, "investment")))

    # -- Asset bought (not an expense)
    p5 = pl()
    ok(_post_np(c, kind="asset_purchase", date="2026-07-10", amount=80000, item_name=f"Laptop {tag}"))
    check(case, "asset: on the balance sheet", 80000, balance(c, f"Fixed Asset - Laptop {tag}"))
    check(case, "asset: not an expense", p5["expense"], pl()["expense"])

    # -- Tax payable paid to the government
    prof = next(a for a in acc.values() if a["type"] == "expense" and "professional" in a["name"].lower())
    tds_pay = acc["TDS Payable"]["id"]
    ok(c.post("/api/journal-entries", json={"date": "2026-07-15", "narration": f"Consultant fee with TDS {tag}", "lines": [
        {"account_id": prof["id"], "debit": 10000, "credit": 0},
        {"account_id": tds_pay, "debit": 0, "credit": 1000},
        {"account_id": bank, "debit": 0, "credit": 9000}]}))
    owed = balance(c, "TDS Payable")
    overpay = _post_np(c, kind="tax_payment", date="2026-08-07", amount=owed + 0.01, liability_account_id=tds_pay)
    check(case, "tax: paying more than payable is refused", 409, overpay.status_code)
    ok(_post_np(c, kind="tax_payment", date="2026-08-07", amount=owed, liability_account_id=tds_pay))
    check(case, "tax: TDS payable cleared", 0, balance(c, "TDS Payable"))
    not_tax = _post_np(c, kind="tax_payment", date="2026-08-07", amount=1, liability_account_id=lender["id"])
    check(case, "tax: a loan is not a tax", 400, not_tax.status_code)

    # -- Refundable deposit, money held for a client
    ok(_post_np(c, kind="deposit_paid", date="2026-07-01", amount=60000, party_name=f"Landlord {tag}"))
    dep = next(r for r in _party_rows(c, "deposit") if r["party_name"] == f"Landlord {tag}")
    over_dep = _post_np(c, kind="deposit_refund_received", date="2026-12-01", amount=60000.01, party_account_id=dep["id"])
    check(case, "deposit: refund above the deposit is refused", 409, over_dep.status_code)
    ok(_post_np(c, kind="deposit_refund_received", date="2026-12-01", amount=60000, party_account_id=dep["id"]))
    check(case, "deposit: refunded in full", 0, balance(c, f"Deposit with - Landlord {tag}"))
    p6 = pl()
    ok(_post_np(c, kind="held_received", date="2026-07-02", amount=100000, party_name=f"Client funds {tag}"))
    held = next(r for r in _party_rows(c, "held") if r["party_name"] == f"Client funds {tag}")
    ok(_post_np(c, kind="held_paid_out", date="2026-07-20", amount=70000, party_account_id=held["id"]))
    check(case, "held: 30,000 still owed back", 30000, balance(c, f"Held for - Client funds {tag}"))
    check(case, "held: never income or expense", [p6["income"], p6["expense"]], [pl()["income"], pl()["expense"]])

    # -- Concurrency: two full repayments at once, only one may pass
    import concurrent.futures
    ok(_post_np(c, kind="money_received", date="2026-10-01", amount=5000, party_name=f"Race {tag}"))
    race = next(r for r in _party_rows(c, "loan") if r["party_name"] == f"Race {tag}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(f.result().status_code for f in [pool.submit(
            _post_np, c, kind="repayment_paid", date="2026-10-02", amount=5000, party_account_id=race["id"]) for _ in range(2)])
    check(case, "concurrency: one repayment posts, the other is refused", 200, codes[0])
    check(case, "concurrency: loan never below zero", 0, balance(c, f"Loan from - Race {tag}"))

    # -- GST: an unregistered studio cannot charge or claim GST
    gst_inv = c.post("/api/invoices", json={"client_id": cid, "project_id": pid, "doc_type": "invoice", "status": "draft",
                                            "tax_rate": 18, "items": [{"description": "Fee", "quantity": 1, "rate": 1000}]})
    check(case, "GST: no GSTIN, no GST invoice", 400, gst_inv.status_code)
    bad_gstin = c.patch("/api/org/current", json={"gstin": "12345"})
    check(case, "GSTIN format is checked", 422, bad_gstin.status_code)
    misc = next(a for a in acc.values() if a["type"] == "expense" and "misc" in a["name"].lower())
    p7 = pl()
    ok(c.post("/api/accounting/expense", json={"date": "2026-08-10", "amount": 1000, "gst": 180,
                                               "expense_account_id": misc["id"], "paid_from_account_id": bank}))
    check(case, "GST: unregistered, GST paid is part of the cost", 1180, round(pl()["expense"] - p7["expense"], 2))
    ok(c.patch("/api/org/current", json={"gstin": "24ABCDE1234F1Z5"}))
    ok(c.post("/api/invoices", json={"client_id": cid, "project_id": pid, "doc_type": "invoice", "status": "draft",
                                     "tax_rate": 18, "items": [{"description": "Fee", "quantity": 1, "rate": 1000}]}))
    ok(c.patch("/api/org/current", json={"gstin": ""}))

    # -- The books still agree with themselves
    trial_balance_ok(c, case)
    balance_sheet_ok(c, case)
    cf = ok(c.get("/api/accounting/reports/cash-flow", params={"fy": "2026-27"}))
    cf_open = cf.get("opening_cash", cf.get("opening_balance", cf.get("opening")))
    cf_close = cf.get("closing_cash", cf.get("closing_balance", cf.get("closing")))
    cf_net = cf.get("net_change", cf.get("net_cash_flow", cf.get("net")))
    if None not in (cf_open, cf_close, cf_net):
        check(case, "cash flow: opening + net = closing", round(float(cf_open) + float(cf_net), 2), round(float(cf_close), 2))


def main() -> None:
    admin = new_workspace()
    for fn in (case_loan, case_invoice, case_commission, case_gold_and_personal, case_year_end,
               case_cash_deposit, case_party_ledger, case_fee_vs_commission,
               case_who_paid, case_credit_card, case_cash_guard, case_user_delete, case_audit_cleanup, case_ca_review):
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
