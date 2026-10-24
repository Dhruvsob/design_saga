# Design Saga Repair Tracker

Last updated: 2026-10-24 (Asia/Calcutta)

## Current Checkpoint

- Local checkout: `codex/repair-release`; deployed application baseline `81b06f3` is pushed to GitHub `main`, `production`, `repair`, and `codex/repair-release`.
- Production checkout: `/opt/design-saga-git`; runtime commit `949c372` and replay-safe updater commit `81b06f3` were verified on 2026-10-24.
- Production working tree: protected external changes in `deploy/Caddyfile` plus `deploy/Caddyfile.pre-tanvika-20261003T154040Z`. Do not overwrite, reset, or include these changes in Design Saga deployments.
- Live URL/API and key-only SSH are reachable. Caddy, web, backend, FerretDB and PostgreSQL were healthy at the last deployment verification.
- Checksummed backup `/opt/design-saga-backups/20261024T062601Z` completed before the latest backend/frontend replacement.
- Current action: continue the remaining P0 operations dependencies, then the P1 route-by-route authorization and business-integrity audit. Do not repeat the completed attendance or quotation-conversion work.

## System Inventory

| Layer | Current implementation | Evidence/status |
|---|---|---|
| Frontend | React/CRA served by Nginx container | Confirmed from Dockerfile/package/docs; workflow coverage varies |
| Backend | FastAPI, mostly `backend/server.py` plus modular routes | Confirmed; production health passes |
| Database | PostgreSQL 17 + DocumentDB extension behind FerretDB Mongo protocol | Confirmed from Compose and running containers |
| Authentication | Password/Google-compatible session tokens in `user_sessions`; HTTP-only secure cookie or bearer token | Recent tenant-login repair verified live on 2026-10-01 |
| Tenancy | `org_id`, scoped DB wrapper, tenant filters, SuperAdmin exceptions | Strong prior evidence; requires continuing endpoint-by-endpoint audit |
| RBAC | Server-side role/permission expansion with tenant-specific overrides | Implemented; coverage audit ongoing |
| Background jobs | In-process notification due/overdue scheduler | Previously reported; runtime behavior not reverified in this pass |
| File storage | Tenant-scoped external links plus content-validated local binary storage on a dedicated persistent VPS mount | Implemented; deployment/live upload verification pending |
| Reverse proxy/TLS | Caddy with automatic HTTPS; shared VPS routing file | Healthy; production file has protected external edits |
| Deployment | Docker Compose; post-merge invokes tracked `deploy/update-production.sh` | Change-aware, backup-gated, health-checked, service-specific, and refuses automatic Compose/Caddy changes |
| Backups | Dedicated daily PostgreSQL/FerretDB and uploaded-file archive with checksums, catalogue validation, seven-day retention, and tested isolated database restore | Active on VPS; same-host storage remains a disaster-recovery limitation |

## Workflow Inventory

| Workflow | Status | Current evidence |
|---|---|---|
| Tenant owner/user login | Previously verified | Live synthetic owner and employee login by email/ID; bcrypt and isolation checks passed at `dbf6595` |
| Tenant isolation | Previously verified, audit continues | Prior two-tenant tests and live cross-tenant 404/RBAC 403 evidence |
| Attendance | Focused critical-path verification complete | Identity, IST date, punch idempotency, authorized-site behavior, review concurrency, leave preservation, correction consistency, and payroll blocking verified |
| Leads → quotations/BOQ → projects | Partial | Implemented and prior module tests exist; full current conversion chain unverified |
| Projects → tasks/assignments | Previously tested, needs currency check | Historical task visibility and assignment evidence exists |
| Vendors/procurement | Partial | Vendor, PO and accounting tests exist; current end-to-end flow unverified |
| Invoices/receipts/accounting | Focused critical-path verification complete | Payment permissions, exact settlement, idempotency, reversals, source deletion, account types, journal balance, and dashboard netting verified |
| Payroll/expenses | Payroll critical path verified; expenses partial | Concurrent payroll posting, account types, unresolved-review blocking, permissions, and journal cardinality verified with synthetic data |
| Notifications/calendar | Previously tested | Historical iteration evidence; scheduler runtime not reverified |
| Files/documents/exports | Unverified | Access control, persistence, and cross-tenant guessing audit pending |

## Reused Evidence

- `dbf6595`: tenant login supports email, employee ID formats, and internal user ID; live synthetic owner/user tests passed and temporary data was purged.
- `f02246e`: production session cookies default to secure.
- PRD and prior reports document P0 tenant-isolation repairs, accounting posting/reversal, suspension enforcement, plan limits, employee-login linking, and notification tenant stamping.
- `plan.md` documents completed attendance, project-finance visibility, salary-history, calendar privacy/reminders, and employee-account work.
- Reuse is provisional where only narrative evidence exists; run the smallest current verification before relying on it for a new repair.

## Prioritized Issue Queue

| ID | Priority | Issue / verification target | State |
|---|---|---|---|
| DS-001 | High | Server-side invoice/dashboard financial-read authorization bypass | Fixed, deployed, and verified live |
| DS-002 | High | Verify attendance identity, idempotency, timezone boundary, approval audit, and payroll consistency end to end | Fixed, deployed, and verified live |
| DS-003 | High | Establish a validated backup and restore path for Design Saga PostgreSQL/FerretDB data and deployment state | Fixed and active with repeatable restore drill and recovery runbook; offsite copy remains a follow-up |
| DS-004 | High | Reconcile dashboard revenue/outstanding figures with journal/invoice sources and permission boundaries | Fixed, deployed, and verified live |
| DS-005 | High | Audit project/task/file authorization and unsafe attachment URLs | Fixed, deployed, and verified live |
| DS-006 | High | Prevent cross-tenant account reset and tenant-to-SuperAdmin escalation | Fixed, deployed, and verified live |
| DS-007 | High | Replace unsafe blanket Git redeploy hook with change-aware deployment | Fixed, installed, and verified live |
| DS-008 | Medium | Measure endpoint/page performance and inspect indexes/N+1/pagination before optimizing | In progress: route-level code splitting reduces the initial JS bundle from 1.52 MB to 495 KB (372 KB to 149 KB gzip); API latency, index and large-data traces remain |
| DS-009 | High | Employee/payroll endpoints expose compensation, bank, and private HR data through broad employee-read permission | Fixed, deployed, and verified live |
| DS-010 | High | Prevent password-login identifier spraying from one network source | Fixed, deployed, and verified live |
| DS-011 | High | Rejected punch retry, late-review races, manual-time integrity, weekly offs, and overlapping leave | Fixed, deployed, and verified live |
| DS-012 | High | Empty role overrides restored default privileges; legacy session routes missed tenant lifecycle gates | Fixed, deployed, and verified live |
| DS-013 | High | Search, comments, calendar, and event notifications bypassed primary visibility boundaries | Fixed, deployed, and verified live |
| DS-014 | High | Repair-branch scheduler, audit-chain, business-date, idempotency, numbering, and workflow integrity gaps | Fixed, deployed, and verified live |
| DS-015 | Medium | Central project milestone collections/receivables view | Deployed; four pending Design Saga milestones confirmed in the production data audit |
| DS-018 | High | Accounting posting, ledger, GST and bank-reconciliation integrity controls | Deployed; focused regression suite and production health checks pass |
| DS-019 | High | Vendor bill, Accounts Payable, advance-payment and three-way-match integrity | Deployed; sample vendor balance and project-linked draft bill verified live |
| DS-020 | High | All-time accounting ranges and safe reversal undo | Deployed; exact historical correction remains record-specific and evidence-gated |
| DS-021 | High | Capital, investment and person-wise receivable/payable workflows | Deployed and verified live with fully reversed sample-tenant journals |
| DS-022 | Medium | Chart of Accounts current balances, editing, deactivation and future duplicate-code prevention | Deployed and verified; scoped duplicate-code cleanup completed after backup |
| DS-023 | High | Invoice accrual, Accounts Receivable settlement and revenue/GST recognition | Fixed, deployed and verified live with a fully reversed sample-invoice lifecycle |
| DS-024 | Medium | Private notification controls, complete search, tenant audit UI and cash-flow activity split | Fixed, regression-tested and deployed; cash-flow totals retain backward-compatible fields |
| DS-025 | Medium | Durable project/vendor document uploads with tenant authorization, validation and backup | Implemented and regression-tested; production deployment/live verification pending |
| DS-026 | High | Quotation conversion bypasses client/project/task create permissions | Fixed, covered by conversion/concurrency regressions, deployed and verified healthy at `fbbd7da` |
| DS-027 | High | Vendor permissions and broad tenant reads exposed purchase orders/GRNs outside visible projects; project invoice access exposed vendor bills/costs | Fixed, covered by permission and project-finance regressions, deployed and verified healthy at `949c372` |
| DS-028 | Medium | Production updater could repeat the same successful release because `ORIG_HEAD` was not advanced | Fixed and installed at `81b06f3`; replay now exits without backup, rebuild or restart |

