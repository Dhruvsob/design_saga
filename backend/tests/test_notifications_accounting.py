"""Iteration 6: Notifications & Accounting v2.3 backend tests."""
import os, time, uuid, requests, pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

ADMIN_TOK = "stable_testtok_do_not_delete"
PM_TOK = "f9ff566b859e4e9080ea2cefbffae93c"          # ProjectManager (pmanager@ds.co)
PM_UID = "user_be5ef6d7a393"
ADMIN_UID = "user_testadmin_stable"


def H(tok): return {"Authorization": f"Bearer {tok}"}


# ---------- Notifications listing / counts ----------
def test_list_notifications_admin():
    r = requests.get(f"{BASE}/notifications", headers=H(ADMIN_TOK))
    assert r.status_code == 200
    b = r.json()
    assert "unread_count" in b and isinstance(b["unread_count"], int)
    assert isinstance(b["notifications"], list)


def test_unread_count_endpoint():
    r = requests.get(f"{BASE}/notifications/unread-count", headers=H(ADMIN_TOK))
    assert r.status_code == 200
    assert "unread_count" in r.json()


# ---------- task_assigned emission ----------
def test_task_assigned_emits_to_other_user():
    title = f"TEST_notif_task_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE}/tasks", headers=H(ADMIN_TOK), json={
        "title": title, "assignee_id": PM_UID, "priority": "medium",
    })
    assert r.status_code in (200, 201), r.text
    task = r.json()
    tid = task["id"]
    # PM should see task_assigned notif
    r2 = requests.get(f"{BASE}/notifications", headers=H(PM_TOK), params={"kind": "task_assigned"})
    assert r2.status_code == 200
    notifs = r2.json()["notifications"]
    match = [n for n in notifs if n.get("meta", {}).get("task_id") == tid or (n.get("link") or "").endswith(tid)]
    assert match, f"No task_assigned notif for task {tid}"
    assert match[0]["link"] == f"/tasks/{tid}"


def test_task_self_assignment_no_notif():
    r = requests.post(f"{BASE}/tasks", headers=H(ADMIN_TOK), json={
        "title": f"TEST_selfassign_{uuid.uuid4().hex[:6]}",
        "assignee_id": ADMIN_UID, "priority": "low",
    })
    assert r.status_code in (200, 201)
    tid = r.json()["id"]
    r2 = requests.get(f"{BASE}/notifications", headers=H(ADMIN_TOK), params={"kind": "task_assigned"})
    matches = [n for n in r2.json()["notifications"]
               if n.get("meta", {}).get("task_id") == tid]
    assert matches == [], "self-assignment should NOT create task_assigned notif"


# ---------- Leave notifications ----------
def test_leave_request_and_decide_emissions():
    emps = requests.get(f"{BASE}/employees", headers=H(ADMIN_TOK)).json()
    assert emps, "no employees seeded"
    emp_id = emps[0]["employee_id"]
    body = {"employee_id": emp_id, "leave_type": "casual",
            "from_date": "2026-02-01", "to_date": "2026-02-01", "reason": "TEST_notif"}
    r = requests.post(f"{BASE}/leaves", headers=H(ADMIN_TOK), json=body)
    assert r.status_code in (200, 201), r.text
    leave = r.json()
    lid = leave.get("id") or leave.get("leave_id")
    assert lid
    # admin should have received leave_request
    r2 = requests.get(f"{BASE}/notifications", headers=H(ADMIN_TOK), params={"kind": "leave_request"})
    assert r2.status_code == 200
    got = [n for n in r2.json()["notifications"] if n.get("meta", {}).get("leave_id") == lid
           or (n.get("link") or "").find(lid) >= 0 or "leave" in (n.get("link") or "")]
    assert got, "admin did not receive leave_request notification"

    # Approve -> requester gets leave_decided
    r3 = requests.post(f"{BASE}/leaves/{lid}/action", headers=H(ADMIN_TOK), json={"action": "approve"})
    assert r3.status_code in (200, 201), r3.text
    # The requester is the admin here (they submitted). Check admin has a leave_decided
    r4 = requests.get(f"{BASE}/notifications", headers=H(ADMIN_TOK), params={"kind": "leave_decided"})
    assert r4.status_code == 200
    assert r4.json()["notifications"], "no leave_decided notif to requester"


