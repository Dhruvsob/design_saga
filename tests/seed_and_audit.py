"""Design Saga ERP — Seed 2 realistic tenants via APIs + full audit.

PART A: Seed (idempotent — checks for existing orgs by slug)
PART B: Tenant isolation audit
PART C: RBAC audit (employee vs admin access)
PART D: GET endpoint sweep (500 detector)
PART E: Accounting integrity (trial balance, balance sheet)
"""
import requests, json, sys, random
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8001/api"
SA = {"identifier": "designsaga10@gmail.com", "password": "SuperAdmin@2026"}
PW = "Studio@2026Pass"

ISSUES = []          # audit findings collected here


def issue(sev, area, msg):
    ISSUES.append((sev, area, msg))
    print(f"  [{sev}] {area}: {msg}")


def login(identifier, password):
    r = requests.post(f"{BASE}/auth/login-password",
                      json={"identifier": identifier, "password": password})
    if r.status_code != 200:
        raise RuntimeError(f"login {identifier} failed: {r.status_code} {r.text[:200]}")
    tok = r.json()["session_token"]
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"
    return s, r.json()["user"]


def jpost(s, path, payload, ok=(200, 201)):
    r = s.post(f"{BASE}{path}", json=payload)
    if r.status_code not in ok:
        print(f"    !! POST {path} -> {r.status_code}: {r.text[:250]}")
        return None
    try:
        return r.json()
    except Exception:
        return {}


def jget(s, path, ok=(200,)):
    r = s.get(f"{BASE}{path}")
    if r.status_code not in ok:
        return None, r
    try:
        return r.json(), r
    except Exception:
        return None, r


def days(n):
    return (datetime.now(timezone.utc) + timedelta(days=n)).date().isoformat()


# ================= PART A: SEED =================
ORGS = [
    dict(slug="atelier-vista", name="Atelier Vista Design Studio", mode="consultancy",
         admin_email="admin@ateliervista.com", admin_name="Meera Sharma"),
    dict(slug="buildcraft-interiors", name="BuildCraft Interiors", mode="turnkey",
         admin_email="admin@buildcraft.com", admin_name="Rohan Verma"),
]


