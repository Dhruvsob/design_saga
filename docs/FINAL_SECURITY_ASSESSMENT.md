# GAMAA ERP: Final security assessment (2026-11-15)

Scope: authorized, non-destructive. All attack-style testing ran against a
**local** two-tenant stack (`127.0.0.1`, disposable QA database). Production
received only read-only health checks and read-only data-integrity queries.
No credentials, tokens or customer data appear in this document.

This is not a claim that the application cannot be attacked. It records what
was tested, what was found and fixed, and what remains.

## 1. Threat model (short)

| Asset | Threat | Main control |
|---|---|---|
| Tenant data (clients, projects, finance, HR) | Another tenant reading or changing it by ID or by body reference | Tenant-scoped DB wrapper (`core/scoped_db.sdb`), `get_visible_*` guards, `core/refs.ensure_in_tenant` |
| Finance and payroll | Employee or unauthorised role reading or posting | Permission checks on every write route (CI gate), finance/payroll permissions, period locks, balanced-journal guard |
| Accounts | Credential stuffing, session theft, PIN bypass | bcrypt, login/PIN rate limits, server-side PIN lock (423 on every API), hashed session tokens, secure cookies |
| Client portal | Link guessing, approving as someone else | 256-bit tokens, personal links stored as SHA-256 only, decisions only from personal links, rate limits |
| Platform | Tenant staff acting as GAMAA staff | Platform routes require super-admin; tenant admins cannot manage platform accounts |
| Availability | Resource exhaustion on a 1-vCPU shared VPS | Rate limits, bounded list reads, single worker, monitor |

## 2. Attack surface

482 API operations from the live OpenAPI schema: 205 GET, 170 POST, 43 PATCH,
15 PUT, 49 DELETE. Public (unauthenticated) routes are an explicit, reviewed
allow-list enforced by CI: login/session, public branding, contact form,
one-time invite links, and the client portal (token is the credential).

## 3. Tests run and results

### 3.1 Cross-tenant object access (BOLA), automated
Tool: `backend/scripts/cross_tenant_probe.py` (refuses any non-localhost
target). Tenant A and tenant B, both tenant **Admins** (maximum in-tenant
privilege). For every route with an ID in its path, tenant A's real IDs were
used:

| Check | Cases | Result |
|---|---|---|
| GET as tenant A (positive control) | 63 | 48 succeeded (rest need data the fixture lacked) |
| GET as tenant B | 63 | **0 disclosures.** 7 answered 2xx with empty lists or an echo of the requested ID, never tenant-A data |
| Writes (POST/PUT/PATCH/DELETE) as tenant B with schema-valid bodies, record hash compared before/after | 144 | **0 tenant-A records changed** |
| `org_id` injected in create bodies | 2 | stored under the caller's own tenant (forced by `sdb.insert_one`) |
| Body references to tenant-A records (client, project, vendor, account, employee, ...) | 62 | **0 accepted after the fix** (see 4.1) |

Routes whose parameters had no fixture data (68 parameter combinations) were
not exercised by this probe; they are covered by the CI route gates and
existing unit tests only.

### 3.2 Role-based access, automated
A fresh Employee-role login in the second tenant:
* 119 parameter-free GET routes: 68 refused (403); of the 45 that answered,
  the sensitive-looking ones were reviewed: commission dropdown options,
  the expense-approval policy, the employee's own expenses and their own
  expense summary. No payroll, salary, accounting, audit, RBAC or platform
  data was returned.
* Escalation attempts (edit role permissions, change own role through
  employee/account endpoints, post payroll, post journals): all refused;
  role and permission count unchanged afterwards.

### 3.3 Static and dependency scans
| Tool | Target | Result |
|---|---|---|
| bandit 1.9.4 (`-ll`, tests excluded) | backend source | 0 medium/high findings |
| pip-audit | `backend/requirements.production.txt` | No known vulnerabilities |
| npm audit `--omit=dev` | frontend production dependencies | 0 vulnerabilities |

Not run: Semgrep, Trivy (container images), Gitleaks, OWASP ZAP. They are not
installed in this environment and were not installed on production. CI
already runs a tracked-credentials scan (`.github/scripts/scan-secrets.sh`),
pip-audit and bandit on `main`.

### 3.4 Existing controls re-verified by the test suite (639 tests)
Authentication and PIN (server-side lock, rate limits, reset links),
route authentication and permission gates, tenant registry completeness,
public share/portal safety (tenant-bound queries, suspended tenants refused,
token formats), audit-chain integrity, formula-safe CSV export, URL safety
(no `javascript:`/`data:` links), notification tenant ownership.

## 4. Findings

### 4.1 Foreign references accepted in request bodies: FIXED (P1, integrity)
* **What:** `POST /projects` (client_id), `POST/PUT /quotations-adv`
  (client_id, project_id), `POST/PUT /tasks` and bulk update (assignee_id,
  assignees, vendor_id), `POST /attendance/locations` (project_id),
  `POST/PATCH /recurring-expenses` (expense and paid-from accounts, vendor,
  project, client) stored IDs belonging to another workspace, or to nothing.
* **Impact:** no data disclosure (all reads are tenant-scoped), but dangling
  cross-tenant references in records and journal tags; a recurring expense
  could name a non-existent account and fail at every scheduled run.
* **Fix:** `core/refs.ensure_in_tenant()` resolves every body reference
  through the tenant-scoped DB and answers 400 "<X> not found in this
  workspace". Updates check only changed references. Tests:
  `test_refs.py`. Deployed in `46eb9c2`; probe re-run: 0 accepted.

### 4.2 Account deactivation not audited: FIXED (P2)
`DELETE /accounts/{id}` returned `{"ok": true}` for unknown IDs and wrote no
audit row. Now 404 for unknown IDs and `account.deactivate` is audited once.
Test: `test_account_deactivation.py`.

### 4.3 Accepted as designed (informational)
* `DELETE /notifications/{id}` is idempotent and owner-filtered: it answers
  `ok` even when nothing matched. No cross-user effect.
* A few read endpoints answer 200 with an empty result for IDs outside the
  workspace (bank-reconciliation rows/batches, activity, collection entries).
  No data is returned; a 404 would be more consistent (backlog).

## 5. Remaining security risks

| Risk | Severity | Owner action / plan |
|---|---|---|
| Previously exposed credentials (SEC-01: MongoDB Atlas password, viewer token) not yet rotated | High (external) | Rotate in the Atlas console; confirm production does not use them |
| No external alert delivery (monitor runs, but alerts stay on the VPS) | Medium | Provide a working alert channel (see backlog) |
| Uploaded files are type/size checked but not malware-scanned | Medium | ClamAV sidecar or object-storage scanning (backlog) |
| Container image scanning not automated | Medium | Add Trivy to CI |
| Git history still contains removed historical secrets | Medium | History rewrite is an owner decision; rotation (above) removes the risk |
| Single shared VPS (blast radius with Tanvika) | Medium | Upsize or separate hosts |