## User-Reported Master Backlog - 2026-10-23

This is the canonical intake list supplied after the repair-release deployment. Statuses below are based on current-code inspection; production-data items remain open until the exact tenant records are reconciled. "Implemented" does not mean historical production data was rewritten.

| ID | Sev | Reported issue | Reconciled state |
|---|---|---|---|
| BR-001 | High | Invoice payment cannot be recorded / draft invoice stuck | Verified live on sample `INV-1001`: paid posting and reversal succeeded, then the invoice was restored to draft with no active receipt journal |
| BR-002 | High | PO/bill cannot link to project | API/UI support is deployed; a temporary project-linked sample bill was created and deleted live without a journal |
| BR-003 | High | Collections Due empty | Deployed; production audit found four pending Design Saga milestones, all linked to projects |
| BR-004 | High | Vendor ledger shows wrong balance | Verified live: sample vendor summary and full ledger both return ₹29,500 |
| BR-005 | High | AR and client receivables not reflected | Fixed and verified live: issue posted ₹59,000 A/R against ₹50,000 revenue + ₹9,000 GST; payment settled A/R, and the full rollback returned every tested balance to baseline |
| BR-006 | High | Attendance check-in and employee-login link broken | Fixed and deployed; attendance identity/project access/idempotency covered by current tests |
| BR-007 | High | Notifications and settings unavailable | Fixed and deployed: each user controls task, finance, attendance and calendar alerts; mandatory account notices remain enabled and preferences are tenant/user scoped |
| BR-008 | Medium | Chart of Accounts balances show zero/opening only | Fixed and verified live: all listed accounts include journal-derived current balances |
| BR-009 | Medium | Duplicate account codes | Future duplicates are rejected; exact unused live duplicates were safely deactivated/re-coded and both affected audit chains pass |
| BR-010 | Medium | Inconsistent monthly balances | Requires exact screen/period data trace after DS-022 current-balance correction |
| BR-011 | Medium | Tasks without due dates marked overdue | Current dashboard and scheduler explicitly require a due date; retain as regression coverage |
| BR-012 | Medium | Preview broken | Needs workflow-specific reproduction; invoice PDF and document preview must be assessed separately |
| BR-013 | Medium | Expense invalid URL | URL handling/security correction is present; production reproduction still useful for affected legacy record |
| BR-014 | Medium | Invoice sending not implemented | Confirmed gap: status/PDF exist, outbound email delivery does not |
| BR-015 | Medium | Invoice payment link/UPI missing | Confirmed product gap; requires payment-provider/security design, not a hard-coded link |
| BR-016 | Medium | GST incomplete | Partial: input/output posting exists; tenant GST settings, split GST and GSTR reports remain |
| BR-017 | Medium | Tally export missing | Confirmed export gap |
| BR-018 | Medium | AI assistant not functional | Requires provider/config/runtime audit; not an accounting source of truth |
| BR-019 | Medium | File upload unavailable | Fixed in code: project/vendor UI uploads to tenant-isolated persistent storage with permission checks, verified file signatures, 15 MB limits, safe delivery/deletion and backup inclusion; production verification pending |
| BR-020 | Medium | Client portal link missing | Explicit share-token/link UI is implemented and deployed |
| BR-021 | Medium | Search misses quotations/events | Fixed and deployed: advanced quotations and privacy-filtered calendar events are included in global search |
| BR-022 | Medium | Slow page loading | Frontend route splitting implemented and smoke-tested across dashboard, accounting, attendance, calendar, audit and privacy; API tracing/pagination remains under DS-008 |
| BR-023 | Medium | Cash-flow split missing | Fixed: report and CSV now split operating/investing/financing activities and reconcile every cash/bank account while preserving existing totals |
| BR-024 | Medium | Draft invoice counts inconsistent | Not reproducible in the 24/10 production trace: the sole current invoice is one explicit sample-tenant draft and all active invoice queries count it consistently; monitor as data grows |
| BR-025 | Low | Date formats inconsistent | Shared DD/MM/YYYY formatter exists; remaining raw-date surfaces need inventory |
| BR-026 | Low | New-tenant PO dead-end | Send/GRN paths exist; empty master-data onboarding needs live workflow verification |
| BR-027 | Low | Bill creation location confusing | UX review item; preserve vendor and PO context while improving discoverability |
| BR-028 | Low | Unsafe automatic matching by name | Confirmed residual risk in selected legacy fallbacks; migrate to IDs where evidence permits |
| BR-029 | Low | Large flat dropdowns | Confirmed usability gap; replace only high-volume selectors with searchable controls |
| BR-030 | Low | System account codes missing | Current defaults have codes; audit legacy/generated accounts and fill only unambiguous gaps |
| BR-031 | Low | Account edit/deactivate missing | Fixed and deployed through the Chart of Accounts UI with non-destructive deactivation/restore |
| BR-032 | Low | Gujarati text in English UI | Confirmed one Collections heading; removed under DS-022 while retaining English accounting terminology |
| BR-033 | Low | Demo data unclean | Sample tenant only; clean via backup and explicit scoped scripts, never production tenants |
| BR-034 | Low | Backup missing | Fixed: checksummed daily database/deployment backup and restore validation active on VPS; offsite copy remains |
| BR-035 | Low | Help and audit-log screens missing | Tenant-admin audit screen and integrity verification are deployed; a generic help manual remains a product-content decision, not a production defect |

### Accounting workflow extension (DS-021/DS-022)

- Reuse the existing journal, ledger, tenant scope, RBAC, reversal and audit mechanisms.
- Add simple balance-sheet workflows for owner capital, owner drawings, gold purchase, money given, money received and repayments.
- Person-wise balances use separate `Advance to - <name>` asset or `Loan from - <name>` liability accounts. Repayments cannot exceed the ledger outstanding amount.
- Do not classify capital, investments, loans or advances as business income/expense.
- Do not add gold sale/profit valuation until cost-basis and gain/loss treatment are explicitly designed and reviewed with the accountant.
- Show derived current balance in Chart of Accounts, while preserving opening balance as accounting input.
- Expose existing edit/deactivate/restore controls; posted account type/opening balance remain locked by the backend.

## Issue Log

### DS-020: All-time accounting and reversal correction

- Root causes:
  - Selecting `All time` sent no period parameter, while report and journal APIs interpret an omitted period as the current Indian financial year. Daybook and account-ledger presets had the same ambiguity.
  - Income/Expense history used the legacy unpaginated journal response and silently showed only the newest 200 rows.
  - Reversal entries were intentionally immutable but had no safe way to correct an accidental reversal.
- Correction:
  - Add an explicit `fy=all` contract that resolves to an unbounded date range, use it across reports, exports, Daybook, account ledgers, Income, and Expense, and show the selected report label.
  - Make Income/Expense history server-filtered and paginated, include reversal/reinstatement records, and open the shared transaction detail view.
  - Add `Undo reversal` for direct manual/income/expense entries. It posts an idempotent reinstatement journal, retains the original reversal and audit event, heals interrupted retries, and does not support source-driven invoice/milestone/payroll/vendor entries whose business document must be restored through its own workflow.