def seed_org(sa_sess, spec):
    print(f"\n--- Seeding org {spec['name']} ({spec['mode']}) ---")
    orgs, _ = jget(sa_sess, "/platform/orgs")
    existing = None
    for o in (orgs or []):
        if o.get("slug") == spec["slug"]:
            existing = o
            break
    if existing:
        print("  org exists, skipping create")
        org_id = existing["org_id"]
    else:
        res = jpost(sa_sess, "/platform/orgs", {
            "name": spec["name"], "slug": spec["slug"],
            "admin_email": spec["admin_email"], "admin_name": spec["admin_name"],
            "admin_password": PW, "business_mode": spec["mode"],
            "phone": "+91 98765 11111", "plan": "pro",
            "gstin": "27AAACB1234C1Z5" if spec["mode"] == "turnkey" else None,
        })
        if not res:
            raise RuntimeError("org create failed")
        org_id = res.get("org_id") or res.get("org", {}).get("org_id")
    print(f"  org_id={org_id}")

    adm, admin_user = login(spec["admin_email"], PW)

    # ---- users / employees ----
    team = [
        ("pm", "Priya Nair" if spec["mode"] == "consultancy" else "Arjun Patel", "ProjectManager"),
        ("emp", "Kabir Das" if spec["mode"] == "consultancy" else "Sneha Rao", "Employee"),
        ("acct", "Anil Kumar" if spec["mode"] == "consultancy" else "Divya Menon", "Accountant"),
    ]
    users = {}
    for key, name, role in team:
        email = f"{key}@{spec['slug'].replace('-', '')}.com"
        res = jpost(adm, "/auth/register", {
            "email": email, "password": PW, "name": name, "role": role,
            "approve_immediately": True}, ok=(200, 201, 409))
        users[key] = {"email": email, "name": name, "role": role,
                      "user_id": (res or {}).get("user_id") or (res or {}).get("user", {}).get("user_id")}
    # employees records
    emps, _ = jget(adm, "/employees")
    if not emps or len(emps if isinstance(emps, list) else emps.get("employees", [])) < 3:
        for key, name, role in team:
            fn, ln = name.split(" ", 1)
            jpost(adm, "/employees", {
                "first_name": fn, "last_name": ln, "email": users[key]["email"],
                "phone": "+91 90000 0000" + str(random.randint(1, 9)),
                "department": "Design" if role != "Accountant" else "Finance",
                "designation": {"ProjectManager": "Senior Project Manager",
                                "Employee": "Interior Designer",
                                "Accountant": "Accounts Manager"}[role],
                "employment_type": "full_time", "joining_date": days(-400),
                "monthly_salary": {"ProjectManager": 85000, "Employee": 45000,
                                   "Accountant": 55000}[role],
                "user_id": users[key]["user_id"],
            })

    # ---- clients ----
    cls, _ = jget(adm, "/clients")
    if not cls:
        cdefs = ([("Aarav Mehta", "Mehta Penthouse", "residential"),
                  ("Zoya Khan", "Khan Villa", "residential"),
                  ("Nexus Cowork", "Nexus Cowork Pvt Ltd", "commercial")]
                 if spec["mode"] == "consultancy" else
                 [("Ritu Malhotra", "Malhotra Residence", "residential"),
                  ("Cafe Terra", "Terra Hospitality LLP", "commercial")])
        cls = []
        for nm, co, ct in cdefs:
            c = jpost(adm, "/clients", {"name": nm, "company": co, "client_type": ct,
                                        "email": nm.split()[0].lower() + "@client.com",
                                        "phone": "+91 98220 1234" + str(random.randint(1, 9)),
                                        "address": "Mumbai"})
            if c:
                cls.append(c)
    print(f"  clients: {len(cls)}")

    # ---- leads ----
    leads, _ = jget(adm, "/leads")
    if not leads:
        for nm, src, stage, bud in [("Karan Johar Residence", "Referral", "New", 2500000),
                                    ("Blue Tokai Cafe", "Instagram", "Qualified", 4000000),
                                    ("Sunder Apartments", "Website", "Proposal", 1500000)]:
            jpost(adm, "/leads", {"name": nm, "source": src, "stage": stage,
                                  "budget": bud, "project_type": "Residential",
                                  "location": "Mumbai",
                                  "email": nm.split()[0].lower() + "@lead.com"})

    # ---- projects ----
    prjs, _ = jget(adm, "/projects")
    if not prjs:
        prjs = []
        pdefs = ([("Mehta Penthouse — Design Consultancy", 0, "Design Dev", 1800000),
                  ("Khan Villa — Full Design Package", 1, "Concept", 2600000),
                  ("Nexus Cowork — Space Planning", 2, "Tech Drawings", 3200000)]
                 if spec["mode"] == "consultancy" else
                 [("Malhotra Residence — Turnkey Fitout", 0, "Execution", 5500000),
                  ("Cafe Terra — Design + Build", 1, "Procurement", 7200000)])
        for nm, ci, stage, bud in pdefs:
            if ci < len(cls):
                p = jpost(adm, "/projects", {
                    "name": nm, "client_id": cls[ci]["id"], "stage": stage,
                    "budget": bud, "project_type": "Residential" if "Residence" in nm or "Villa" in nm or "Penthouse" in nm else "Commercial",
                    "engagement_type": spec["mode"],
                    "start_date": days(-60), "end_date": days(120),
                    "description": f"{nm} — seeded project"})
                if p:
                    prjs.append(p)
    print(f"  projects: {len(prjs)}")

    # ---- tasks ----
    tasks, _ = jget(adm, "/tasks")
    tlist = tasks if isinstance(tasks, list) else (tasks or {}).get("tasks", [])
    if not tlist and prjs:
        tdefs = [("Site measurement & survey", "todo", "high", 2, "pm"),
                 ("Concept moodboard v1", "in_progress", "medium", 4, "emp"),
                 ("Client presentation deck", "todo", "high", 6, "pm"),
                 ("3D renders — living + dining", "in_progress", "high", 8, "emp"),
                 ("BOQ verification", "review", "medium", 3, "acct"),
                 ("Vendor follow-up — lighting", "todo", "low", 5, "emp")]
        for title, st, pri, due, who in tdefs:
            jpost(adm, "/tasks", {
                "title": title, "project_id": prjs[0]["id"], "status": st,
                "priority": pri, "due_date": days(due),
                "assignee_id": users[who]["user_id"],
                "assignee_name": users[who]["name"],
                "reminder_date": days(due - 1)})

    # ---- vendors ----
    vnds, _ = jget(adm, "/vendors")
    vlist = vnds if isinstance(vnds, list) else (vnds or {}).get("vendors", [])
    if not vlist:
        vdefs = ([("Studio Lights Co", "agency", "Lighting"),
                  ("GreenScape Landscapes", "agency", "Landscape")]
                 if spec["mode"] == "consultancy" else
                 [("Sharma Modular Works", "contractor", "Carpentry"),
                  ("Apex Electricals", "supplier", "Electrical"),
                  ("Stone Gallery", "supplier", "Stone & Marble")])
        vlist = []
        for nm, at, cat in vdefs:
            v = jpost(adm, "/vendors", {"name": nm, "agency_type": at, "category": cat,
                                        "contact_person": nm.split()[0],
                                        "phone": "+91 91111 2222" + str(random.randint(1, 9)),
                                        "email": nm.split()[0].lower() + "@vendor.com",
                                        "city": "Mumbai", "tds_applicable": at == "contractor",
                                        "tds_rate": 2 if at == "contractor" else 0})
            if v:
                vlist.append(v)
    print(f"  vendors: {len(vlist)}")

    # ---- accounting: COA + income/expense ----
    jpost(adm, "/accounting/seed-coa", {}, ok=(200, 201, 409))
    accounts, _ = jget(adm, "/accounts")
    acc_by_name = {a["name"]: a for a in (accounts or [])}
    bank = next((a for a in (accounts or []) if a.get("type") == "asset" and "bank" in a["name"].lower()), None)
    inc_acc = next((a for a in (accounts or []) if a.get("type") == "income"), None)
    exp_acc = next((a for a in (accounts or []) if a.get("type") == "expense"), None)

    jes, _ = jget(adm, "/journal-entries")
    je_list = jes if isinstance(jes, list) else (jes or {}).get("entries", [])
    if bank and inc_acc and exp_acc and len(je_list) < 3 and prjs and cls:
        jpost(adm, "/accounting/income", {
            "date": days(-20), "amount": 350000, "client_id": cls[0]["id"],
            "project_id": prjs[0]["id"], "income_account_id": inc_acc["id"],
            "bank_account_id": bank["id"], "payment_method": "bank_transfer",
            "notes": "Design fee — milestone 1"})
        jpost(adm, "/accounting/income", {
            "date": days(-8), "amount": 250000, "client_id": cls[-1]["id"],
            "project_id": prjs[-1]["id"], "income_account_id": inc_acc["id"],
            "bank_account_id": bank["id"], "payment_method": "upi",
            "notes": "Advance received"})
        jpost(adm, "/accounting/expense", {
            "date": days(-15), "amount": 48000, "expense_account_id": exp_acc["id"],
            "paid_from_account_id": bank["id"], "project_id": prjs[0]["id"],
            "vendor_id": vlist[0]["id"] if vlist else None,
            "payment_method": "bank_transfer", "notes": "Site expenses — materials"})

    # ---- invoices + milestones ----
    invs, _ = jget(adm, "/invoices")
    if not invs and prjs and cls:
        for i, (desc, amt, st) in enumerate([("Concept design retainer", 400000, "paid"),
                                             ("Design development — milestone 2", 350000, "sent")]):
            pi = prjs[min(i, len(prjs) - 1)]
            ci = cls[min(i, len(cls) - 1)]
            jpost(adm, "/invoices", {
                "client_id": ci["id"], "client_name": ci["name"],
                "project_id": pi["id"], "project_name": pi["name"],
                "items": [{"description": desc, "quantity": 1, "rate": amt, "amount": amt}],
                "tax_rate": 18, "due_date": days(15), "status": st,
                "doc_type": "invoice", "notes": "Payment due within 15 days."})
        # milestones
        jpost(adm, f"/projects/{prjs[0]['id']}/milestones", {
            "project_id": prjs[0]["id"], "name": "Design sign-off", "percent": 30,
            "amount": prjs[0].get("budget", 0) * 0.3, "due_date": days(20)})

    # ---- quotations ----
    qts, _ = jget(adm, "/quotations-adv")
    qlist = qts if isinstance(qts, list) else (qts or {}).get("quotations", [])
    if not qlist and cls:
        qtype = "consultancy" if spec["mode"] == "consultancy" else "turnkey"
        jpost(adm, "/quotations-adv", {
            "type": qtype, "project_title": f"{cls[0]['name']} — {qtype.title()} Proposal",
            "client_id": cls[0]["id"], "client_name": cls[0]["name"],
            "project_location": "Mumbai", "area_sqft": 2400})

    # ---- attendance policy + location + holidays ----
    jget(adm, "/attendance/policy")
    locs, _ = jget(adm, "/attendance/locations")
    llist = locs if isinstance(locs, list) else (locs or {}).get("locations", [])
    if not llist:
        jpost(adm, "/attendance/locations", {
            "name": "Head Office", "kind": "office",
            "lat": 19.0760, "lng": 72.8777, "radius_m": 150})
    hols, _ = jget(adm, "/holidays")
    hlist = hols if isinstance(hols, list) else (hols or {}).get("holidays", [])
    if not hlist:
        jpost(adm, "/holidays/bulk", {"year": 2026, "holidays": [
            {"date": "2026-10-02", "name": "Gandhi Jayanti", "kind": "national", "recurring": True},
            {"date": "2026-11-09", "name": "Diwali", "kind": "festival"},
            {"date": "2026-12-25", "name": "Christmas", "kind": "national", "recurring": True}]},
            ok=(200, 201, 422))

    # ---- turnkey extras: PO + GRN + vendor bill ----
    if spec["mode"] == "turnkey" and vlist and prjs:
        pos, _ = jget(adm, "/purchase-orders")
        plist = pos if isinstance(pos, list) else (pos or {}).get("purchase_orders", [])
        if not plist:
            po = jpost(adm, "/purchase-orders", {
                "vendor_id": vlist[0]["id"], "project_id": prjs[0]["id"],
                "order_date": days(-10), "expected_delivery": days(5),
                "payment_terms": "50% advance, 50% on delivery",
                "lines": [{"item_name": "Modular kitchen carcass", "quantity": 12,
                           "unit": "rft", "unit_price": 2200, "tax_rate": 18},
                          {"item_name": "Soft-close hardware set", "quantity": 6,
                           "unit": "set", "unit_price": 3500, "tax_rate": 18}]})
            if po:
                jpost(adm, f"/purchase-orders/{po['id']}/send", {})
        bills, _ = jget(adm, "/vendor-bills")
        blist = bills if isinstance(bills, list) else (bills or {}).get("bills", [])
        if not blist:
            jpost(adm, "/vendor-bills", {
                "vendor_id": vlist[1]["id"], "bill_date": days(-5),
                "due_date": days(10), "project_id": prjs[0]["id"],
                "items": [{"description": "Electrical wiring — phase 1",
                           "quantity": 1, "rate": 85000, "amount": 85000}],
                "tax_rate": 18, "status": "approved"})

    return org_id, adm, users, admin_user


