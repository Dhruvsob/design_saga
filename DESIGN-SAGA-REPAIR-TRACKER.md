# Design Saga Repair Tracker

Last updated: 2026-10-12 (Asia/Calcutta)

## Current Checkpoint

- Local checkout: `production`; repair implementation commit `1a1903c` plus this tracker checkpoint, eight commits ahead of `origin/main`.
- Production checkout: `/opt/design-saga-git`, `production` at `dbf6595`.
- Production working tree: protected external changes in `deploy/Caddyfile` plus `deploy/Caddyfile.pre-tanvika-20261003T154040Z`. The diff adds `gamaa.tech` routes to services outside this Compose project. Do not overwrite, reset, or include these changes in Design Saga deployments.
- Live URL/API: `https://gamaa.in`, API health returned `{"service":"Design Saga API","status":"ok"}`.
- Services: Caddy, web, backend, FerretDB, and PostgreSQL are running; health-enabled services are healthy.
- VPS baseline: 3.8 GiB RAM (2.5 GiB available), 2 GiB swap, root disk 45% used, low load at inspection.
- Current action: DS-001 is implemented and isolated-tested. No production change is authorized by this tracker entry; deployment awaits an approved maintenance window.

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
| Backups | No current backup schedule or restore-test evidence found yet | High-priority verification gap |

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
| DS-001 | High | Server-side invoice/dashboard financial-read authorization bypass | Implemented and isolated-tested; awaiting production deployment approval |
| DS-002 | High | Verify attendance idempotency, timezone boundary, approval audit, and payroll consistency end to end | Queued |
| DS-003 | High | Verify backup schedule, encrypted retention, and tested restore path for PostgreSQL/FerretDB data and Caddy state | Queued |
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
- Current state: implemented and isolated-tested at `1a1903c`; awaiting production backup and deployment approval.
- Production impact: none. Not deployed; live containers and database unchanged.
- Rollback: revert the DS-001 commit. No database migration or data rewrite is involved.

## Deployment Safety

- Before any production repair: capture database backup, record image/commit rollback target, verify the exact Compose service affected, and preserve the VPS Caddy modifications.
- Prefer service-specific rebuild/restart after testing. Do not run `docker compose down -v`.
- Rollback baseline for this pass: Git commit `dbf6595` and current running backend/web image IDs recorded by `docker compose images` on 2026-10-12.

## Next Action

With approval for a brief maintenance window, back up production data, preserve the protected Caddy changes, and deploy commit `1a1903c` using service-specific backend/web rebuilds and restarts. Run post-deployment permission and health checks, then continue with DS-002.