- Verification: Python compilation, period-contract assertion, `git diff --check`, frontend ESLint, and Vite production build pass. A pinned local backend environment additionally passed 57 focused accounting, vendor-payment, URL/download safety, RBAC/session, attendance, and Google Calendar tests. The build retains the existing large-chunk warning; FastAPI reports only its existing lifespan deprecation warnings.
- Production status: not deployed. The named ₹10,000 Ritesh Soni reversal has not been changed because the exact tenant, original journal, reversal journal, and linked source cannot be safely inspected while SSH/public access is unavailable.
- Database effect after deployment: no migration or automatic rewrite. Using Undo reversal adds one balanced reinstatement journal and audit record; it never deletes posted accounting evidence.

### DS-019: Vendor bills, A/P and three-way matching

- Root causes:
  - Received vendor bills updated the vendor UI but posted no journal, while vendor payments debited Accounts Payable. A/P could therefore become negative without a booked liability.
  - Bill schemas could not carry a purchase-order or PO-line link, while the three-way matcher queried those links and obsolete `lines`/`amount` fields. The advertised PO/GRN/bill comparison could not succeed.
  - Unallocated vendor payments also debited A/P instead of a vendor-advance asset.
  - Posted bills could be financially edited or hard-deleted, and paid bills could be cancelled without first reversing their payments.
  - Draft bills leaked into billed/performance/commission totals, reversed payments inflated the vendor summary, and filtered vendor ledgers lost their pre-period opening balance.
- Correction:
  - New received non-PO bills post DR expense + DR Input GST / CR Accounts Payable + CR TDS Payable. The UI requires an explicit expense account; legacy API clients fall back to `Miscellaneous Expenses` with an `accounting_warning` marker.
  - New PO bills carry `po_id`/`po_line_id`, verify the vendor and received quantities, and post DR GRN Clearing + DR Input GST / CR Accounts Payable + CR TDS Payable. The existing three-way report now reads `items` and `total` and excludes draft/cancelled bills.
  - Allocated payments debit A/P; excess/on-account amounts debit the new `Vendor Advances` asset; both use the central journal validator and a linked source ID.
  - Vendor bill and payment creation use idempotency keys. Posted financials require reversal; paid bills cannot be cancelled until linked payments are reversed; cancellation posts an idempotent bill reversal and preserves/corrects commission audit state.
  - Drafts are excluded from billed, ledger, performance, and commission figures; reversed payments are excluded from paid summaries; date-filtered vendor ledgers carry the correct opening balance.
  - The vendor bill form can select a purchase order and prefill linked PO lines, or select an expense account for a non-PO bill. Failed API calls remain visible with an error instead of closing the form.
- Files changed: `backend/core/indexes.py`, `backend/models/accounting.py`, `backend/models/vendor.py`, `backend/routes/purchase.py`, `backend/routes/vendors.py`, vendor/purchase/accounting regression tests, and `frontend/src/pages/VendorDetail.jsx`.
- Verification: Python compilation and `git diff --check` pass; frontend ESLint and Vite production build pass; 20 focused accounting/vendor-payment/purchase/release tests pass locally.
- Database effect: startup/account seeding adds the zero-balance `Vendor Advances` asset when missing and adds non-destructive vendor-bill PO/idempotency indexes. No historical bill or journal is rewritten automatically.
- Production gate: audit historical non-draft vendor bills for missing `journal_entry_id`, compare bill totals to existing payment/AP activity, back up the database, and run an explicit reviewed backfill only where evidence is unambiguous.

### DS-018: Accounting integrity controls

- Root causes:
  - Journal posting accepted malformed dates, blank narrations, inactive accounts, non-finite/negative values, and lines containing both or neither debit and credit.
  - Posted standalone journals could be amount/date edited or hard-deleted, bypassing a durable correction trail.
  - A date-filtered account ledger started from the static account opening balance and omitted every movement before the selected range; large ledgers were silently cut at 2,000 entries.
  - Expense and recurring-expense input GST debited the `GST Payable` liability instead of an input-tax asset.
  - Manual bank matching did not verify account, direction, amount, date proximity, reversal state, or duplicate use; unmatched rows could be marked reconciled.
  - Recurring-expense journal idempotency keyed only by rule, so a later period could conflict with the first successful posting.
  - Balance-sheet reconcile directly mutated an equity opening balance, hiding the source of an imbalance.
- Correction:
  - Validate journal dates, narration, line cardinality, finite non-negative values, exactly-one-side debit/credit, balance, and active same-tenant accounts.
  - Require reversal for posted date/amount corrections and disable physical journal deletion in API/UI; descriptive metadata remains auditable and editable.
  - Carry pre-period movements into filtered ledger opening balances and fail explicitly above 10,000 rows instead of silently truncating.
  - Seed and use `Input GST Credit` as an asset for new expense input-tax postings. Historical GST rows are not rewritten automatically.
  - Require a unique, unreversed journal with the same bank account, signed direction, exact paise amount, and a three-day date window before match/reconcile; audit both actions.
  - Key recurring postings by rule and run date, and tighten automatic bank matching to one paisa.
  - Disable automatic balance-sheet opening-balance mutation and direct users to diagnose and reverse the actual bad entry.
  - Lock account type and opening balance after journal activity; reject duplicate account names and audit account updates.
- Files changed: `backend/core/finance.py`, `backend/models/accounting.py`, `backend/routes/accounting.py`, `backend/routes/finance_extras.py`, `backend/tests/test_accounting_safety.py`, `frontend/src/components/TransactionDetail.jsx`, `frontend/src/pages/Accounting.jsx`.
- Verification: Python compilation and `git diff --check` pass; frontend ESLint and Vite production build pass; the focused accounting/vendor-payment/purchase/release suite passes 20/20 locally. Container integration and production data audits remain required before deployment.
- Database effect: startup/account-list seeding adds one zero-balance asset account (`Input GST Credit`) per tenant when missing. No existing journal, opening balance, or business record is rewritten.
- Deployment: pending VPS access, verified backup, disposable integration test, and service-specific health checks.

### DS-015: Central project collections due (ઉઘરાણી)

- Existing behavior: payment milestones can already be created and paid inside each individual project, and Accounting shows only the first eight milestones due in the next 30 days.
- Gap: there was no tenant-wide view for accountants to see total pending, overdue, next-30-day, later, and undated project collections with project/client context.
- Correction: added a tenant-scoped read endpoint over existing payment milestones, project/client enrichment, outstanding-amount calculation, due buckets, an indexed query path, search/filter controls, DD/MM/YYYY rendering, and direct navigation to the original project. No second payment or accounting engine was introduced.
- Files changed: `backend/routes/accounting.py`, `backend/core/indexes.py`, `backend/tests/test_accounting_safety.py`, `frontend/src/pages/Accounting.jsx`.
- Verification: backend modules compile; frontend ESLint passes; Vite production build passes. The focused pytest file could not run locally because this Windows Python installation does not include pytest. No production data was read or changed.
- Deployment: pending. `gamaa.in:443` and `187.52.124.46:22` timed out on 2026-10-20, so backup, service deployment, and live verification were not attempted.
- Rollback: revert the DS-015 commit and redeploy backend/web. The added non-unique milestone index is backward-compatible and may remain. No data migration or rewrite is involved.

### DS-001: Server-side financial read authorization

- Symptom/risk: an authenticated user without `invoices.read` or `finance.read` can call invoice list/detail/PDF APIs directly. `/dashboard/stats` also calculates and returns tenant revenue and collection totals to every authenticated user. Navigation hiding is not an authorization boundary.
- Severity: High. Tenant scoping prevents cross-tenant reads, but restricted users can read sensitive financial data from their own tenant.
- Evidence collected:
  - `GET /invoices`, `GET /invoices/{id}`, and authenticated `GET /invoices/{id}/pdf` only called authentication helpers before the repair.
  - `/dashboard/stats` exposed journal-derived revenue and invoice-derived collections without financial permission checks.
  - The accounting router is protected by a router-level `finance.read` dependency and is not affected by this finding.
- Root cause: incomplete server-side authorization on monolithic invoice/dashboard handlers; the frontend sidebar was incorrectly relied on to hide access.
- Local correction:
  - Enforce `invoices.read` or `finance.read` for invoice list/detail/authenticated PDF reads.
  - Keep unauthenticated project share-token PDFs working through the existing token validation path.
  - Require `dashboard.read`; query and return revenue only for `finance.read`, and collections only for `invoices.read` or `finance.read`.
  - Hide unauthorized dashboard finance cards and protect the `/invoices` frontend route.