# ================ PART B: ISOLATION ================
LIST_ENDPOINTS = [
    "/clients", "/projects", "/tasks", "/leads", "/invoices", "/vendors",
    "/quotations-adv", "/employees", "/journal-entries", "/accounts",
    "/purchase-orders", "/vendor-bills", "/expenses", "/loans", "/holidays",
    "/attendance/locations", "/notifications", "/calendar/events", "/files",
    "/master-data",
]


def extract_ids(payload):
    ids = set()
    def walk(x):
        if isinstance(x, dict):
            if "id" in x and isinstance(x["id"], str):
                ids.add(x["id"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(payload)
    return ids


def audit_isolation(sessA, sessB, nameA, nameB):
    print(f"\n=== PART B: Tenant isolation ({nameA} vs {nameB}) ===")
    for ep in LIST_ENDPOINTS:
        da, ra = jget(sessA, ep)
        db_, rb = jget(sessB, ep)
        if da is None or db_ is None:
            continue
        ids_a, ids_b = extract_ids(da), extract_ids(db_)
        common = ids_a & ids_b
        if common:
            issue("P0", "ISOLATION", f"{ep}: {len(common)} shared record ids between tenants! sample={list(common)[:3]}")
    print("  isolation sweep complete")


# ================ PART C: RBAC ================
def audit_rbac(emp_sess, org_name):
    print(f"\n=== PART C: RBAC — Employee role restrictions ({org_name}) ===")
    forbidden = [
        ("/accounting/dashboard", "finance data"),
        ("/journal-entries", "journal entries"),
        ("/rbac/users", "user admin"),
        ("/platform/orgs", "platform"),
        ("/payroll/runs", "payroll"),
        ("/accounting/reports/pl", "P&L report"),
    ]
    for ep, label in forbidden:
        d, r = jget(emp_sess, ep, ok=(200, 401, 403))
        if r.status_code == 200:
            issue("P0", "RBAC", f"Employee can access {ep} ({label}) — should be 403")
        else:
            print(f"  OK {ep} -> {r.status_code}")


# ================ PART D: GET SWEEP ================
SWEEP = [
    "/dashboard/stats", "/clients", "/projects", "/tasks", "/tasks/meta",
    "/leads", "/invoices", "/vendors", "/vendors/meta", "/quotations-adv",
    "/quotations-adv/templates", "/employees", "/employees/meta",
    "/journal-entries", "/accounts", "/accounting/dashboard",
    "/accounting/dashboard/extended", "/accounting/meta", "/accounting/fy/list",
    "/accounting/reports/pl", "/accounting/reports/trial-balance",
    "/accounting/reports/balance-sheet", "/accounting/reports/cash-flow",
    "/purchase-orders", "/vendor-bills", "/vendor-payments", "/expenses",
    "/expenses/summary/dashboard", "/expense-policy", "/loans",
    "/loans/summary/dashboard", "/holidays", "/attendance/policy",
    "/attendance/locations", "/attendance/records", "/attendance/dashboard",
    "/attendance/me/today", "/attendance/me/summary", "/attendance/monthly",
    "/attendance/live", "/attendance/meta", "/attendance/leave-rules",
    "/notifications", "/notifications/unread-count", "/calendar/events",
    "/calendar/feed?start=2026-08-01&end=2026-09-30", "/files", "/master-data", "/audit-log",
    "/payroll/runs", "/payroll/preview?year=2026&month=8", "/leaves", "/search?q=design",
    "/commissions/dashboard", "/commissions/report", "/rbac/roles",
    "/rbac/users", "/expenses/approvers", "/tasks/reminders/upcoming",
]


def audit_sweep(sess, org_name):
    print(f"\n=== PART D: GET endpoint sweep ({org_name}) ===")
    n500 = 0
    for ep in SWEEP:
        r = sess.get(f"{BASE}{ep}")
        if r.status_code >= 500:
            issue("P0", "500", f"GET {ep} -> {r.status_code}: {r.text[:200]}")
            n500 += 1
        elif r.status_code == 404:
            issue("P2", "404", f"GET {ep} -> 404 (missing endpoint?)")
        elif r.status_code not in (200, 403):
            issue("P1", "HTTP", f"GET {ep} -> {r.status_code}: {r.text[:120]}")
    print(f"  sweep done, {n500} server errors")


# ============== PART E: ACCOUNTING ==============
def audit_accounting(sess, org_name):
    print(f"\n=== PART E: Accounting integrity ({org_name}) ===")
    tb, _ = jget(sess, "/accounting/reports/trial-balance")
    if tb:
        td, tc = tb.get("total_debit"), tb.get("total_credit")
        if td is not None and tc is not None and abs(td - tc) > 0.01:
            issue("P0", "ACCOUNTING", f"Trial balance NOT balanced: DR={td} CR={tc}")
        else:
            print(f"  TB balanced: DR={td} CR={tc}")
    bs, _ = jget(sess, "/accounting/reports/balance-sheet")
    if bs:
        if not bs.get("balanced", True):
            issue("P1", "ACCOUNTING", f"Balance sheet unbalanced, delta={bs.get('delta')}")
        else:
            print(f"  BS balanced (delta={bs.get('delta')})")
    val, r = jget(sess, "/accounting/dashboard/validation", ok=(200, 403))
    if val:
        print(f"  validation: match_within_1pc={val.get('match_within_1pc')} "
              f"delta={val.get('delta')}")
        diags = val.get("diagnostics") or {}
        for k, v in diags.items():
            if isinstance(v, list) and v:
                issue("P1", "ACCOUNTING", f"validation diagnostic {k}: {len(v)} items")


def main():
    print("=== Login as SuperAdmin ===")
    sa, sa_user = login(**SA)
    print(f"  ok — super_admin={sa_user.get('is_super_admin')}")

    org_data = []
    for spec in ORGS:
        oid, adm, users, admin_user = seed_org(sa, spec)
        org_data.append((spec, oid, adm, users))

    (specA, oidA, admA, usersA), (specB, oidB, admB, usersB) = org_data

    audit_isolation(admA, admB, specA["name"], specB["name"])

    empA, _ = login(usersA["emp"]["email"], PW)
    audit_rbac(empA, specA["name"])

    audit_sweep(admA, specA["name"])
    audit_accounting(admA, specA["name"])
    audit_accounting(admB, specB["name"])

    print("\n\n================ AUDIT SUMMARY ================")
    if not ISSUES:
        print("No issues found by automated audit.")
    for sev in ("P0", "P1", "P2"):
        rows = [i for i in ISSUES if i[0] == sev]
        if rows:
            print(f"\n{sev} ({len(rows)}):")
            for _, area, msg in rows:
                print(f"  - [{area}] {msg}")
    with open("/app/tests/audit_findings.json", "w") as f:
        json.dump([{"sev": s, "area": a, "msg": m} for s, a, m in ISSUES], f, indent=1)


if __name__ == "__main__":
    main()
