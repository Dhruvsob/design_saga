# GAMAA ERP: master audit (release `504a2c3`, 2026-11-20)

Companion reports: `FINAL_SECURITY_REPORT.md`, `FINAL_BUSINESS_LOGIC_VERIFICATION.md`,
`FINAL_UI_UX_REVIEW.md`, `FINAL_BACKUP_AND_RECOVERY.md`, `FINAL_TEST_RESULTS.md`,
`FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md`, `FINAL_PRODUCTION_SIGNOFF.md`.
Earlier cycles: `FINAL_PRODUCTION_READINESS_AUDIT.md` (2026-11-15),
`IMPROVEMENT_FINDINGS_2026-11-16.md` (rounds 1-2).

## 1. What is running

* Repository `Dhruvsob/design_saga`; release branch `claude/improvements-20261116`.
* Production `gamaa.in` = host `srv2020574`, checkout `/opt/design-saga-git`,
  images labelled `504a2c3` (verified 2026-11-20 09:07 UTC).
* GitHub `main`/`production` at `200aa28` (one release behind; push waits for
  the owner's OK). No staging environment exists; the local QA stack plays
  that role.
* `gamaa.tech` (Tanvika) shares the host and was not touched.
* Tenancy (preserved as built): GAMAA is the platform (super-admin,
  `/platform`); each customer firm is an organisation (`org_id`) with its own
  branding and its own role permissions (Team & Roles); projects carry
  assignment-based visibility; client portal users act only through personal
  links. **Branches (offices inside a firm) are not modelled**: there is no
  branch field or branch-scoped permission in the backend, so a multi-office
  firm is one workspace. Adding branches would be a data-architecture change
  (REQUIRES OWNER APPROVAL).

## 2. Inventory (from code, 2026-11-20)

| Area | Count | Source |
|---|---|---|
| API operations | 496 (211 GET, 175 POST, 44 PATCH, 15 PUT, 51 DELETE) on 390 paths | `app.openapi()` |
| Front-end routes | 39 (36 code-split pages) | `frontend/src/App.js` |
| Tenant collections | 74, each registered for export/purge | `core/tenant_registry.py` |
| In-app background jobs | 4: notification scan, check-out reminders, Google Calendar sync and reconnect notices, collection reminders | `server.py` |
| Host jobs (systemd) | daily backup, 5-min monitor, weekly restore drill, payload validation | `systemctl list-timers` |
| Integrations | Google sign-in, Google Calendar (per user), client portal links; e-mail, push and AI storage not configured | env and code |

## 3. Completion matrix (this cycle and carried evidence)

Status words: VERIFIED, FIXED AND VERIFIED, PARTIAL, MISSING, EXTERNALLY
BLOCKED, REQUIRES OWNER APPROVAL, NOT YET VERIFIED.

| Component / workflow | Role | Env / revision | Evidence | Status | Remaining action |
|---|---|---|---|---|---|
| Google Calendar: outage vs expiry, notice, catch-up | each employee | local + prod `504a2c3` | 10 unit tests; prod notice sent | FIXED AND VERIFIED | Owner: publish OAuth app; user: reconnect |
| Google Calendar reconnect with a real account | employee | prod | needs the account holder | NOT YET VERIFIED | Reconnect from Calendar |
| Projects / Quotations for restricted roles | Designer (studio overrides) | local `504a2c3` | `ux.spec` desktop + phone; prod 403 logs | FIXED AND VERIFIED | none |
| Notification panel on phones | all | local `504a2c3` | measured bounds, screenshots | FIXED AND VERIFIED | none |
| Loans, invoice receipts, commissions, gold, FY boundary | finance | local `504a2c3` | 37/37 fixture checks | VERIFIED | Investment register is MISSING (proposal) |
| Payroll, advances, period close | finance/HR | local `504a2c3` | `money.spec`, `period-close.spec` (rerun 2026-11-20) | VERIFIED | Hand-worked proration fixture: PARTIAL |
| Tenant isolation | all | local `200aa28` | cross-tenant probe round 2 | VERIFIED | none |
| Role × action × resource matrix | all roles | mixed | Employee + Designer checks; route gates | PARTIAL | Live probe for Accountant, HR, portal |
| Enquiry → lead → client → quotation → project | studio | local `504a2c3` | `crm-chain.spec`, `proposal.spec`, `ux.spec` (2026-11-20) | VERIFIED | Portal quotation acceptance: proposal #3 |
| Concept → GFC → site (drawings, transmittals) | designer, site | local `504a2c3` | `drawings.spec` (2026-11-20, after a test fix, see #7) | VERIFIED | none |
| Measurement → BOQ → PO → GRN → bill | procurement | local `504a2c3` | `procurement-chain.spec`, `collections.spec` (2026-11-20) | VERIFIED | Selections: proposal #1 |
| Snags with photos, site visits | site | local `504a2c3` | `snags.spec`, `site-visits.spec`, `expense-receipts.spec` (2026-11-20) | VERIFIED | Real-device photo upload: NOT YET VERIFIED |
| Reminders → notification → record | all | local + prod | check-out reminder, calendar notice | VERIFIED | Phone/e-mail delivery: proposal #2 |
| Accessibility | all | local | axe A/AA pass | PARTIAL | Screen reader, zoom, real devices |
| Backups and isolated restore | operator | prod | drill pass 2026-11-20 | VERIFIED | Off-site: EXTERNALLY BLOCKED |
| Alerts | operator | prod | monitor runs; alerts local only | EXTERNALLY BLOCKED | Alert channel |
| CI | developers | GitHub | billing lock since 2026-10-24 | EXTERNALLY BLOCKED | GitHub billing |
| Credential rotation SEC-01 | owner | Atlas | not rotated | EXTERNALLY BLOCKED | Rotate |

## 4. Defects found this cycle

| # | Severity | Defect (evidence) | Root cause | Fix | Commit |
|---|---|---|---|---|---|
| 1 | P2 | Production's only Google Calendar connection paused since late October; nobody was told | Google expires grants after 7 days while the OAuth app is in Testing mode; the app gave no notice and showed the reason twice | Notice once per pause, clear status, Testing-mode hint, Disconnect while paused | `bcb5e3b` |
| 2 | P2 | Any Google outage or rate limit during token refresh would have paused sync until the user reconnected | Every non-200 refresh answer was treated as "authorization expired" | Only `invalid_grant`-type refusals pause; 5xx/429/network retry; bad client = server message | `bcb5e3b` |
| 3 | P2 (privacy) | After a pause, Google kept copies of items deleted, completed or reassigned meanwhile | Nothing is queued while paused; reconnect only re-sent current items | Reconnect queues removal of stale copies | `bcb5e3b` |
| 4 | P2 | Two active Designers saw empty Projects and Quotations pages (prod logs: 403 on `/clients`, `/employees` beside 200 on `/projects`) | A lookup the role cannot read rejected the page's whole `Promise.all` | `optionalList` on Projects, Quotations, Invoices, Accounting; Projects loading/error states | `504a2c3` |
| 5 | P3 | Notification panel started 22-45 px off-screen on phones | Right-anchored to the bell, not the screen | Full-width panel under the top bar on small screens | `504a2c3` |
| 6 | P3 | "Loading" and "failed" looked like "No projects yet" | One empty state for three conditions | Separate states with Try again | `504a2c3` |
| 7 | P3 (test only) | `drawings.spec` failed on every run: "Approve" matched two menu items | P2.7 added "Ask client to approve" to the same menu; the test matched names by substring | The test clicks the item's own test id; product unchanged | docs commit |

No P0/P1 defects found. No accounting or payroll calculation defect found.

## 5. Outstanding work

* Owner: publish the Google OAuth app; reconnect the paused calendar; off-site
  backup target; alert channel; GitHub billing; SEC-01 rotation; approve the
  GitHub `main`/`production` push to `504a2c3`.
* Approvals: `FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md`.
* Verification still open: screen reader, real phones and Safari, a
  hand-worked payroll proration fixture, a live role probe for Accountant, HR
  and portal users.