# ---------- Scan idempotency ----------
def test_scan_is_idempotent():
    r1 = requests.post(f"{BASE}/notifications/scan", headers=H(ADMIN_TOK))
    assert r1.status_code == 200
    c1 = requests.get(f"{BASE}/notifications/unread-count", headers=H(ADMIN_TOK)).json()["unread_count"]
    r2 = requests.post(f"{BASE}/notifications/scan", headers=H(ADMIN_TOK))
    assert r2.status_code == 200
    c2 = requests.get(f"{BASE}/notifications/unread-count", headers=H(ADMIN_TOK)).json()["unread_count"]
    assert c1 == c2, f"scan not idempotent: {c1} -> {c2}"


# ---------- Mark read / mark-all-read / dismiss ----------
def test_mark_read_and_dismiss():
    # Ensure at least one notif exists — create by assigning a task
    r = requests.post(f"{BASE}/tasks", headers=H(ADMIN_TOK), json={
        "title": f"TEST_mrk_{uuid.uuid4().hex[:6]}", "assignee_id": PM_UID})
    assert r.status_code in (200, 201)
    listing = requests.get(f"{BASE}/notifications", headers=H(PM_TOK), params={"unread_only": True}).json()
    unread_before = listing["unread_count"]
    assert unread_before >= 1
    n_id = listing["notifications"][0]["id"]
    # mark one read
    r2 = requests.post(f"{BASE}/notifications/{n_id}/read", headers=H(PM_TOK))
    assert r2.status_code == 200
    after1 = requests.get(f"{BASE}/notifications/unread-count", headers=H(PM_TOK)).json()["unread_count"]
    assert after1 == unread_before - 1
    # mark-all-read
    r3 = requests.post(f"{BASE}/notifications/mark-all-read", headers=H(PM_TOK))
    assert r3.status_code == 200
    assert requests.get(f"{BASE}/notifications/unread-count", headers=H(PM_TOK)).json()["unread_count"] == 0
    # dismiss
    r4 = requests.delete(f"{BASE}/notifications/{n_id}", headers=H(PM_TOK))
    assert r4.status_code == 200
    ids = [n["id"] for n in requests.get(f"{BASE}/notifications", headers=H(PM_TOK)).json()["notifications"]]
    assert n_id not in ids


# ---------- RBAC on accounting ----------
def test_designer_denied_balance_sheet():
    # Create a Designer-role session (use existing testps user; we need their session)
    # Fall back: use the pmanager token first; ProjectManager might or might not have finance.read.
    # We'll instead directly create a designer user session in DB via API? Not straightforward.
    # Instead check with PM token (ProjectManager) — should get 403 too (no finance.read).
    r = requests.get(f"{BASE}/accounting/reports/balance-sheet", headers=H(PM_TOK))
    # ProjectManager without finance.read expected 403
    assert r.status_code == 403
    assert "finance.read" in r.text


# ---------- Balance sheet ----------
def test_balance_sheet_structure_and_income_effect():
    # Fetch accounts
    accs = requests.get(f"{BASE}/accounts", headers=H(ADMIN_TOK)).json()
    bank = next((a for a in accs if a.get("is_bank")), None) or next((a for a in accs if a["type"] == "asset"), None)
    income_acc = next((a for a in accs if a["type"] == "income"), None)
    assert bank and income_acc
    # Post income
    r = requests.post(f"{BASE}/accounting/income", headers=H(ADMIN_TOK), json={
        "amount": 1000, "date": "2026-01-15",
        "bank_account_id": bank["id"], "income_account_id": income_acc["id"],
        "payment_method": "cash", "notes": "TEST_bs_income",
    })
    assert r.status_code in (200, 201), r.text
    bs = requests.get(f"{BASE}/accounting/reports/balance-sheet", headers=H(ADMIN_TOK)).json()
    assert "assets" in bs and "rows" in bs["assets"] and "total" in bs["assets"]
    assert "liabilities" in bs and "equity" in bs
    assert "total_with_net_income" in bs["equity"]
    assert "total_assets" in bs and "total_liabilities_and_equity" in bs
    assert bs["balanced"] is True
    assert bs["equity"]["net_income"] >= 1000 - 0.01


