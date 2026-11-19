"""Cross-tenant and foreign-reference probe for a LOCAL or disposable QA stack.

Never point this at production: it sends write requests with another tenant's IDs.
It refuses to run unless PROBE_BASE is a localhost URL.

What it checks (two tenants, both callers are tenant Admins):
  1. Every API operation with an ID in its path, using tenant A's real IDs:
     GET  - tenant A (control) should succeed; tenant B must get 4xx and no A data.
     write- tenant B sends a schema-valid minimal body; tenant A's record must be
            byte-for-byte unchanged afterwards (hash compare).
  2. Every create/update body field that references another record
     (client_id, project_id, account IDs, ...) set to tenant A's ID by tenant B
     must be refused (core.refs.ensure_in_tenant).

Environment:
  PROBE_BASE=http://127.0.0.1:8001   PROBE_MONGO=mongodb://127.0.0.1:27017   PROBE_DB=design_saga_qa_local
  PROBE_ORG_A, PROBE_ORG_B           tenant org_ids
  PROBE_A_LOGIN, PROBE_A_PASSWORD     tenant A admin; PROBE_B_LOGIN, PROBE_B_PASSWORD, PROBE_B_WORKSPACE
  PROBE_PIN                           App PIN used for both sessions (set up if missing)
Exit code 1 when any leak, foreign write or accepted foreign reference is found.
"""
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests
from pymongo import MongoClient

BASE = os.environ.get("PROBE_BASE", "http://127.0.0.1:8001")
if urlparse(BASE).hostname not in ("127.0.0.1", "localhost"):
    sys.exit("Refusing to probe a non-local server. This tool writes data.")
ORG_A, ORG_B = os.environ["PROBE_ORG_A"], os.environ["PROBE_ORG_B"]
PIN = os.environ["PROBE_PIN"]
db = MongoClient(os.environ.get("PROBE_MONGO", "mongodb://127.0.0.1:27017"))[os.environ.get("PROBE_DB", "design_saga_qa_local")]
openapi = requests.get(f"{BASE}/openapi.json", timeout=30).json()

PARAM_COLL = {
    "project_id": "projects", "eid": "employees", "employee_id": "employees", "vendor_id": "vendors_acc",
    "invoice_id": "invoices", "qid": "quotations_adv", "lead_id": "leads", "task_id": "tasks", "user_id": "users",
    "client_id": "clients", "je_id": "journal_entries", "transmittal_id": "transmittals", "po_id": "purchase_orders",
    "visit_id": "site_visits", "doc_id": "documents", "acc_id": "accounts", "account_id": "accounts",
    "loan_id": "loans", "exp_id": "expenses", "snag_id": "snags", "row_id": "bank_statement_rows",
    "drawing_id": "drawings", "file_id": "files", "run_id": "payroll_runs", "bill_id": "vendor_bills",
    "approval_id": "approvals", "receipt_id": "collection_receipts", "reminder_id": "payment_reminders",
    "ms_id": "payment_milestones", "pmt_id": "vendor_payments", "commission_id": "vendor_commissions",
    "settlement_id": "commission_settlements", "ntf_id": "notifications", "contact_id": "portal_access",
    "holiday_id": "holidays", "event_id": "calendar_events", "batch_id": "bank_statement_batches",
    "leave_id": "leaves", "att_id": "attendance", "corr_id": "attendance_corrections", "adv_id": "employee_advances",
    "grn_id": "goods_receipts", "comment_id": "comments", "phase_id": "project_phases",
    "receivable_id": "collection_receivables", "loc_id": "office_locations", "rec_id": "collection_receivables",
    "record_id": "attendance", "source_id": "invoices", "target_id": "projects", "item_id": "master_data",
    "session_id": "ai_messages", "product_id": "products",
}
FIXED = {"rev": "A", "index": "0", "kind": "invoice", "source_type": "invoice", "target_type": "project",
         "date_str": "2026-11-10", "role": "Employee", "name": "probe", "key": "probe"}
SKIP = re.compile(r"logout|/pin/|/auth/(login|session|password|register|invite|reset|google)|/portal/|"
                  r"/org/logo/|/org/public/|/files/\{full_path|/platform/")
BODY_REFS = {"project_id": "projects", "client_id": "clients", "vendor_id": "vendors_acc", "employee_id": "employees",
             "lead_id": "leads", "task_id": "tasks", "invoice_id": "invoices", "account_id": "accounts",
             "salary_account_id": "accounts", "paid_from_account_id": "accounts", "expense_account_id": "accounts",
             "drawing_id": "drawings", "file_id": "files", "po_id": "purchase_orders", "assignee_id": "employees",
             "project_manager_id": "employees", "bill_id": "vendor_bills", "default_vendor_id": "vendors_acc"}


def foreign(coll):
    d = db[coll].find_one({"org_id": ORG_A, "id": {"$exists": True}}, sort=[("_id", -1)]) or \
        db[coll].find_one({"org_id": {"$nin": [ORG_B, None, ""]}, "id": {"$exists": True}}, sort=[("_id", -1)])
    if not d and coll == "users":
        d = db.users.find_one({"org_id": ORG_A})
        if d:
            d["id"] = d.get("user_id")
    return d


def fingerprint(coll, rid):
    d = db[coll].find_one({("user_id" if coll == "users" else "id"): rid}, {"_id": 0})
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest() if d else "MISSING"


def deref(s):
    while isinstance(s, dict) and "$ref" in s:
        s = openapi["components"]["schemas"][s["$ref"].split("/")[-1]]
    return s


