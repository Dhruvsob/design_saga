"""Deep cross-module flow audit — the connections the user cares about:
1. Invoice paid -> does accounting JE get created? (source of truth)
2. Task create -> notification + calendar feed?
3. Lead convert -> project?
4. Vendor bill payment -> JE?
5. Payroll <- attendance linkage
6. Milestone paid -> JE?
7. Validation dashboard raw output
8. seed_demo org_id stamping check (direct db)
"""
import requests, json
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8001/api"
PW = "Studio@2026Pass"


def login(identifier, password=PW):
    r = requests.post(f"{BASE}/auth/login-password", json={"identifier": identifier, "password": password})
    r.raise_for_status()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['session_token']}"
    return s


def days(n):
    return (datetime.now(timezone.utc) + timedelta(days=n)).date().isoformat()


adm = login("admin@ateliervista.com")
admB = login("admin@buildcraft.com")

print("=== 1. INVOICE PAID -> JE? ===")
je_before = adm.get(f"{BASE}/journal-entries").json()
n_before = len(je_before if isinstance(je_before, list) else je_before.get("entries", []))
clients = adm.get(f"{BASE}/clients").json()
projects = adm.get(f"{BASE}/projects").json()
inv = adm.post(f"{BASE}/invoices", json={
    "client_id": clients[0]["id"], "client_name": clients[0]["name"],
    "project_id": projects[0]["id"],
    "items": [{"description": "Flow-test invoice", "quantity": 1, "rate": 100000, "amount": 100000}],
    "tax_rate": 18, "due_date": days(10), "status": "sent", "doc_type": "invoice"}).json()
r = adm.patch(f"{BASE}/invoices/{inv['id']}/status", json={"status": "paid"})
print(f"  mark paid: {r.status_code}")
je_after = adm.get(f"{BASE}/journal-entries").json()
n_after = len(je_after if isinstance(je_after, list) else je_after.get("entries", []))
print(f"  JEs before={n_before} after={n_after} -> {'JE CREATED' if n_after > n_before else 'NO JE — invoice payment NOT in accounting!'}")

print("\n=== 2. TASK -> NOTIFICATION + CALENDAR ===")
users = adm.get(f"{BASE}/rbac/users").json()
ulist = users if isinstance(users, list) else users.get("users", [])
emp = next((u for u in ulist if u.get("role") == "Employee"), None)
t = adm.post(f"{BASE}/tasks", json={
    "title": "Flow-test task w/ due date", "project_id": projects[0]["id"],
    "assignee_id": emp["user_id"] if emp else None, "assignee_name": emp.get("name") if emp else None,
    "priority": "high", "due_date": days(2), "reminder_date": days(1)}).json()
print(f"  task created: {t.get('id')}")
emp_sess = login("emp@ateliervista.com")
notifs = emp_sess.get(f"{BASE}/notifications").json()
nlist = notifs if isinstance(notifs, list) else notifs.get("notifications", [])
task_notifs = [n for n in nlist if "task" in json.dumps(n).lower()]
print(f"  employee notifications total={len(nlist)}, task-related={len(task_notifs)}")
if task_notifs:
    print(f"    sample: {json.dumps(task_notifs[0])[:200]}")
feed = adm.get(f"{BASE}/calendar/feed", params={"start": days(-30), "end": days(30)})
print(f"  calendar feed: {feed.status_code}")
if feed.status_code == 200:
    events = feed.json()
    elist = events if isinstance(events, list) else events.get("events", [])
    kinds = {}
    for e in elist:
        k = e.get("kind") or e.get("type") or "?"
        kinds[k] = kinds.get(k, 0) + 1
    print(f"  feed events by kind: {kinds}")

print("\n=== 3. LEAD CONVERT -> PROJECT ===")
leads = adm.get(f"{BASE}/leads").json()
if leads:
    lid = leads[0]["id"]
    r = adm.post(f"{BASE}/leads/{lid}/convert")
    print(f"  convert: {r.status_code} {r.text[:200]}")

print("\n=== 4. VENDOR BILL PAYMENT -> JE (turnkey org) ===")
bills = admB.get(f"{BASE}/vendor-bills").json()
blist = bills if isinstance(bills, list) else bills.get("bills", [])
print(f"  bills: {len(blist)}")
if blist:
    accounts = admB.get(f"{BASE}/accounts").json()
    bank = next((a for a in accounts if a.get("type") == "asset" and "bank" in a["name"].lower()), None)
    b = blist[0]
    jeB_before = len(admB.get(f"{BASE}/journal-entries").json())
    r = admB.post(f"{BASE}/vendor-payments", json={
        "vendor_id": b["vendor_id"], "amount": b.get("total", 50000) / 2,
        "payment_date": days(0), "paid_from_account_id": bank["id"],
        "payment_method": "bank_transfer", "bill_ids": [b["id"]]})
    print(f"  payment: {r.status_code} {r.text[:150]}")
    jeB_after = len(admB.get(f"{BASE}/journal-entries").json())
    print(f"  JEs before={jeB_before} after={jeB_after} -> {'JE created' if jeB_after > jeB_before else 'NO JE!'}")

print("\n=== 5. PAYROLL PREVIEW (attendance linkage) ===")
now = datetime.now()
r = adm.get(f"{BASE}/payroll/preview", params={"year": now.year, "month": now.month})
print(f"  payroll preview: {r.status_code}")
if r.status_code == 200:
    pr = r.json()
    print(f"  keys: {list(pr)[:8] if isinstance(pr, dict) else 'list of ' + str(len(pr))}")
    print(f"  {json.dumps(pr)[:400]}")

print("\n=== 6. MILESTONE -> mark paid -> JE? ===")
ms = adm.get(f"{BASE}/projects/{projects[0]['id']}/milestones").json()
mlist = ms if isinstance(ms, list) else ms.get("milestones", [])
print(f"  milestones: {len(mlist)}")
if mlist:
    m = mlist[0]
    jeb = len(adm.get(f"{BASE}/journal-entries").json())
    r = adm.patch(f"{BASE}/milestones/{m['id']}", json={"status": "paid"})
    print(f"  mark paid: {r.status_code} {r.text[:150]}")
    jea = len(adm.get(f"{BASE}/journal-entries").json())
    print(f"  JE before={jeb} after={jea} -> {'JE created' if jea > jeb else 'NO JE — milestone payments bypass accounting!'}")

print("\n=== 7. VALIDATION DASHBOARD RAW ===")
r = adm.get(f"{BASE}/accounting/dashboard/validation")
print(f"  {r.status_code}: {r.text[:600]}")

print("\n=== 8. ACCOUNTING DASHBOARD KPIs vs reality ===")
r = adm.get(f"{BASE}/accounting/dashboard")
print(f"  {json.dumps(r.json())[:500]}")

print("\n=== 9. NOTIFICATION SCAN (emitters) ===")
r = adm.post(f"{BASE}/notifications/scan")
print(f"  scan: {r.status_code} {r.text[:300]}")