- Files changed: `backend/server.py`, `backend/tests/test_financial_read_permissions.py`, `frontend/src/App.js`, `frontend/src/pages/Dashboard.jsx`.
- Pre-fix isolated reproduction against the production backend image and a disposable database:
  - Restricted Employee received HTTP 200 from invoice list, invoice detail, and authenticated invoice PDF endpoints.
  - Restricted Employee dashboard exposed revenue `54321` and collections due `12345` from synthetic records.
  - Cross-tenant invoice detail returned 404, confirming tenant scoping remained intact while role authorization was missing.
- Post-fix isolated integration results against candidate commit `1a1903c`:
  - Restricted Employee received 403 from invoice list, detail, and authenticated PDF; dashboard omitted revenue, collection totals, and collection alerts.
  - Project Manager retained same-tenant invoice/collection visibility, did not receive revenue, and received 404 for another tenant's invoice.
  - Accountant retained revenue, collection, and authenticated PDF access.
  - A valid unauthenticated project share token still returned its invoice PDF with HTTP 200.
  - Focused permission-helper assertions passed.
  - Candidate backend and frontend Docker images both built successfully. The frontend build completed with existing dependency/hook warnings and no errors.
- Cleanup verification: the disposable database, candidate containers/images, temporary worktree, repair ref, and transfer bundle were removed after testing.
- Production deployment:
  - Captured a 22 MB custom-format PostgreSQL backup, globals, environment/Caddy snapshots, commit/image metadata, and checksums before deployment.
  - Tagged the prior backend and web images as `rollback-dbf6595`.
  - Deployed backend and web only; PostgreSQL, FerretDB, and Caddy were not restarted.
  - Both new containers became healthy; site and API returned HTTP 200, protected unauthenticated endpoints returned 401, runtime permission assertions passed, and recent logs contained no critical errors.
- Current state: deployed at `1a1903c` within production checkpoint `a659939` and verified live.
- Rollback: revert the DS-001 commit. No database migration or data rewrite is involved.

### DS-003: Dedicated Design Saga backup and restore path

- Symptom/risk: Design Saga had no confirmed scheduled backup. Existing encrypted ERP timers pull Gamma and jewellery ERP payloads from another VPS; their manifests do not include this VPS's Design Saga PostgreSQL volume.
- Severity: High. A host or volume failure could otherwise make current Design Saga data unrecoverable.
- Root cause: Design Saga was deployed after the independent cross-server backup workflow and was never added to a dedicated backup schedule.
- Correction:
  - Added `deploy/backup.sh` with a non-overlapping lock, root-only permissions, atomic publication, custom PostgreSQL dump, role dump, Caddy/environment/Git/image metadata, archive listing validation, SHA-256 checksums, and seven-day retention.
  - Added a hardened systemd oneshot service and daily persistent timer. It runs at 18:22 UTC with randomized delay and does not stop or write to application services.
- Verification:
  - Shell syntax and systemd unit validation passed.
  - Manual systemd execution created `/opt/design-saga-backups/20261012T092326Z`; all checksums and the `pg_restore` catalogue validation passed.
  - Restored that archive into a memory-limited temporary DocumentDB/PostgreSQL container using a filtered restore list for the two image-preseeded `pg_cron` rows. Restore completed with 76 non-system tables and 535 document rows.
  - The restore container and temporary list were removed. `design-saga-backup.timer` is enabled and active; its next run was scheduled for 2026-10-12 18:22 UTC.
- Files changed: `deploy/backup.sh`, `deploy/systemd/design-saga-backup.service`, `deploy/systemd/design-saga-backup.timer`.
- Current state: deployed at `1bafdea` and verified. No application/database restart or data mutation was required.
- Limitation: dedicated archives currently remain on the same VPS. Configure an independently controlled offsite destination before treating this as host-loss disaster recovery.
- Rollback: disable/remove `design-saga-backup.timer` and its two units, then revert `1bafdea`. Existing archives can remain for recovery or be removed separately after explicit approval.

#### 2026-10-24 recovery revalidation

- Added `deploy/restore-drill.sh`, which accepts only a timestamped archive directly under the configured backup root, verifies database and uploaded-file checksums, restores into a memory/CPU-limited container with no published ports, compares non-system table and DocumentDB row counts with production, and always removes its temporary container and volume.
- Backup `/opt/design-saga-backups/20261024T062601Z` passed the drill: 106 non-system tables and 1,015 document rows matched production; database restore completed in 2 seconds.
- Added `docs/runbooks/DISASTER-RECOVERY.md` with the initial 24-hour engineering RPO, 8-hour engineering RTO, restore validation sequence, and explicit provider-loss limitation. Encrypted off-server replication still requires a destination and credentials.

### DS-002A: Attendance identity, punch idempotency, and business date

- Symptom/risk:
  - Check-in, check-out, leave creation, and leave-balance endpoints trusted a client-supplied `employee_id`. A regular employee could act for a coworker in the same tenant.
  - A regular employee could list tenant-wide leave requests when `mine=true` was omitted.
  - Attendance day/month defaults used UTC, producing the previous business date between midnight and 05:29 IST.
  - Check-in used a read-then-insert flow with a non-unique employee/date index, allowing concurrent requests to create duplicates.
- Severity: High. This enabled within-tenant attendance/leave impersonation and could corrupt payroll inputs.
- Production precondition audit: 33 attendance rows, zero duplicate `(org_id, employee_id, date)` groups, and zero rows missing `org_id`. An isolated FerretDB probe confirmed a unique index can coexist with the legacy index.
- Pre-fix isolated reproduction against rollback image `dbf6595`:
  - Employee check-in for a coworker returned 200.
  - Employee leave creation for a coworker returned 200.
  - Employee tenant-wide leave listing exposed the coworker's row.
  - Employee coworker leave-balance request returned 200.
- Correction:
  - Resolve self-service attendance identity from the authenticated employee link; only attendance managers may target another employee.
  - Enforce the same self-only boundary for leave lists and leave balances.
  - Use the shared IST clock for attendance dates and default reporting periods.
  - Add a unique `(org_id, employee_id, date)` index, atomic conditional punch updates, and duplicate-key handling.
- Isolated post-fix verification:
  - Coworker check-in, leave creation, and leave balance returned 403; own leave/list/balance paths remained available.
  - Admin delegated attendance remained available.
  - Eight concurrent check-ins produced one HTTP 200, seven HTTP 400 responses, and exactly one stored attendance row.
  - Eight concurrent check-outs produced one HTTP 200 and seven HTTP 400 responses.
  - Unique-index and IST midnight-boundary assertions passed. The disposable database and containers were deleted.
- Production deployment:
  - Created and verified pre-deploy backup `/opt/design-saga-backups/20261012T093311Z`.
  - Deployed the already-tested backend image only; web, PostgreSQL, FerretDB, and Caddy were not restarted.
  - Backend became healthy; site/API returned HTTP 200; production unique index is active; duplicate groups remain zero; recent backend logs contain no critical errors.
- Files changed: `backend/routes/attendance.py`, `backend/core/indexes.py`, `backend/tests/test_attendance_safety.py`.
- Current state: deployed at `c836807` and verified live.
- Rollback: retag `design-saga-backend:rollback-a659939`, recreate only the backend service, and revert `c836807`. The added unique index is compatible with the prior code and need not be removed during an emergency rollback.

### DS-002B: Approval atomicity and attendance-to-payroll integrity

- Symptom/risk:
  - Attendance, leave, and correction reviews used read-then-write transitions, so concurrent reviewers could both succeed or overwrite each other.
  - Leave approval could overwrite an existing worked/punched attendance day with `leave`.
  - Correction review completed the request before safely applying attendance and accepted invalid, cross-day, or reversed timestamps.
  - Concurrent salary submissions could post duplicate journals/runs, and payroll could proceed while attendance, leave, or correction reviews were unresolved.
