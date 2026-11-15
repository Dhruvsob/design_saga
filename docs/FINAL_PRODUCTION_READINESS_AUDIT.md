# GAMAA ERP: Final production readiness audit

Date: 2026-11-15 (IST evening). Author: Claude (Opus 5.5) working in the
`claude/integrate-release-20261111` line. Every statement below is backed by a
command run on this date; "not verified" means exactly that.

**Verdict: GO WITH KNOWN LIMITATIONS** for normal employee use from 2026-11-16.
No known open P0. Two P1 infrastructure gaps need owner action (off-site
backup copy, external alert delivery); see `POST_LAUNCH_BACKLOG.md`.

## 1. Versions

| Item | Value | Evidence |
|---|---|---|
| Production host | `srv2020574` (187.52.124.46), SSH alias `design-saga-vps` | `hostname`, `hostname -I` |
| Production checkout | `/opt/design-saga-git`, branch `production` | `git rev-parse --abbrev-ref HEAD` |
| Running code (release) | backend image rev `46eb9c2`, web image rev `eaecdcf` (no frontend change since) | `docker inspect ... org.opencontainers.image.revision` |
| Protected files | `deploy/Caddyfile` (local change) and `deploy/Caddyfile.pre-tanvika-20261003T154040Z` untouched | `git status --short` before and after every deploy |
| GitHub `production`/`main` | were at `88ff4ca` (an ancestor of the live revision); fast-forwarded to the live line on 2026-11-15 with the owner's go-ahead, so GitHub `main`, `production`, the release branch and the VPS checkout point at the same commit | `git ls-remote`, `git merge-base --is-ancestor` |
| Tanvika (`gamaa.tech`) | HTTP 200 before and after every deploy; no Tanvika service touched | `curl` |

Source and running images agree: the deploy hook labels images with the commit
it built, and the labels match the checkout.

## 2. Inventory

* **API surface:** 482 operations (205 GET, 170 POST, 43 PATCH, 15 PUT, 49 DELETE),
  generated from the live OpenAPI schema (`app.openapi()`), not hand-listed.
  CI-enforced gates already require every route to authenticate
  (`test_every_api_route_has_authentication_or_reviewed_public_delegation`) and
  every write route to call a permission/ownership guard
  (`test_every_mutating_route_has_permission_or_ownership_guard`).
* **Tenant data:** every tenant collection is registered in
  `core/tenant_registry.py` (enforced by test); tenant export/purge read it.
* **Background jobs (VPS systemd):** daily backup, 5-minute health monitor,
  weekly isolated restore drill, independent encrypted pull, payload
  validation; all last runs `success`.
* **Production size:** 9 tenants, 15 users, 102 journal entries, 89 attendance
  rows, 7 payroll runs (read-only counts).

## 3. Findings by area

### Security (details: `FINAL_SECURITY_ASSESSMENT.md`)
* Cross-tenant reads/writes: **no disclosure and no foreign record changed**
  across every ID route that had test data (63 GET, 144 write), on a local
  two-tenant stack with tenant Admin callers.
* **Fixed (P1 integrity):** six create/update endpoints stored another
  workspace's IDs from the request body (projects, quotations, tasks,
  attendance locations, recurring expenses). Now refused (`core/refs.py`), and
  a 62-case body-reference sweep reports zero accepted.
* **Fixed (P2 audit):** chart-of-accounts deactivation had no audit row and
  returned `ok` for unknown IDs.
* Employee role: 68 of 119 list endpoints refuse; the 4 sensitive-looking ones
  that answer return only own data or static options; 8 escalation attempts
  refused.
* Scans: bandit (medium+) 0, pip-audit (production requirements) 0, npm audit
  (production deps) 0.

### Data integrity (production, read-only)
| Check | Result |
|---|---|
| Journal entries balanced (debit = credit) | 102 of 102 |
| Duplicate invoice numbers per tenant | 0 |
| Duplicate attendance (employee, date) | 0 |
| Payroll: more than one paid/processing run per employee-month | 0 (3 paid, 2 reversed, 2 corrected = correction trail) |
| Records pointing at a missing or foreign project | 0 |
| Stored files missing on disk | 0 |
| Tenant records without `org_id` | 2 platform-level rows (the platform owner user and its app-lock row); no tenant data |

### Business modules
Covered by the automated suites (639 backend unit tests; 29 browser E2E
tests across smoke, accessibility, forms, navigation, UX and phases) plus the
targeted checks in this audit:
* Lead conversion: one winner under concurrency, re-conversion refused (409),
  status changes cannot convert, converted leads never offer "Convert", drag
  state always clears, failures show the server message (code review +
  existing tests).
* Project fee structures: the missing / null / zero / value contract between
  the edit form and the API is now pinned by `test_project_fee_semantics.py`.
* Platform revenue: platform analytics read only platform billing data; no
  route in `routes/platform*.py` or `core/platform_billing.py` reads tenant
  invoices, journals, milestones or receivables.
* Payroll corrections keep an audited trail (`corrected` / `reversed`).

### Performance (local, largest QA tenant: 5,000+ open tasks)
| Path | Median |
|---|---|
| PIN unlock | 318 ms |
| Dashboard stats | 254 ms |
| Session check (`/auth/me`) | 7 ms |
| Capacity heatmap (10 weeks) | 75 ms |
| Task list (full) | 502 ms, 1.7 MB |
Public production endpoints answer in about 0.3 s including TLS. Production
data is far smaller than the test tenant.

### Infrastructure
1 vCPU, 3.8 GiB RAM (2.6 GiB available), 2 GiB swap (about 0.4 GiB used), disk
47% of 48 GB, shared with Tanvika. Containers restart `unless-stopped` and
report healthy (Caddy has no health check; up 3 days). TLS: gamaa.in valid to
2026-12-29, gamaa.tech to 2027-01-01 (Caddy renews automatically).

### Backups and recovery (details: `FINAL_RELEASE_AND_RECOVERY.md`)
Daily backups plus a pre-deploy backup on every release; SHA-256 manifests
verify; an isolated restore of today's pre-deploy backup restored 162 tables
and 2,288 documents (equal to live) in about 1 s. **Gap:** all copies are on
the same VPS disk.

## 4. Status matrix

| State | Items |
|---|---|
| Implemented and verified (this audit) | Tenant isolation on ID routes; body-reference checks; RBAC for Employee role; journals balanced; no duplicate payroll/invoices/attendance; backups + isolated restore; deploy, health and rollback path; capacity, transmittals, approvals, timeline releases |
| Implemented, verified by existing automated tests only | Attendance paid-leave rules, payroll calculations, accounting reports, invoices/receipts, CRM, quotations, procurement |
| Not verified here | Live production sign-in/PIN timings with a real account (no production credentials used by design); Safari/iOS; load beyond a few concurrent users |
| Blocked by external configuration | Off-site backup target; external alert channel; Google OAuth publishing; credential rotation SEC-01; e-mail delivery |
| Deferred (release risk / roadmap) | Product & material library, selections, object storage, email/WhatsApp channels, stamping superseded drawing files |
