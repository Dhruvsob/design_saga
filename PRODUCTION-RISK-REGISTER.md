# Design Saga ERP Production Risk Register

Last updated: 2026-10-25 (Asia/Kolkata)

This is a living production checklist, not a claim that unknown defects do not exist.
`Fixed` means code and production behavior were verified. `Open` means remediation or
evidence is still required. `Audit` means no defect is confirmed, but the area has not
yet received sufficient adversarial testing.

## P0 - Immediate Security and Availability

| Area | Risk / required evidence | Status |
|---|---|---|
| Tenant login | Super Admin, tenant owner, email, and employee ID must use one authentication system and resolve the correct tenant/role | Fixed and deployed |
| Tenant isolation | Every business query must enforce `org_id`; cross-tenant IDs must return no data | Scoped business database, secondary lookup repairs, tenant cleanup, orphan-account fail-closed lifecycle gate, session-scoped platform impersonation and focused isolation tests are in place; route-by-route adversarial coverage continues |
| Project/task/file IDOR | Same-tenant users must not read or modify guessed projects, tasks, follow-ups, reminders, settings, or file links | Fixed, tested, and deployed at `236d7c7` |
| Attachment URL injection | Reject `javascript:`, `data:`, `file:`, credential-bearing, malformed, and control-character URLs | Fixed, tested, and deployed at `236d7c7` |
| Exposed credentials | Rotate the MongoDB Atlas password previously pasted into chat and revoke the temporary Mongo viewer token; confirm neither is used by production | Open, external account action required |
| Super Admin allowlist | Require an explicit production identity, prevent tenant role escalation, and keep platform owners outside tenant scope | Fixed and deployed at `e086089` |
| SSH access | Key-only login, disabled password/root remote login where operationally safe, restricted users, firewall, brute-force protection | Fixed baseline: passwords and keyboard-interactive auth disabled, root is key-only, three-attempt/30-second limits active; dedicated non-root operator and fail2ban remain defense-in-depth follow-ups |
| Host firewall | Deny unsolicited inbound traffic while preserving SSH, HTTP, HTTPS, and HTTP/3 | Fixed: UFW default-deny is active with only 22/tcp, 80/tcp, 443/tcp, and 443/udp allowed for IPv4/IPv6 |
| Backups | Encrypted automated database backups, off-server retention, restore drill, documented RPO/RTO | Partial: daily checksummed archive, repeatable isolated restore validation and engineering RPO/RTO are documented; off-server encrypted retention remains open |
| Disaster rollback | Known image tags, database compatibility, service-specific rollback, preserved Caddy configuration | Fixed baseline: repeatable restore drill and incident runbook verified against the 2026-10-24 production backup; full provider-loss exercise remains dependent on off-server replication |
| Monitoring | Uptime, container health, disk, memory, CPU, database capacity, TLS expiry, 5xx rate and backup-failure alerts | Partial: five-minute container/site/API/disk/memory/load/database-capacity/TLS/backup monitor is active; repeated backend 5xx detection is implemented and pending deployment; external notification delivery remains blocked by Hostinger outbound IPv4 resolution |

## P1 - Authorization and Data Protection