- Production precondition audit: no pending attendance/late/correction/leave reviews, no leave rows with a real punch, no duplicate payroll period groups, and no existing payroll runs requiring repair.
- Correction:
  - Added atomic review claims and conditional updates for attendance, leave, and correction decisions, with stale-claim recovery and audit preservation.
  - Leave approval now fills only absent/missing/leave days and never overwrites a real punch, worked day, or holiday.
  - Correction requests require valid ISO timestamps on the requested IST business date with checkout after check-in; review applies attendance before finalizing approval.
  - Added a unique sparse `(org_id, period_key)` payroll index and a processing reservation before journal posting.
  - Payroll now blocks unresolved attendance/late/leave/correction reviews and validates expense and cash/bank account types.
- Verification:
  - 17 focused backend tests passed.
  - Candidate backend/frontend images built successfully; frontend emitted only the existing hook warnings.
  - Disposable FerretDB/PostgreSQL integration: six concurrent attendance approvals and four concurrent leave approvals each produced exactly one winner; a worked punch was preserved; one missing leave day was created; correction conflicts remained coherent; eight concurrent salary submissions created exactly one payroll run and one journal; pending correction blocked payment.
  - Temporary QA containers/database were deleted; no production business rows were written.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261012T141305Z` and tagged prior images `rollback-c4df434`.
  - Deployed backend/web at `bbb0442`; PostgreSQL, FerretDB, and Caddy remained running.
  - All services are healthy, site/API return 200, the unique payroll index is active, duplicate period groups remain zero, pending review counts remain zero, and recent logs show no critical errors.
- Files changed: `backend/core/indexes.py`, `backend/routes/attendance.py`, `backend/routes/payroll.py`, `backend/tests/test_attendance_safety.py`, `backend/tests/test_payroll_safety.py`, `frontend/src/pages/Attendance.jsx`.
- Rollback: retag `design-saga-backend:rollback-c4df434` and `design-saga-web:rollback-c4df434`, recreate only backend/web, and revert `bbb0442`. No historical data rewrite occurred.

### DS-009: Compensation and private employee data authorization

- Symptom/risk: users with broad `employees.read` access, including Project Manager and Designer roles, received full employee documents containing salary history, bank details, government IDs, documents, emergency contacts, and performance data. Salary preview/history and another employee's generated payslip also accepted employee-read permission.
- Severity: High. Tenant isolation was intact, but sensitive same-tenant HR/payroll data was exposed beyond intended roles.
- Root cause: employee APIs returned raw database documents and payroll reads reused the broader employee permission.
- Correction:
  - Employee list/detail/create/update responses now project compensation fields by `payroll.read` and private HR fields by `employees.update`.
  - Compensation writes require `payroll.create`; salary history/preview/all-payroll preview and another employee's payslip require `payroll.read`.
  - Employee account metadata requires `users.read`.
  - Attendance summaries/configuration omit compensation without payroll permission.
  - Frontend salary columns, cards, tabs, bank controls, private HR tabs, and employee-account tab follow the corresponding permissions.
- Verification:
  - Project Manager synthetic API tests retained basic employee list/detail access while salary, salary history, bank, Aadhaar/PAN, gender, documents, and performance were absent; salary history/preview/payroll preview/other-user payslip returned 403.
  - Runtime production projection assertion passed after deployment; unauthenticated employee endpoint returns 401.
- Files changed: `backend/server.py`, `backend/routes/attendance.py`, `backend/routes/payroll.py`, `backend/tests/test_financial_read_permissions.py`, `frontend/src/pages/Attendance.jsx`, `frontend/src/pages/EmployeeDetail.jsx`, `frontend/src/pages/Employees.jsx`.
- Current state: deployed at `bbb0442` and verified live.

### DS-004: Linked financial posting integrity and dashboard reversals

- Symptom/risk:
  - Invoice and milestone status handlers could create or reverse accounting entries using document permissions without the matching `finance.create`/`finance.update` permission.
  - The linked income endpoint accepted arbitrary partial/over-payments, wrong account types, both invoice and milestone IDs together, and concurrent duplicate receipts; it could mark the source paid even when the amount did not settle it.
  - Milestone-linked income was mislabeled as generic income, so reversal did not reset the milestone.
  - Paid invoices/milestones could be deleted with financial history removed or left orphaned.
  - The finance dashboard excluded reversed originals but included reversal entries, showing negative monthly income instead of a net-zero reversal.
- Production precondition audit: no current invoices or milestones, no duplicate active receipts, no reversal chains, and zero unbalanced journal entries. No production financial records required repair.
- Correction:
  - Payment transitions now require `finance.create`; reversals require `finance.update`.
  - Linked payments require exactly one valid source, exact full settlement, correct asset/income accounts, and trusted project/client linkage from the source record.
  - Journal entries use a tenant-embedded single-field idempotency key with a unique sparse index, preventing concurrent duplicates while allowing a later payment after a legitimate reversal.
  - Payroll period keys were similarly upgraded to a tenant-embedded single-field unique key after a disposable FerretDB test exposed compound-sparse behavior.
  - Paid sources must be reversed before deletion, and journal history is preserved.
  - Dashboard month P&L and today's collections now include reversal pairs so they net correctly.
- Verification:
  - 20 focused backend tests passed; backend/frontend candidate images built successfully.
  - Disposable integration blocked invoice/milestone payment transitions without finance write permissions, rejected partial settlement and wrong account types, preserved two-entry reversal history, netted dashboard income/collections to zero, and produced one receipt from eight concurrent submissions.
  - A second payment after a full reversal succeeded with exactly one active receipt, confirming the idempotency lifecycle.
  - Temporary QA database, containers, worktree, scripts, and candidate images were deleted.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261012T143132Z`; prior images tagged `rollback-bbb0442`.
  - Deployed backend/web at `8ca840d`; PostgreSQL, FerretDB, and Caddy remained running.
  - All services are healthy; site/API return 200; unauthenticated accounting returns 401; both v2 unique indexes are active; production has zero unbalanced journals; recent logs show no critical errors.
- Files changed: `backend/core/indexes.py`, `backend/routes/accounting.py`, `backend/routes/payroll.py`, `backend/server.py`, `backend/tests/test_accounting_safety.py`, `backend/tests/test_payroll_safety.py`, `frontend/src/pages/Invoices.jsx`.
- Rollback: retag `design-saga-backend:rollback-bbb0442` and `design-saga-web:rollback-bbb0442`, recreate backend/web, and revert `8ca840d`. No production business row was rewritten.

### DS-005: Project, task, file and attachment authorization

- Symptom/risk:
  - Several project, task, follow-up, reminder, project-setting, and file endpoints authenticated the caller but did not enforce module permissions or project membership.
  - A same-tenant user could read or modify a guessed task/project/file identifier even when the frontend hid it.
  - User-supplied attachment links accepted executable or local URL schemes such as `javascript:`, `data:`, and `file:`.
- Production precondition audit: production contained zero files, zero tasks, zero vendors, zero expense claims, zero journal entries, and six employees; no unsafe legacy attachment URLs were found. No data rewrite was required.
- Correction:
  - Added one shared same-tenant visibility policy for projects/tasks, including linked employee identities and organization-wide finance/project roles.
  - Enforced read/create/update permissions and visibility on project lists/details/stages, task CRUD/status/bulk/follow-ups/reminders/settings, and file list/create/delete.
  - Added a shared external URL policy allowing only credential-free HTTP/HTTPS URLs and applied it to project files, task links/attachments, employee/vendor documents, expense receipts, and accounting bills.
