# Design Saga Repair Tracker

Last updated: 2026-10-12 (Asia/Calcutta)

## Current Checkpoint

- Local checkout: `production`; application checkpoint `8ca840d` is committed and pushed to GitHub `main` and `production`.
- Production checkout: `/opt/design-saga-git`, `production` at `8ca840d`.
- Production working tree: protected external changes in `deploy/Caddyfile` plus `deploy/Caddyfile.pre-tanvika-20261003T154040Z`. The diff adds `gamaa.tech` routes to services outside this Compose project. Do not overwrite, reset, or include these changes in Design Saga deployments.
- Live URL/API: `https://gamaa.in`, API health returned `{"service":"Design Saga API","status":"ok"}`.
- Services: Caddy, web, backend, FerretDB, and PostgreSQL are running; health-enabled services are healthy.
- VPS baseline: 3.8 GiB RAM (2.5 GiB available), 2 GiB swap, root disk 45% used, low load at inspection.
- Current action: DS-001 through DS-004 and DS-009 are deployed and verified live. Continue with DS-005 file/attachment security and persistence.

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
| File storage | URL metadata and local/generated documents; durable object storage remains unverified | Partial/unverified |
| Reverse proxy/TLS | Caddy with automatic HTTPS; shared VPS routing file | Healthy; production file has protected external edits |
| Deployment | Docker Compose; merge/rebase hooks invoke `deploy/redeploy.sh` | Confirmed from docs/history; automatic hook behavior must account for protected Caddy edits |
| Backups | Dedicated daily PostgreSQL/FerretDB archive with checksums, catalogue validation, seven-day retention, and tested isolated restore | Active on VPS; same-host storage remains a disaster-recovery limitation |

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
| DS-003 | High | Establish a validated backup and restore path for Design Saga PostgreSQL/FerretDB data and deployment state | Fixed and active; offsite copy remains a follow-up |
| DS-004 | High | Reconcile dashboard revenue/outstanding figures with journal/invoice sources and permission boundaries | Fixed, deployed, and verified live |
| DS-005 | Medium | Audit file/attachment persistence, upload validation, download authorization, and tenant isolation | Queued |
| DS-006 | Medium | Verify Client role compatibility, then remove it from team-management choices without breaking dependent records | Queued |
| DS-007 | Medium | Trace approved architecture workflow from lead through accounting with synthetic data | Queued |
| DS-008 | Medium | Measure endpoint/page performance and inspect indexes/N+1/pagination before optimizing | Queued |
| DS-009 | High | Employee/payroll endpoints expose compensation, bank, and private HR data through broad employee-read permission | Fixed, deployed, and verified live |

## Issue Log

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

## Deployment Safety

- Before any production repair: capture database backup, record image/commit rollback target, verify the exact Compose service affected, and preserve the VPS Caddy modifications.
- Prefer service-specific rebuild/restart after testing. Do not run `docker compose down -v`.
- Rollback baseline for this pass: Git commit `dbf6595` and current running backend/web image IDs recorded by `docker compose images` on 2026-10-12.

## Next Action

Install the tracked safe-update script as the VPS post-merge hook, rotate the exposed external MongoDB/viewer credentials, then continue the route-by-route IDOR audit listed in `PRODUCTION-RISK-REGISTER.md`.