| Area | Risk / required evidence | Status |
|---|---|---|
| Employee privacy | Salary, bank, government IDs, private documents, performance and payslips restricted by HR/payroll permissions | Fixed and deployed |
| Attendance identity | Employees may check in/out only for themselves except explicit managers; geofence/site authorization enforced; rejected punches can be retried without losing audit history | Fixed, deployed, and verified live |
| Attendance data integrity | Validate geo/type/schedule inputs, manual punch dates/order, employee references, overlapping leave, and employee-specific weekly offs | Fixed, deployed, and verified live |
| Approval races | Concurrent attendance, leave, correction, and late-arrival approvals must produce one final decision | Fixed, deployed, and verified live |
| Payroll integrity | One payroll per period, unresolved attendance blocks payroll, correct account types and idempotent posting | Fixed; interrupted finalization recovery tested locally, deployment pending |
| Financial posting | Exact linked settlement, correct accounts, atomic idempotency, reversible immutable journal history | Fixed; interrupted receipt/loan and commission-allocation recovery tested locally, deployment pending |
| Remaining module IDOR | Adversarially test clients, leads, quotations, vendors, purchase orders, expenses, loans, holidays, comments, calendar, notifications and search | Project/task/file/search/comments/calendar/notification/public-share fixed; vendor financial/privacy and linked project/task visibility fixed; quotation and lead composite-create permission boundaries fixed; expense APIs now enforce custom-role permissions before claimant/approver visibility; ambiguous task-user/vendor name fallbacks fail closed; purchase/GRN/search/comment/audit reads follow visible projects; remaining route audit continues |
| Role overrides | Test empty/custom permission sets, protected roles, privilege escalation, role changes during active sessions | Empty/custom overrides are fail-closed; tenant user creation, approval, employee-account creation and role changes cannot mint a platform `SuperAdmin`; broader route audit continues |
| Session lifecycle | Expiry, logout invalidation, password-change revocation, inactive/suspended tenant revocation, stolen-token resistance | Lifecycle gates fixed; password/reset/reassignment/offboarding and tenant suspension/deactivation revoke sessions; SuperAdmin impersonation is isolated to one session; production uses cookie-only sessions |
| CSRF and cookies | Confirm `Secure`, `HttpOnly`, appropriate `SameSite`, origin checks and no state-changing GET routes | Secure HttpOnly SameSite=Lax cookies, unsafe-method Origin/Referer enforcement and a production fail-closed explicit-CORS guard are covered; ongoing route audit remains |
| Rate limiting | Login, password reset, OTP, public portal, search, AI and expensive exports need per-IP/account limits | Fixed single-worker baseline for auth/reset, portal, branding, search, AI, exports and uploads; move buckets to shared storage before adding workers |
| Secrets management | No secrets in Git/images/logs; least-privilege environment access; rotation procedure and secret inventory | Current tree audited: historical account/password pairs removed from scripts/reports, test harnesses require environment credentials, production hashes do not match the removed passwords, and structured log redaction is active; full Git-history rewrite and external credential rotation remain operations actions |
| Stored XSS | Validate/sanitize notes, descriptions, comments, names, SVG/media and any rich-text rendering | Baseline fixed: React text rendering, no `dangerouslySetInnerHTML`, shared external-URL validation, defensive rendering of legacy links, response-time branding sanitization, raster-only logo upload/proxy paths, and tenant-owned branding validation; future rich-text changes require continuing review |
| File handling | Authenticated object access, signed expiry, ownership, size/type limits, filename safety, malware scanning and deletion lifecycle | Project/vendor binary uploads are tenant/permission scoped, rate limited, signature validated, capped at 15 MB/file, 512 MB/tenant and 5 GB/server, served with safe headers, deleted with their records and included in deduplicated checksummed backups. Server-side malware scanning and orphan reconciliation remain defense-in-depth follow-ups |
| Tenant deletion lifecycle | Purge all tenant business/integration data, sessions, login identifiers and per-tenant audit state without touching global records | Fixed, disposable-database tested and deployed at `7cf22c1`; physical object-store garbage collection remains an operations follow-up |
| Audit logs | Tamper-resistant records for auth, permissions, payroll, finance, approvals, exports and destructive actions | Audit |

## P1 - Business Integrity and Concurrency