- Verification:
  - 18 focused security/accounting tests passed in the candidate image.
  - Disposable-database integration proved assigned staff access, same-tenant outsider denial, HR permission denial, cross-tenant denial, zero-row unauthorized bulk updates, unchanged protected task data, and unsafe URL rejection.
  - Temporary QA database, container, scripts, image, and worktree were deleted.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261013T092427Z`; prior backend tagged `rollback-8ca840d`.
  - Deployed backend at `236d7c7`; web, PostgreSQL, FerretDB, and Caddy were not restarted.
  - Backend and dependent services are healthy; site/API return 200; protected project/task/file endpoints return 401 without authentication; recent logs contain no application errors.
- Files changed: `backend/core/access_control.py`, `backend/core/url_security.py`, `backend/models/accounting.py`, `backend/models/expense.py`, `backend/models/task.py`, `backend/models/vendor.py`, `backend/routes/tasks.py`, `backend/server.py`, `backend/tests/test_access_and_url_safety.py`.
- Rollback: retag `design-saga-backend:rollback-8ca840d`, recreate only the backend service, and revert `236d7c7`. No database schema or business records were changed.

### DS-006: Account-management isolation and Super Admin escalation

- Symptom/risk:
  - A tenant Admin could reset another tenant user's password by guessing a global user ID.
  - Tenant role-assignment, approval, registration, and employee-account paths accepted `SuperAdmin`, while the scoped database treated that role string as a global bypass.
  - The first Google user in an empty database was implicitly promoted, and the repository contained a hard-coded Super Admin fallback email.
  - Bearer-only logout did not revoke the server session; self-service password changes left existing sessions active.
  - The legitimate production platform-owner row retained a legacy `org_id`, making tenant-route context ambiguous.
- Production precondition audit: one explicitly allowlisted platform owner, zero unauthorized Super Admins, zero duplicate email groups, and one legacy tenant-scoped platform-owner row. Production uses local FerretDB, not the exposed Atlas connection.
- Correction:
  - Tenant ownership is verified before password reset; tenant admins cannot assign, create, or approve `SuperAdmin` through any tenant workflow.
  - A role string alone no longer bypasses scoped storage; only an explicit flag or configured allowlist identity does.
  - Removed first-user elevation and all hard-coded Super Admin defaults; production requires `SUPER_ADMIN_EMAILS` configuration.
  - Allowlisted platform owners are reconciled without `org_id` during startup and Google sign-in.
  - Logout revokes cookie and bearer sessions; password changes invalidate every active session.
- Verification:
  - 12 focused auth/permission tests passed.
  - Disposable-database integration blocked cross-tenant reset/role changes and all tenant Super Admin creation paths, kept a forged role tenant-scoped, preserved legitimate platform access, and verified logout/password session revocation.
  - Production post-deploy audit: one authorized platform owner, zero unauthorized or tenant-scoped Super Admins, explicit allowlist active, local FerretDB active.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261013T131412Z`; prior backend tagged `rollback-236d7c7`.
  - Deployed backend at `e086089`; backend is healthy, site/API return 200, protected auth/platform endpoints return 401 without authentication, and recent logs contain no application errors.
- Rollback: retag `design-saga-backend:rollback-236d7c7`, recreate only backend, and revert `e086089`. The platform-owner `org_id` cleanup is correct under either version.

### DS-010: Password-login source rate limiting

- Symptom/risk: password login limited failures per identifier but not per network source. An attacker could rotate through many email or employee IDs and avoid the five-attempt account threshold.
- Correction: hash the client address before storage, count failures per opaque source over the existing 15-minute window, block the thirty-first source failure, bound identifier/password request sizes, and expire attempt records after 24 hours. Existing email, employee-ID, tenant disambiguation, and account-lockout behavior remains unchanged.
- Verification: 8 focused auth tests passed in the candidate image. A disposable PostgreSQL/FerretDB/API stack returned 401 for 30 distinct failed identifiers and 429 for attempt 31, confirmed all identifier/source/TTL indexes, and confirmed stored rows contain only opaque source hashes. All temporary containers, network, database, and test script were removed.
- Files changed: `backend/routes/auth.py`, `backend/models/user.py`, `backend/core/indexes.py`, `backend/tests/test_auth_tenant_safety.py`.
- Database effect: startup creates two non-business indexes on `login_attempts`; no user or ERP business records are rewritten.
- Production deployment: verified backup `/opt/design-saga-backups/20261013T133112Z`; prior backend tagged `rollback-bd3b796`; deployed only backend at `d14fc5d`. Site/API returned 200, unauthenticated auth returned 401, all services are healthy, recent logs contain no application errors, and the identifier/source/TTL indexes are active.
- Rollback: retag `design-saga-backend:rollback-bd3b796`, recreate only backend, and revert `d14fc5d`. The new indexes are compatible with the prior application.

### DS-011: Attendance retry and integrity hardening

- Production evidence: Hiren Panchal's account/employee linkage is valid. His 2026-10-13 site punch matched Oeuvre_2 at 23.2 m with 16.7 m GPS accuracy, was accepted automatically, and checked out successfully. Two older in-fence punches from before `c4df434` were rejected under the former approval behavior; no duplicate, missing-tenant, checkout-without-checkin, or future attendance rows exist.
- Root causes:
  - A rejected punch retained `check_in`, while backend and frontend treated any stored check-in as final for the day. Employees could not retry after reaching an authorized location.
  - Late-arrival review used an unrestricted update, so later or concurrent reviewers could overwrite an earlier decision.
  - Manual attendance silently accepted malformed, cross-day, or reversed timestamps and manager workflows could reference nonexistent employees.
  - Check-in used organization weekly offs even when an employee had an explicit schedule; overlapping pending/approved leave requests were accepted.
- Correction: allow exactly one atomic retry of a rejected/absent punch, archive the rejected attempt in the same attendance record, clear stale checkout/review fields, and show a clear retry state in the UI. Late review now changes only `pending` rows. Manual timestamps and employee references are validated, employee weekly offs take precedence, overlapping active leave is rejected, leave ranges are bounded, and attendance/geofence/config inputs have strict type/range validation.
- Verification: 25 focused attendance/payroll/auth tests passed; backend and frontend production images built successfully. A disposable PostgreSQL/FerretDB/API workflow proved rejected-punch retry/history, duplicate-punch denial, overlapping-leave denial, reversed-time and unknown-employee denial, and exactly one winner from six concurrent late-review requests. Temporary database, containers, network, and scripts were removed.
- Files changed: `backend/models/attendance.py`, `backend/routes/attendance.py`, `backend/tests/test_attendance_safety.py`, `frontend/src/pages/Attendance.jsx`.
- Database effect: no migration or production business-data rewrite; future rejected retries append an embedded audit snapshot to the existing daily row.
- Production deployment:
  - Verified pre-deploy backup `/opt/design-saga-backups/20261014T080312Z`; all SHA-256 checks passed. Prior backend/web images remain tagged `rollback-eae36f1`.
  - Deployed backend and web at `35d07c6`; PostgreSQL, FerretDB, and Caddy were not restarted. Both rebuilt services became healthy and public site/API/auth smoke checks returned 200/200/401 as expected.
  - Hiren Panchal successfully checked in on 2026-10-14 as `site_visit` with `present/auto` status. Production still has zero duplicate employee/date groups, zero checkout-without-check-in rows, and zero future-dated attendance rows.
  - Recent backend/web logs contain no application errors, systemd reports no failed units, protected VPS Caddy changes remain untouched, and disposable candidate images/worktrees were removed.

### DS-012: RBAC override and session lifecycle enforcement

- Root causes:
  - Permission checks and user serializers treated an explicit empty permission list as if no override existed, restoring the role's static defaults. A tenant could not fully revoke a role even though the Team & Roles UI saved the empty override.
  - Legacy routes in `server.py`, including `/auth/me`, used a duplicate account gate that did not check tenant suspension/deactivation. Missing tenant records were also allowed by login and request gates.
