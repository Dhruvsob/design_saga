"""Role x action x resource probe (FINAL_SECURITY_REPORT.md section 2).

Fresh local workspace; one user per built-in role (default permissions, no
tenant overrides). Each user tries reads, exports and writes across finance,
payroll, HR, projects and administration. The expected answer comes from the
role table in core/rbac.py (ROLE_PERMISSIONS), not from the routes under test.
Then: a role change and a deactivation must take effect on the user's
existing session. Refuses non-local targets (via accounting_acceptance).
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from accounting_acceptance import PASSWORD, RESULTS, check, login, new_workspace, ok  # noqa: E402
from core.rbac import ROLE_PERMISSIONS  # noqa: E402  (plain module, no DB)

ROLES = ["Director", "ProjectManager", "Designer", "Accountant", "HR", "Employee"]


def allowed(role: str, perm: str) -> bool:
    grants = ROLE_PERMISSIONS.get(role, [])
    if "*.*" in grants or perm in grants:
        return True
    return f"{perm.split('.')[0]}.*" in grants


def main() -> None:
    admin = new_workspace()
    acc = {a["name"]: a for a in ok(admin.get("/api/accounts"))}
    bank = acc["Bank - Primary"]["id"]
    client = ok(admin.post("/api/clients", json={"name": "Probe Client"}))
    project = ok(admin.post("/api/projects", json={"name": "Probe Project", "client_id": client["id"],
                                                   "project_type": "Residential", "engagement_type": "consultancy"}))
    inv = ok(admin.post("/api/invoices", json={"client_id": client["id"], "doc_type": "invoice", "status": "draft",
                                               "tax_rate": 0, "items": [{"description": "Fee", "quantity": 1, "rate": 1000}]}))
    other = ok(admin.post("/api/employees", json={"first_name": "Salaried", "last_name": "Person",
                                                  "email": f"salaried-{uuid.uuid4().hex[:5]}@qa.example.com",
                                                  "monthly_salary": 90000}))
    other_id = other.get("id") or other.get("employee", {}).get("id")

    users = {}
    stamp = uuid.uuid4().hex[:6]
    for role in ROLES:
        email = f"probe-{role.lower()}-{stamp}@qa.example.com"
        u = ok(admin.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": f"Probe {role}",
                                                      "role": role, "approve_immediately": True}))
        users[role] = {"email": email, "user_id": u.get("user_id") or u.get("user", {}).get("user_id"),
                       "client": login(email)}

    get = lambda path: ("GET", path, None)  # noqa: E731
    matrix = [
        ("clients list", get("/api/clients"), "clients.read"),
        ("leads list", get("/api/leads"), "leads.read"),
        ("invoices list", get("/api/invoices"), "invoices.read"),
        ("invoice PDF", get(f"/api/invoices/{inv['id']}/pdf"), "invoices.read"),
        ("quotations list", get("/api/quotations-adv"), "quotations.read"),
        ("journal entries", get("/api/journal-entries"), "finance.read"),
        ("profit and loss", get("/api/accounting/reports/pl"), "finance.read"),
        ("balance sheet", get("/api/accounting/reports/balance-sheet"), "finance.read"),
        ("bank ledger CSV export", get(f"/api/accounting/ledger/account/{bank}/csv"), "finance.read"),
        ("client statement PDF", get(f"/api/clients/{client['id']}/statement.pdf"), "finance.read"),
        ("loans", get("/api/loans"), "loans.read"),
        ("payroll runs", get("/api/payroll/runs"), "payroll.read"),
        ("another person's salary history", get(f"/api/employees/{other_id}/salary/history"), "payroll.read"),
        ("another person's salary preview", get(f"/api/employees/{other_id}/salary/preview?year=2026&month=10"), "payroll.read"),
        ("another person's payslip PDF", get(f"/api/payroll/payslip.pdf?employee_id={other_id}&year=2026&month=10"), "payroll.read"),
        ("employees list", get("/api/employees"), "employees.read"),
        ("timesheet approvals", get("/api/timesheets/approvals"), "attendance.approve"),
        ("vendors list", get("/api/vendors"), "vendors.read"),
        ("purchase orders", get("/api/purchase-orders"), "purchase_orders.read"),
        ("audit log", get("/api/audit"), "*.*"),
        ("post a journal entry", ("POST", "/api/journal-entries", {
            "date": "2026-10-01", "narration": "probe",
            "lines": [{"account_id": bank, "debit": 1, "credit": 0},
                      {"account_id": acc["Owner Capital"]["id"], "debit": 0, "credit": 1}]}), "finance.create"),
        ("add capital (non-operating)", ("POST", "/api/accounting/non-operating", {
            "kind": "owner_investment", "date": "2026-10-01", "amount": 1, "bank_account_id": bank}), "finance.create"),
        ("create a client", ("POST", "/api/clients", {"name": f"Probe made {uuid.uuid4().hex[:4]}"}), "clients.create"),
        ("create an employee", ("POST", "/api/employees", {"first_name": "Probe", "email": f"pe-{uuid.uuid4().hex[:5]}@qa.example.com"}), "employees.create"),
        ("change someone's role", ("PATCH", f"/api/rbac/users/{users['Employee']['user_id']}/role", {"role": "Employee"}), "rbac.manage"),
    ]

    for label, (method, path, body), perm in matrix:
        for role in ROLES:
            c = users[role]["client"]
            res = c.request(method, path, json=body) if body is not None else c.request(method, path)
            got = res.status_code < 300
            exp = allowed(role, perm)
            if res.status_code >= 500:
                got = f"HTTP {res.status_code}"
            check("roles", f"{role:<14} {label} ({perm})", "allow" if exp else "deny",
                  "allow" if got is True else ("deny" if got is False else got))

    # A role change applies to the next request of an existing session.
    acct = users["Accountant"]
    ok(admin.patch(f"/api/rbac/users/{acct['user_id']}/role", json={"role": "Employee"}))
    res = acct["client"].get("/api/journal-entries")
    check("lifecycle", "Accountant demoted to Employee: journals refused on the same session", "deny",
          "deny" if res.status_code in (401, 403) else f"allow ({res.status_code})")

    # Offboarding: deactivating the login ends the existing session.
    emp = users["Employee"]
    linked = ok(admin.post("/api/employees", json={"first_name": "Probe", "last_name": "Leaver", "email": emp["email"],
                                                   "user_id": emp["user_id"]}))
    eid = linked.get("id") or linked.get("employee", {}).get("id")
    res = admin.post(f"/api/employees/{eid}/account/status", json={"active": False})
    check("lifecycle", "admin can deactivate the leaver's login", True, res.status_code < 300)
    me = emp["client"].get("/api/projects")
    check("lifecycle", "deactivated login refused on its existing session", "deny",
          "deny" if me.status_code in (401, 403) else f"allow ({me.status_code})")

    failed = [r for r in RESULTS if r["pass"] is False]
    print(f"\n{len(RESULTS)} checks, {len(failed)} failed")
    for r in failed:
        print("MISMATCH", r["check"], "expected", r["expected"], "observed", r["observed"])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