| Area | Risk / required evidence | Status |
|---|---|---|
| Employee/user link | Employee creation must create/link exactly one active authentication user where requested | Tenant-bound account lookup, safe offboarding, active-session revocation and duplicate login-ID prevention are covered; production identity preflight is clean and user IDs are uniquely indexed |
| Invoice lifecycle | Draft/issued/paid/reversed/deleted transitions and permissions | Fixed and deployed: accounting-aware status transitions are idempotent, permission checked and reversal based |
| Invoice accrual / Accounts Receivable | Issued invoices must not leave AR at zero; payment must settle AR without double-counting revenue | Fixed and verified live: issue posts A/R against revenue/GST, payment settles A/R, and rollback uses balanced reversals; no historical migration was required |
| Capital and non-operating money | Owner capital/drawings, investments, advances and private loans must never be misclassified as operating income/expense | Fixed, deployed and verified live through reversible owner capital, gold, advance and repayment tests |
| Chart of Accounts integrity | Current balances, unique names/codes, safe edits and non-destructive deactivation | Fixed and deployed; live current balances verified, future duplicate codes rejected, exact unused duplicates cleaned after backup, and audit chains pass |
| Expense claims | Duplicate submission, concurrent approval/reimbursement, receipt ownership and account validation | Idempotency, duplicate submission, claimant visibility, approval concurrency, receipt URLs and reimbursement accounts fixed/tested; broader workflow QA continues |
| Purchase orders/GRN | Approval races, quantity over-receipt, duplicate bills/payments and immutable history | Status transitions, cancellation dependencies, over-receipt and bill/payment idempotency fixed/tested; broader workflow QA continues |
| Loans/EMI | Concurrent payment/prepayment, balance floor, journal reconciliation and deletion rules | EMI/prepayment locking, balance floors, journal cardinality, request idempotency and interrupted-write recovery fixed/tested; deployment pending |
| Vendor commissions | Duplicate settlement, reversal, tax/account validation and tenant isolation | Stable request idempotency, partial reversal allocation and excess-as-liability accounting fixed/tested; tax-policy review remains and deployment is pending |
| Commission visibility | Direct/excess receipts must reconcile across journals, vendor ledger and commission dashboard without double counting allocations | Fixed and deployed at `3b95ca1`; live three-receipt/₹21,000 production reconciliation passes and reversed settlement journals are excluded |
| Project deletion | Preserve dependent financial/history records; archive instead of destructive cascades | Dependency matrix blocks deletion when operational, attendance or financial history exists; archive path is available and tested |
| Unique identities | Case-insensitive email, employee ID, tenant slug, invoice number and vendor tax identifiers | User ID, tenant employee counter, employee/document counters and key finance identifiers are protected; production duplicate preflight is clean; broader normalization audit continues |
| Time zones | All business dates use Asia/Kolkata while stored timestamps remain UTC; test midnight/month/year boundaries | Shared IST business-date helper applied to audited modules; boundary regression test passes |
| Money precision | Decimal-safe calculations, rounding policy, GST/TDS, currency and reconciliation | Non-finite, zero/negative and out-of-range financial inputs are rejected before persistence; Decimal migration and tax-rounding policy audit remain open |

## P2 - Reliability, DevOps and Operations