- Correction: an attached permission list is now authoritative even when empty. Account approval/activation and secure SuperAdmin-aware tenant existence/status checks are centralized in `ensure_user_access` and reused by password login, modular routes, legacy routes, and `/auth/me`. The Google session cookie now uses `SameSite=Lax` for the same-origin deployment.
- Verification:
  - 37 focused RBAC/auth/attendance/payroll/accounting tests passed; the production backend image built successfully.
  - Disposable PostgreSQL/FerretDB/API testing proved an empty Employee override blocks a default `projects.read` grant, serializers return `permissions: []`, and suspended or missing tenants receive 403. Disposable containers, network, database, image, and worktree were removed.
  - Production had zero empty permission overrides before deployment, so no current user was unexpectedly locked out.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261014T081519Z`; all SHA-256 checks passed. Prior backend remains tagged `rollback-b20cb9c`.
  - Deployed backend only at `767bfee`; web, PostgreSQL, FerretDB, and Caddy were not restarted. Public site/API/auth smoke checks returned 200/200/401, backend is healthy, systemd has no failed units, and logs contain no application errors.
  - A temporary production QA org/user/session/override proved active `/auth/me` 200 with an empty permission list, project access 403, suspended tenant 403, and missing tenant 403. Every QA row was deleted and a zero-row cleanup assertion passed.
- Files changed: `backend/core/deps.py`, `backend/core/rbac.py`, `backend/routes/auth.py`, `backend/server.py`, `backend/tests/test_rbac_session_safety.py`.
- Database effect: no migration or permanent business-data changes.

### DS-013: Secondary-surface visibility enforcement

- Root causes:
  - Global search applied tenant and module permission checks but skipped the assignment/team visibility rules used by project and task endpoints.
  - Comments required authentication only, so a user could list or add comments against a guessed hidden project/task/entity ID.
  - The calendar feed exposed all tenant tasks, project deadlines, approved employee leave names, and payment milestone amounts to any role with `calendar.read`.
  - Calendar attendee IDs were not tenant-validated before notification fan-out, and unbounded search/date inputs allowed unnecessarily expensive requests.
- Correction: search now merges the shared project/task visibility queries and uses the correct purchase-order permission. Comment list/create/delete validates the target entity, module read permission, and project/task visibility. Calendar sources are independently permission-gated; tasks/projects use shared visibility, ordinary employees see only their own approved leave, milestone amounts require invoice/finance access, and direct notification recipients must belong to the creator's tenant. Search and calendar ranges are bounded and validated.
- Verification:
  - 50 focused visibility/RBAC/auth/attendance/payroll/accounting tests passed; the production backend image built successfully.
  - A disposable two-tenant PostgreSQL/FerretDB/API workflow proved hidden project/task search results are absent, hidden comments return 404, calendar returns only the employee's visible task/project and own leave, milestones remain hidden without financial permission, oversized ranges return 400, a foreign-tenant attendee receives zero notifications, and vendor-only search cannot reveal purchase orders.
  - The disposable database, containers, network, candidate image, and worktree were removed; production business data was not used or changed.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261014T082426Z`; all SHA-256 checks passed. Prior backend remains tagged `rollback-1f891dc`.
  - Deployed backend only at `cf82c92`; web, PostgreSQL, FerretDB, and Caddy were not restarted. Public site/API/auth smoke checks returned 200/200/401, backend is healthy, systemd has no failed units, protected Caddy changes remain untouched, and recent logs contain no application errors.
- Files changed: `backend/routes/calendar.py`, `backend/routes/comments.py`, `backend/routes/search.py`, `backend/tests/test_visibility_surfaces.py`.
- Database effect: no migration or business-data rewrite.

### DS-014: Repair release integrity and concurrency gates

- Root causes: scheduled work bypassed the shared job lock and used the wrong tenant field; audit verification could miss a deleted tail and did not require a production HMAC key; password-reset throttling missed the direct user route; several finance workflows used UTC calendar dates; optional compound sparse indexes could reject normal records without idempotency/GSTIN values; and employee numbering used a racy count-based allocator without a unique counter invariant.
- Correction: route both recurring jobs through persisted single-run locks and health state; require an audit HMAC key in production and verify stored chain head/count; cover every reset-password route; centralize business dates on `BUSINESS_TIMEZONE`; use normalized single-field sparse keys for optional uniqueness; add unique scheduler/audit/business indexes; and allocate employee/document numbers through a unique per-tenant atomic counter.
- Candidate verification at `b28a373`: 62 deterministic backend tests passed; backend and frontend production images built; a disposable PostgreSQL/FerretDB workflow passed tenant-admin and employee-ID login, first-attempt authorized site attendance, expense retry, invoice terminal-state guards, PO/GRN over-receipt rejection, concurrent EMI protection, and cross-tenant 404 checks. Eight concurrent employee creates produced eight unique IDs and one counter row. Optional-key tests proved multiple keyless expenses/vendors/bills/payments remain valid while keyed retries remain single-write.
- Production preflight: six employee rows have IDs; zero duplicate groups were found for employee IDs, counters, audit chains, job state, expense/payment request IDs, vendor bill numbers, GSTINs, or invoice numbers, including case-folded identity checks.
- Files changed: `backend/core/audit.py`, `backend/core/helpers.py`, `backend/core/http_security.py`, `backend/core/indexes.py`, `backend/core/jobs.py`, `backend/server.py`, finance/notification route modules, `backend/tests/test_repair_release_safety.py`, `.env.example`, and `docker-compose.yml`.
- Database effect: startup creates/promotes indexes and initializes job state. No historical business rows are rewritten.
- Production deployment: verified backup `/opt/design-saga-backups/20261015T132809Z`; rollback images tagged `rollback-831bb19`; production audit HMAC and IST business timezone configured; backend/web replaced while PostgreSQL, FerretDB, and Caddy remained running. Site/API returned 200, unauthenticated `/api/auth/me` returned 401, all services became healthy, all 11 required unique indexes are active, and both scheduled jobs completed successfully on their first attempt with zero failures. Protected VPS Caddy changes remain untouched.
- Credential hygiene: removed obsolete test scripts containing historical login strings. The named demo tenant accounts do not exist in production and the historical Super Admin string does not match the live password. Previously exposed external MongoDB/viewer credentials still require rotation at their provider.

### DS-015: Runtime dependency, container and monitoring hardening

- Root causes: production dependency pins included known-vulnerable FastAPI/Starlette, PyMongo/Motor and multipart versions; the frontend build was not lockfile-reproducible; the Nginx 1.27 runtime contained 43 fixed high/critical OS findings; backend ran without a non-root/read-only boundary; download filenames were assembled inconsistently; and production had no recurring local health/backup/disk monitor.
- Correction: upgraded the Python runtime dependencies and replaced Passlib with bcrypt's compatible native API; committed the npm lockfile and switched builds to `npm ci`; upgraded the final Nginx runtime to 1.31 Alpine; centralized safe RFC 5987 download headers; ran backend as UID/GID 10001 with a read-only root filesystem, writable `/tmp`, dropped capabilities and no-new-privileges; and installed a deduplicating five-minute systemd monitor for all five containers, public HTTP, disk usage, backup age and backup checksums.
- Verification: 53 focused backend tests passed. A disposable two-tenant workflow passed Super Admin, tenant-owner and employee-ID login, first-attempt authorized attendance for Hiren Panchal, duplicate-punch rejection and cross-tenant denial. Exact candidate containers passed startup and read-only/non-root checks. `pip-audit` and both final runtime-image Trivy scans report zero known high/critical findings; the production npm runtime tree reports zero vulnerabilities. The legacy CRA build-only tree still reports findings and remains a modernization item.
- Production deployment: verified backup `/opt/design-saga-backups/20261015T190147Z` passed every SHA-256 check and `pg_restore -l`; deployed commit `bad2f103ce3c47df5b21608e5ca62191b06fcf17` to backend/web only; PostgreSQL, FerretDB and Caddy retained their uptime. Site/API/auth checks returned 200/200/401, all containers are healthy, both scheduled jobs succeeded with zero failures, the audit chain verifies, systemd has zero failed units, and the protected VPS Caddy changes remain untouched.
- Database effect: startup reconciled one existing platform-owner/user document and ensured indexes; no ERP business records were migrated or deleted. Rollback images are `design-saga-backend:rollback-bf9745c-hardening` and `design-saga-web:rollback-bf9745c-hardening`.
- Remaining external operations: configure `DESIGN_SAGA_ALERT_WEBHOOK_URL` for off-host notifications, add encrypted off-server backup replication, and rotate the previously exposed Atlas/viewer credentials at their providers.

## Deployment Safety

### DS-019: Attendance project selection for authorized sites

- Root cause: the Attendance page reused the general `/projects` list, whose project-team visibility correctly hid projects from unassigned employees. Hiren Panchal is in the `Site Execution` department but was not a project team member, leaving his site-project selector empty despite his cross-site supervision duties.
- Correction: added an attendance-only project-options endpoint that returns only project `id` and `name`. Site Supervisor and Site Execution/Site Supervision employees may choose any active project for a punch; ordinary employees remain limited to assigned projects or active authorized site fences, and archived projects remain hidden. Check-in and geo-check reject unavailable or unauthorized project IDs without weakening normal project visibility.
- Verification: production data identifies Hiren as `Site Execution`; the candidate rule gives him all active attendance project choices while excluding archived projects. Focused attendance, payroll, authentication and tenant-scope tests pass; frontend lint/build and diff checks pass.
- Database effect: none. No attendance, employee, project, geofence, or business record was changed.