def example(s, field="", depth=0):
    s = deref(s or {})
    if depth > 4:
        return None
    for k in ("anyOf", "oneOf", "allOf"):
        if k in s:
            opts = [o for o in s[k] if deref(o).get("type") != "null"] or s[k]
            return example(opts[0], field, depth + 1)
    if "enum" in s:
        return s["enum"][0]
    t = s.get("type")
    if t == "object" or "properties" in s:
        return {k: example(v, k, depth + 1) for k, v in s.get("properties", {}).items() if k in s.get("required", [])}
    if t == "array":
        return [example(s.get("items", {}), field, depth + 1)] if s.get("minItems") else []
    if t in ("integer", "number"):
        return 1
    if t == "boolean":
        return False
    if field.endswith("_date") or field == "date":
        return "2026-11-20"
    if "email" in field:
        return "probe@example.com"
    if field == "engagement_type":
        return "consultancy"
    return "probe-value"


def body_schema(path, method):
    op = openapi["paths"].get(path, {}).get(method.lower(), {})
    return deref(((op.get("requestBody") or {}).get("content", {}).get("application/json") or {}).get("schema", {}))


def session(login, password, workspace=None):
    s = requests.Session()
    body = {"identifier": login, "password": password}
    if workspace:
        body["workspace"] = workspace
    r = s.post(f"{BASE}/api/auth/login-password", json=body, timeout=30)
    r.raise_for_status()
    s.headers["Authorization"] = "Bearer " + r.json()["session_token"]
    if s.get(f"{BASE}/api/auth/pin/status", timeout=30).json().get("setup_required"):
        s.post(f"{BASE}/api/auth/pin/setup", json={"pin": PIN}, timeout=30)
    s.post(f"{BASE}/api/auth/pin/unlock", json={"pin": PIN}, timeout=30)
    assert s.get(f"{BASE}/api/clients", timeout=30).status_code != 423, "session still PIN-locked"
    return s


def call(s, method, url, body=None):
    for _ in range(3):
        r = s.request(method, url, json=body, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(int(r.headers.get("Retry-After", "5")) + 1)
    if r.status_code == 423:
        sys.exit(f"session got PIN-locked at {method} {url}; results would be vacuous")
    return r


A = session(os.environ["PROBE_A_LOGIN"], os.environ["PROBE_A_PASSWORD"])
B = session(os.environ["PROBE_B_LOGIN"], os.environ["PROBE_B_PASSWORD"], os.environ.get("PROBE_B_WORKSPACE"))
problems, counts = [], {"get": 0, "get_control_ok": 0, "write": 0, "body_refs": 0}
cache = {}
for path, ops in openapi["paths"].items():
    params = re.findall(r"{(\w+)}", path)
    if not path.startswith("/api") or not params or SKIP.search(path):
        continue
    for method in [m.upper() for m in ops]:
        url, ids, ok = path, [], True
        for p in params:
            if p in FIXED:
                url = url.replace("{" + p + "}", FIXED[p])
                continue
            coll = PARAM_COLL.get(p)
            d = cache.setdefault(coll, foreign(coll)) if coll else None
            if not d:
                ok = False
                break
            ids.append((coll, d["id"], d))
            url = url.replace("{" + p + "}", str(d["id"]))
        if not ok:
            continue
        if method == "GET":
            counts["get"] += 1
            counts["get_control_ok"] += call(A, "GET", BASE + url).status_code < 300
            rb = call(B, "GET", BASE + url)
            ctype = rb.headers.get("content-type", "")
            text = rb.text if ("json" in ctype or "text" in ctype) else ""
            markers = {str(rid) for _, rid, _ in ids} | {v for _, _, d in ids for k in ("name", "title", "email")
                                                        if isinstance(v := d.get(k), str) and len(v) >= 6}
            echoed = {str(rid) for _, rid, _ in ids if f'"source_id":"{rid}"' in text.replace(" ", "")}
            leaked = [m for m in markers - echoed if m in text]
            if rb.status_code < 300 and (leaked or (not text and rb.content)):
                problems.append(f"READ {method} {path} -> {rb.status_code} {leaked[:3]} {ctype}")
        else:
            counts["write"] += 1
            before = {(c, rid): fingerprint(c, rid) for c, rid, _ in ids}
            schema = body_schema(path, method)
            rb = call(B, method, BASE + url, example(schema) if schema else None)
            changed = [f"{c}:{rid}" for (c, rid), h in before.items() if fingerprint(c, rid) != h]
            if changed:
                problems.append(f"WRITE {method} {path} -> {rb.status_code} changed {changed}")

for path, ops in openapi["paths"].items():
    if "{" in path or not path.startswith("/api") or SKIP.search(path):
        continue
    for method in ("post", "put", "patch"):
        schema = body_schema(path, method) if method in ops else None
        props = deref(schema).get("properties", {}) if schema else {}
        for field in [f for f in props if f in BODY_REFS]:
            d = cache.setdefault(BODY_REFS[field], foreign(BODY_REFS[field]))
            if not d:
                continue
            body = example(schema) or {}
            body[field] = d["id"]
            for k in ("name", "title"):
                if k in props and k not in body:
                    body[k] = f"probe {field}"
            counts["body_refs"] += 1
            r = call(B, method.upper(), BASE + path, body)
            if r.status_code < 300:
                problems.append(f"FOREIGN-REF {method.upper()} {path} accepted {field}")

print(json.dumps(counts))
for p in problems:
    print(p)
sys.exit(1 if problems else 0)