| Area | Risk / required evidence | Status |
|---|---|---|
| Database indexes | Index every tenant/filter/uniqueness path; monitor slow queries and index build failures | Integrity plus vendor-rating/chat/AI tenant indexes fixed/tested; performance/slow-query audit remains open |
| Database capacity | Connection limits, timeouts, pool sizing, storage growth, vacuum/maintenance and corruption alerts | Audit |
| Container hardening | Non-root runtime, read-only filesystem where possible, dropped capabilities, resource limits and health checks | Fixed baseline: backend is non-root/read-only with all capabilities dropped; backend/web use no-new-privileges, init and health checks |
| Dependency security | Automated Python/Node/container CVE scan, lockfiles, update policy and license review | Partial: Python and Node production dependency scans are clean and enforced in CI; npm lockfile is committed; final-image automation and license review remain open |
| CI/CD | Build, lint, unit, integration, migration, security scan, immutable artifact and approval gate before production | Partial: GitHub quality gate runs focused backend security/integrity tests (including password/PIN, notification tenant ownership and monitor wiring), Python/Node dependency audits and frontend lint/build on `main`; disposable integration, container scanning, immutable artifacts and approval gate remain open |
| Deployment safety | Change-aware service replacement, pre-deploy backup, readiness gate, rollback on health failure, and no blanket Compose teardown | Fixed; tracked updater and VPS hook installed, and successful/skipped revisions are checkpointed so replay cannot repeat backups or container restarts |
| Log safety | Structured logs, request IDs, redaction of passwords/tokens/PII and retention/rotation | Audit |
| Alerting/runbooks | Actionable alerts and written response steps for outage, full disk, DB failure, auth spike and certificate failure | Partial: local systemd monitor and deduplicated journal alerts are active; external webhook and broader incident runbooks remain open |
| Scheduled jobs | Single-run locks, retries, idempotency, missed-job recovery and visible failure state | Single-run locks and visible health fixed/tested; retry/alert policy remains open |
| Data exports | Permission checks, tenant scoping, formula injection protection, memory limits and audit records | Fixed baseline: finance permissions and tenant scoping, formula-safe CSV cells, 50,000-row cap, export rate limits and audit records are active; large-dataset streaming remains a performance follow-up |
| Email/notifications | No cross-tenant recipient resolution, retries without duplicates, bounce/error handling | Active approved recipients are tenant-scoped; notification deduplication is atomic and uniquely indexed; external email retry/bounce handling remains open |
| AI features | No secret/PII leakage, tenant context boundaries, prompt injection controls, cost/rate limits and graceful key absence | Message history is user+tenant scoped, caller context stays at untrusted user priority, rate limits and graceful key absence are covered; automated PII redaction and budget telemetry remain open |

## P2 - Frontend and Product QA

| Area | Risk / required evidence | Status |
|---|---|---|
| Production UI cleanup | Remove demo/seed/debug/tip controls while preserving real empty-state guidance and Ctrl/Cmd+K | Fixed in frontend inventory; no demo/seed/debug/tip controls remain, and backend seed routes are disabled plus hard-blocked in production |
| Permission-aware UI | Hidden controls must match backend permissions; backend remains authoritative | Partial: salary/private HR and shared Daybook edit/reverse actions match permissions; broader screen inventory continues |
| Authentication UX | Correct errors, no redirect loops, token refresh/expiry behavior and safe logout | Audit |
| Form safety | Server errors shown clearly, double-submit prevention, validation parity and unsaved-change protection | Audit |
| Accessibility | Keyboard navigation, labels, focus, contrast, table semantics and screen-reader checks | Audit |
| Responsive layout | No clipped controls, overlapping text or unusable tables on supported mobile/desktop widths | Audit |
| Browser compatibility | Current Chrome, Edge, Safari and mobile smoke tests | Audit |
| Performance | Bundle size, lazy loading, pagination, large tenant datasets and API latency budgets | Accounting/Daybook pagination and route-level lazy loading are active; initial JavaScript is reduced from 1.52 MB (372 KB gzip) to 495 KB (149 KB gzip). Large-data/API latency budgets remain open |
| Date presentation | Business dates should be DD/MM/YYYY without changing API/database date storage | Fixed on major ERP operational, accounting, attendance, project, vendor, client, task, HR and administration surfaces at `8e1ec41`; timestamp boundaries render in IST while native date inputs and stored values remain ISO by design |

## Required Release Gates

1. Backup and verify the backup artifact before every production change.
2. Run focused unit tests plus disposable-database workflow tests for the changed area.
3. Prove unauthorized, same-tenant outsider and cross-tenant requests are denied.
4. Build immutable candidate images and verify startup/readiness before replacement.
5. Restart only affected services and preserve VPS-only Caddy changes.
6. Verify public site, API health, login, role access, logs and database invariants after deployment.
7. Remove all temporary QA data, containers, scripts and images.
8. Record commit, backup path, image rollback tag, tests, database changes and residual risk.
