# Design Saga Repair Tracker

Last updated: 2026-10-12 (Asia/Calcutta)

## Current Checkpoint

- Local checkout: `production`; DS-001 implementation `1a1903c`, verification checkpoint `a659939`, and backup implementation `1bafdea`.
- Production checkout: `/opt/design-saga-git`, `production` at `1bafdea`.
- Production working tree: protected external changes in `deploy/Caddyfile` plus `deploy/Caddyfile.pre-tanvika-20261003T154040Z`. The diff adds `gamaa.tech` routes to services outside this Compose project. Do not overwrite, reset, or include these changes in Design Saga deployments.
- Live URL/API: `https://gamaa.in`, API health returned `{"service":"Design Saga API","status":"ok"}`.
- Services: Caddy, web, backend, FerretDB, and PostgreSQL are running; health-enabled services are healthy.
- VPS baseline: 3.8 GiB RAM (2.5 GiB available), 2 GiB swap, root disk 45% used, low load at inspection.
- Current action: DS-001 is deployed and verified live. DS-003 dedicated backups and recovery validation are deployed. Continue with DS-002 attendance verification.

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
| Attendance | Partial verification | GPS, holidays, policy and monthly-grid tests exist; complete current check-in/out/payroll chain still needs focused verification |
| Leads → quotations/BOQ → projects | Partial | Implemented and prior module tests exist; full current conversion chain unverified |
| Projects → tasks/assignments | Previously tested, needs currency check | Historical task visibility and assignment evidence exists |
| Vendors/procurement | Partial | Vendor, PO and accounting tests exist; current end-to-end flow unverified |
| Invoices/receipts/accounting | Previously tested, targeted recheck needed | Posting/reversal and reporting fixes documented; current permission and reconciliation sweep pending |
| Payroll/expenses | Partial | Implemented with prior tests; current attendance-to-payroll reconciliation unverified |
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
| DS-002 | High | Verify attendance idempotency, timezone boundary, approval audit, and payroll consistency end to end | Queued |
| DS-003 | High | Establish a validated backup and restore path for Design Saga PostgreSQL/FerretDB data and deployment state | Fixed and active; offsite copy remains a follow-up |
| DS-004 | High | Reconcile dashboard revenue/outstanding figures with journal/invoice sources and permission boundaries | Queued |
| DS-005 | Medium | Audit file/attachment persistence, upload validation, download authorization, and tenant isolation | Queued |
| DS-006 | Medium | Verify Client role compatibility, then remove it from team-management choices without breaking dependent records | Queued |
| DS-007 | Medium | Trace approved architecture workflow from lead through accounting with synthetic data | Queued |
| DS-008 | Medium | Measure endpoint/page performance and inspect indexes/N+1/pagination before optimizing | Queued |

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

## Deployment Safety

- Before any production repair: capture database backup, record image/commit rollback target, verify the exact Compose service affected, and preserve the VPS Caddy modifications.
- Prefer service-specific rebuild/restart after testing. Do not run `docker compose down -v`.
- Rollback baseline for this pass: Git commit `dbf6595` and current running backend/web image IDs recorded by `docker compose images` on 2026-10-12.

## Next Action

Begin DS-002 with targeted attendance endpoint/test review: establish idempotency, configured business timezone/date behavior, approval audit fields, and payroll-input consistency before running isolated synthetic transactions.