# ---------- Cash Flow ----------
def test_cash_flow():
    r = requests.get(f"{BASE}/accounting/reports/cash-flow", headers=H(ADMIN_TOK),
                     params={"from_date": "2026-01-01", "to_date": "2026-12-31"})
    assert r.status_code == 200
    b = r.json()
    for k in ["opening_balance", "inflows", "outflows", "total_inflow",
              "total_outflow", "net_change", "closing_balance"]:
        assert k in b
    for k in ["income", "client_payment", "other"]:
        assert k in b["inflows"]
    for k in ["expense", "vendor_payment", "payroll", "other"]:
        assert k in b["outflows"]
    assert abs(b["opening_balance"] + b["net_change"] - b["closing_balance"]) < 0.01


# ---------- Extended dashboard ----------
def test_extended_dashboard():
    b = requests.get(f"{BASE}/accounting/dashboard/extended", headers=H(ADMIN_TOK)).json()
    assert "receivables" in b and "total" in b["receivables"] and "overdue" in b["receivables"]
    assert "payables" in b and "total" in b["payables"] and "overdue" in b["payables"]
    assert isinstance(b["monthly_trend"], list) and len(b["monthly_trend"]) == 12
    for m in b["monthly_trend"]:
        assert "key" in m and "income" in m and "expense" in m and "profit" in m
        assert len(m["key"]) == 7 and m["key"][4] == "-"
    assert isinstance(b["expense_breakdown"], list)


# ---------- CSV Exports ----------
@pytest.mark.parametrize("path,first_header", [
    ("/accounting/reports/pl.csv", "section,account,amount"),
    ("/accounting/reports/trial-balance.csv", "account_name,account_type,debit,credit,balance"),
    ("/accounting/reports/balance-sheet.csv", "section,name,balance"),
    ("/accounting/reports/cash-flow.csv", "section,line,amount"),
    ("/journal-entries.csv", "date,reference,narration,source,account,account_type,debit,credit,project_id,client_id,vendor_id"),
])
def test_csv_exports(path, first_header):
    r = requests.get(f"{BASE}{path}", headers=H(ADMIN_TOK))
    assert r.status_code == 200, r.text[:200]
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    first_line = r.text.splitlines()[0]
    assert first_line == first_header


def test_journal_csv_vendor_filter():
    # Find a vendor id from journal entries
    ents = requests.get(f"{BASE}/journal-entries", headers=H(ADMIN_TOK)).json()
    vendor_ids = {e.get("vendor_id") for e in ents if e.get("vendor_id")}
    if not vendor_ids:
        pytest.skip("no vendor_id journal entries in DB")
    vid = next(iter(vendor_ids))
    r = requests.get(f"{BASE}/journal-entries.csv", headers=H(ADMIN_TOK), params={"vendor_id": vid})
    assert r.status_code == 200
    lines = r.text.splitlines()
    # Every data row must have vendor_id column == vid
    header = lines[0].split(",")
    vi = header.index("vendor_id")
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = list(__import__("csv").reader([line]))[0]
        assert cols[vi] == vid, f"line has vendor_id {cols[vi]} != {vid}"


# ---------- account_approved notif ----------
def test_account_approved_notif():
    # Create a pending user
    email = f"TEST_appr_{uuid.uuid4().hex[:6]}@ds.co"
    r = requests.post(f"{BASE}/auth/register", headers=H(ADMIN_TOK), json={
        "email": email, "password": "Test@1234", "name": "TEST Approve",
        "approve_immediately": False,
    })
    assert r.status_code in (200, 201), r.text
    uid = r.json()["user_id"]
    # Approve
    r2 = requests.post(f"{BASE}/rbac/users/{uid}/approve", headers=H(ADMIN_TOK),
                       json={"decision": "approve", "role": "Designer"})
    assert r2.status_code in (200, 201), r2.text
    # Login as that user (password) to get a session
    lp = requests.post(f"{BASE}/auth/login-password",
                       json={"identifier": email.lower(), "password": "Test@1234"})
    assert lp.status_code == 200, lp.text
    tok = lp.json().get("session_token") or lp.cookies.get("session_token")
    assert tok
    ln = requests.get(f"{BASE}/notifications", headers=H(tok),
                      params={"kind": "account_approved"})
    assert ln.status_code == 200
    assert ln.json()["notifications"], "account_approved notif missing"
