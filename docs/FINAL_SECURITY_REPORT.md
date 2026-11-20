# GAMAA ERP: security report (releases `74aff6e` and `1cdac8c`, 2026-11-20)

The full assessment (threat model, cross-tenant BOLA probe, Employee-role
tests, scans) is `FINAL_SECURITY_ASSESSMENT.md` (2026-11-15). This report adds
what was checked and changed on 2026-11-20 (releases `504a2c3` and `74aff6e`).
No secrets or customer data appear here.

## 1. Trust boundaries

| Boundary | Control | Evidence |
|---|---|---|
| Internet -> app | Caddy TLS (HSTS 1 year), nginx security headers, app shell `no-cache` | `curl -I https://gamaa.in/` |
| User -> API | session cookie + server-side App PIN lock (423); permission check on every write route; rate limits on login, PIN, registration, exports, portal writes | CI gates in the suite (700 pass); `core/http_security.py` |
| Tenant -> tenant | tenant-scoped DB wrapper, `get_visible_*`, body-reference checks | cross-tenant probe (round 2): 53 reads, 94 writes, 61 body references from another workspace: no leaks, no foreign writes, nothing accepted |
| Role -> role | `has_permission` with Team & Roles overrides | §2 |
| Client portal | 256-bit personal tokens stored hashed; decisions only from personal links; every lookup filtered by the token owner's org | `test_client_approvals.py`, `test_selections_and_quote_acceptance.py` |
| ERP -> Google | per-user OAuth with PKCE and hashed `state`; tokens Fernet-encrypted; one Google account per ERP user (unique index) | `test_google_calendar.py` |

API surface now 504 operations (212 GET, 180 POST, 45 PATCH, 15 PUT, 52 DELETE);
7 new in `74aff6e` and 1 in `1cdac8c` (add an approved variation to the fee
milestones; `projects.update`, visible project only), all authenticated (401
without a session, checked on production).
No new public route: the portal's existing decision and file routes gained two
request kinds (selection, quotation).

## 2. Role x action x resource matrix

`backend/scripts/role_probe.py`: a fresh workspace, one user per built-in role
(Director, ProjectManager, Designer, Accountant, HR, Employee; default
permissions). Each tried 25 reads, exports and writes; the expected answer is
computed from `core/rbac.py ROLE_PERMISSIONS`, not from the routes.

| Resource / action | Permission | Roles allowed (observed = expected) |
|---|---|---|
| Clients and leads lists | clients/leads.read | all six except HR |
| Quotations list | quotations.read | Director, PM, Designer, Accountant |
| Invoices list and invoice PDF | invoices.read | Director, PM, Accountant |
| Journals, P&L, balance sheet, ledger CSV, client statement PDF | finance.read | Director, Accountant |
| Loans | loans.read / finance.read | Director, Accountant |
| Payroll runs; another person's salary history, salary preview, payslip PDF | payroll.read | Director, Accountant, HR |
| Employees list | employees.read | all except Employee (defaults) |
| Timesheet approvals | attendance.approve | Director, PM, HR |
| Vendors, purchase orders | vendors/purchase_orders.read | all except HR |
| Audit log | Admin only | none of the six |
| Post a journal, add capital | finance.create | Director, Accountant |
| Create a client / an employee | clients.create / employees.create | per role table |
| Change someone's role | rbac.manage (Admin) | none of the six |
| **Result** | | **150/150 decisions match** |

Lifecycle (same run): an Accountant demoted to Employee is refused journals on
the **same session** at the next request; a leaver whose login is deactivated
is refused on the existing session (sessions are deleted); 3/3.

Production overrides (read-only): the studio's Designers lack clients.read and
employees.read; ProjectManager and Employee lack employees.read. The server
denies these correctly (403s in the logs); the screens now skip such lookups
(`optionalList`) instead of failing.

Not probed live: client-portal users across every route (covered by the
portal unit tests: token scope, personal-link-only decisions, org filtering),
platform super-admin (covered by route gates). **Status: VERIFIED** for the six
tenant roles and tenant isolation.

## 3. Defensive fixes on 2026-11-20

| Finding | Severity | Fix | Regression evidence |
|---|---|---|---|
| Client quotation PDF exposed the studio's margin percentage and base cost rate | **High** (confidential commercial data in a client document) | Selling rate only; no margin column | `pdf_inspection.py`; before/after render of the same quotation |
| Google outage or rate limit during token refresh paused calendar sync until the user reconnected | Medium (availability) | Only a refused grant pauses; outages retry | `test_google_outage_during_refresh_keeps_the_connection` |
| Paused calendar was silent | Medium | One bell notice per pause | `test_expired_grant_pauses_once...`; 1 notice on production |
| Items deleted/reassigned during a pause kept their Google copy | Medium (privacy) | Reconnect removes stale copies | `test_reconnect_removes_copies...` |
| Restricted roles' pages failed on a lookup 403 | Medium (availability) | `optionalList` | `ux.spec` restricted-role test (desktop and phone) |
| Construction drawing superseded by a review draft | High (site safety / integrity) | Site copy kept until a new construction issue | `test_drawings.py`, `drawings.spec` |
| A client could approve a quotation version the studio had since changed | Prevented by design in the new flow | Edits, versions, status changes and deletes close the pending request; stale decisions refused (409) | `test_quotation_changed_after_sending_cannot_be_accepted` |

## 4. Scans (2026-11-20)

| Tool | Target | Result |
|---|---|---|
| bandit 1.9.4 (`-ll`, tests and scripts excluded) | backend | 0 medium/high |
| pip-audit 2.10.1 | `requirements.production.txt` | no known vulnerabilities |
| npm audit `--omit=dev` | frontend production dependencies | 0 vulnerabilities |

Not run: Semgrep, Trivy, Gitleaks, OWASP ZAP (not installed; not installed on
production either).

## 5. Identity and files

Unchanged and covered by the suite: bcrypt, login/PIN rate limits, hashed
session tokens, secure cookies, server-side PIN lock, file type/size checks,
private storage with tenant checks, superseded-sheet stamping. The quotation
PDF in the portal is generated per request (no stored copy), `Cache-Control:
private, no-store`, and only for a request in the token's own project and org.

## 6. Residual risk

| Risk | Severity | Owner action |
|---|---|---|
| SEC-01 credentials (Atlas password, viewer token) not yet rotated | High (external) | Rotate in the Atlas console |
| Google OAuth app in Testing mode: calendar grants expire every 7 days | Medium (operational) | Publish the app |
| No off-site backup; no external alerts | Medium | Storage account; alert channel |
| Uploads not malware-scanned; container images not scanned | Medium | ClamAV, Trivy |
| Removed secrets remain in git history | Medium | History rewrite is an owner decision |
| Shared VPS with Tanvika | Medium | Separate or upsize hosts |