### DS-018: Accounting all-time, reversal recovery, and deployment resilience

- Root causes: accounting views treated a missing financial-year filter as the current FY, so "All time" omitted older transactions; reversal recovery had no audit-safe user action; vendor bill posting could leave accounts-payable activity disconnected; and the VPS deployment/monitor scripts depended on the host's failing outbound IPv4 path.
- Correction: added an explicit `fy=all` contract across Income, Expenses, Daybook, ledgers, reports and exports; added paginated transaction history/detail; introduced an idempotent `undo-reversal` operation that posts a reinstatement instead of deleting audit history; tightened accounting/vendor posting invariants; and made trusted image builds use a configurable host build network with direct container smoke checks.
- Verification: 57 focused accounting, vendor, attachment, RBAC/session, attendance and Google Calendar tests passed, plus frontend lint/build and Python compilation. Production contains four journal entries spanning 22/11/2025 through 05/08/2026, proving the all-time range crosses financial years.
- Ritesh Soni entry: `je_9201f35ac20e`, dated 22/11/2025 for Rs 10,000, remains present as an income journal. Production contains zero linked or global reversal entries, so no financial row was deleted or altered.
- Production deployment: verified backups `/opt/design-saga-backups/20261021T071920Z` and `/opt/design-saga-backups/20261021T072737Z` passed all SHA-256 checks. Backend and web were deployed at `cddc2dad4e9538ad033407c4d0c1d285ff97f8e6`; PostgreSQL, FerretDB and Caddy retained uptime. All five containers are healthy, site/API/auth return 200/200/401, UFW is active, SSH key access works over IPv6, and VPS-only Caddy changes remain untouched.
- VPS networking: persistent IPv6 DNS was added because provider-side outbound IPv4 is unavailable. The independent off-server backup and attendance-evidence jobs still require the provider to restore outbound IPv4 access to their IPv4-only source; same-host Design Saga backups remain current and verified.
- Files changed: accounting/vendor backend routes and models, accounting frontend views, focused tests, `deploy/update-production.sh`, and `deploy/monitor.sh`.
- Database effect: no migration, deletion, reversal, reinstatement, or permanent QA data was created.

### DS-007: Safe Git-driven production updates

- Symptom/risk: the VPS `post-merge` hook rebuilt backend and web and ran unrestricted `docker compose up -d` after every merge, including documentation-only changes. It performed no pre-deploy backup, changed-service detection, readiness rollback, or infrastructure-change gate.
- Correction: added tracked `deploy/update-production.sh` with a deployment lock, revision diff classification, documentation-only skip, automatic refusal for Compose/Caddy infrastructure changes, verified pre-deploy backup, affected-service-only build/recreate, health wait, HTTP smoke checks, and automatic image rollback.
- VPS configuration: replaced the ad-hoc hook with a minimal hook that executes the tracked updater. Existing VPS-only Caddy modifications remain untouched.
- Verification: shell syntax passed; the installer merge and explicit updater run identified no runtime changes and skipped all container work. A docs-only end-to-end post-merge test is recorded in the following documentation commit.

### DS-016: Tenant scope and lifecycle completion

- Root causes: the scoped database merge allowed a caller-supplied `org_id` to win over the trusted request scope; several secondary attendance, task, master-data and vendor-rating lookups used global queries; portal/chat/AI message ownership was incomplete; tenant purge omitted business, integration, session, login-attempt and audit-chain records; and orphaned organization logos remained retrievable.
- Correction: trusted scope now overwrites conflicting tenant fields; affected lookup/update paths are tenant-bound; new portal/chat/AI records carry ownership with legacy ownership inferred safely at startup; tenant purge covers 52 explicit tenant-owned collections plus sessions, normalized login identities and audit-chain state; deleted/inactive tenant logos return 404; supporting indexes were added.
- Verification: 88 local-safe backend tests and Python compilation passed. The exact `7cf22c1` image started against disposable PostgreSQL/FerretDB; a two-tenant workflow proved scope override resistance, all 52 purge collection classes, session/login cleanup and the three new indexes. Temporary containers, volume, image and worktree were deleted.
- Production precondition: 46 attendance, 420 master-data and 20 notification records all had valid tenant ownership; tasks, ratings, chat and AI collections were empty. No production business-data rewrite was required.
- Production deployment: backup `/opt/design-saga-backups/20261016T211613Z` passed every SHA-256 check; prior backend is tagged `rollback-be360c8`; only backend was recreated. Site/API returned 200, protected auth/platform endpoints returned 401, all services and the local monitor passed, affected collections retained zero missing/unknown tenant ownership, indexes are active, and recent backend logs contain no errors. VPS-only Caddy changes remain untouched.
- Files changed: tenant scope/index modules, attendance/master-data/organization/platform/task/vendor routes, legacy server message handling, focused tests, and planning evidence under `docs/planning`.

### DS-017: Public share-link tenant isolation

- Root cause: public client-portal and shared-invoice routes resolved a random project token globally, but then loaded child records through an unscoped context using only `project_id` or invoice `id`. Globally random IDs made collision unlikely but did not provide a tenant-isolation guarantee. Suspended tenant share links also remained available.
- Correction: share tokens must match the application-generated format and resolve to an active, unsuspended tenant; every public task, file, invoice, milestone, PDF and message operation is bound to both project and owner `org_id`.
- Verification: all 15 production project share tokens were format-compatible. Ninety-two local-safe backend tests passed. A disposable two-tenant HTTP workflow deliberately reused project and invoice IDs and proved the token exposed only its tenant, wrote its message to that tenant, rendered its invoice, and returned 404 after tenant suspension. Temporary containers, volume, image and worktree were removed.
- Production deployment: backup `/opt/design-saga-backups/20261016T212145Z` passed all checksums; prior backend remains available as a rollback image; backend-only deployment completed at `56e465b`. An existing production share link returned its expected 200 response, site/API/auth smoke checks passed, every service and the local monitor are healthy, and recent logs contain no errors. Caddy changes remain untouched.
- Files changed: `backend/server.py`, `backend/tests/test_public_share_safety.py`.

### OPS-001: VPS access, firewall, and backup health

- SSH: installed `/etc/ssh/sshd_config.d/00-design-saga-hardening.conf`; password and keyboard-interactive authentication are disabled, root is limited to public-key login, `MaxAuthTries` is 3, and `LoginGraceTime` is 30 seconds. `sshd -t`, daemon reload, and fresh key-only connections passed before and after firewall activation.
- Firewall: enabled UFW with default deny inbound and only 22/tcp, 80/tcp, 443/tcp, and 443/udp allowed for IPv4 and IPv6. The public site and API remained HTTP 200 and every Compose service remained healthy.
- Backup health: `design-saga-backup.timer` is enabled and its latest scheduled service run completed successfully. The newest archive `/opt/design-saga-backups/20261013T131412Z` passed every SHA-256 check and `pg_restore -l` parsed its 24.5 MB database dump successfully.
- Service health: cleared the failed-state marker for the obsolete six-day-old transient `tanvika-clean-reset.service`; systemd now reports zero failed units. No application service or business data was changed.
- Rollback evidence: original SSH configuration is retained under `/root/ssh-config-backup-20261013T131903Z`. Firewall rules can be inspected with `ufw status verbose`; keep an established SSH session open for any future SSH/firewall change.
- Remaining operations risk: same-host backups do not protect against VPS loss. Add encrypted off-server replication, backup-failure/uptime/disk alerts, and a documented recovery-time/recovery-point target.

- Before any production repair: capture database backup, record image/commit rollback target, verify the exact Compose service affected, and preserve the VPS Caddy modifications.
- Prefer service-specific rebuild/restart after testing. Do not run `docker compose down -v`.
- Current rollback baseline: backend/web images tagged `rollback-bf9745c-hardening`; the newest verified database/config archive is `/opt/design-saga-backups/20261015T190147Z`.

## Next Action

Rotate the exposed external MongoDB/viewer credentials, configure an external alert webhook and encrypted off-server backups, modernize the legacy CRA build toolchain, and continue the remaining route-by-route business/security audits in `PRODUCTION-RISK-REGISTER.md`.
