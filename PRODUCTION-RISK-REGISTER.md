# Design Saga ERP Production Risk Register

Last updated: 2026-10-15 (Asia/Kolkata)

This is a living production checklist, not a claim that unknown defects do not exist.
`Fixed` means code and production behavior were verified. `Open` means remediation or
evidence is still required. `Audit` means no defect is confirmed, but the area has not
yet received sufficient adversarial testing.

## P0 - Immediate Security and Availability

| Area | Risk / required evidence | Status |
|---|---|---|
| Tenant login | Super Admin, tenant owner, email, and employee ID must use one authentication system and resolve the correct tenant/role | Fixed and deployed |
| Tenant isolation | Every business query must enforce `org_id`; cross-tenant IDs must return no data | Fixed in shared database scope; ongoing route-by-route audit |
| Project/task/file IDOR | Same-tenant users must not read or modify guessed projects, tasks, follow-ups, reminders, settings, or file links | Fixed, tested, and deployed at `236d7c7` |
| Attachment URL injection | Reject `javascript:`, `data:`, `file:`, credential-bearing, malformed, and control-character URLs | Fixed, tested, and deployed at `236d7c7` |
| Exposed credentials | Rotate the MongoDB Atlas password previously pasted into chat and revoke the temporary Mongo viewer token; confirm neither is used by production | Open, external account action required |
| Super Admin allowlist | Require an explicit production identity, prevent tenant role escalation, and keep platform owners outside tenant scope | Fixed and deployed at `e086089` |
| SSH access | Key-only login, disabled password/root remote login where operationally safe, restricted users, firewall, brute-force protection | Fixed baseline: passwords and keyboard-interactive auth disabled, root is key-only, three-attempt/30-second limits active; dedicated non-root operator and fail2ban remain defense-in-depth follow-ups |
| Host firewall | Deny unsolicited inbound traffic while preserving SSH, HTTP, HTTPS, and HTTP/3 | Fixed: UFW default-deny is active with only 22/tcp, 80/tcp, 443/tcp, and 443/udp allowed for IPv4/IPv6 |
| Backups | Encrypted automated database backups, off-server retention, restore drill, documented RPO/RTO | Partial: daily checksummed archive and restore validation pass; off-server encrypted retention and documented RPO/RTO remain open |
| Disaster rollback | Known image tags, database compatibility, service-specific rollback, preserved Caddy configuration | Partially fixed; test a complete restore drill |
| Monitoring | Uptime, container health, disk, memory, CPU, database capacity, TLS expiry, 5xx rate and backup-failure alerts | Partial: five-minute container/site/API/disk/backup monitor is active; external webhook, capacity/TLS/5xx alerting remain open |

## P1 - Authorization and Data Protection

| Area | Risk / required evidence | Status |
|---|---|---|
| Employee privacy | Salary, bank, government IDs, private documents, performance and payslips restricted by HR/payroll permissions | Fixed and deployed |
| Attendance identity | Employees may check in/out only for themselves except explicit managers; geofence/site authorization enforced; rejected punches can be retried without losing audit history | Fixed, deployed, and verified live |
| Attendance data integrity | Validate geo/type/schedule inputs, manual punch dates/order, employee references, overlapping leave, and employee-specific weekly offs | Fixed, deployed, and verified live |
| Approval races | Concurrent attendance, leave, correction, and late-arrival approvals must produce one final decision | Fixed, deployed, and verified live |
| Payroll integrity | One payroll per period, unresolved attendance blocks payroll, correct account types and idempotent posting | Fixed and deployed |
| Financial posting | Exact linked settlement, correct accounts, atomic idempotency, reversible immutable journal history | Fixed and deployed |
| Remaining module IDOR | Adversarially test clients, leads, quotations, vendors, purchase orders, expenses, loans, holidays, comments, calendar, notifications and search | Search/comments/calendar/notification-recipient leaks fixed; remaining modules continue |
| Role overrides | Test empty/custom permission sets, protected roles, privilege escalation, role changes during active sessions | Empty/custom overrides fixed and deployed; broader escalation audit continues |
| Session lifecycle | Expiry, logout invalidation, password-change revocation, inactive/suspended tenant revocation, stolen-token resistance | Lifecycle gates fixed and deployed; stolen-token resistance audit continues |
| CSRF and cookies | Confirm `Secure`, `HttpOnly`, appropriate `SameSite`, origin checks and no state-changing GET routes | Audit |
| Rate limiting | Login, password reset, OTP, public portal, search, AI and expensive exports need per-IP/account limits | Partial: password login has account and opaque per-source limits; remaining endpoint classes are open |
| Secrets management | No secrets in Git/images/logs; least-privilege environment access; rotation procedure and secret inventory | Audit |
| Stored XSS | Validate/sanitize notes, descriptions, comments, names, SVG/media and any rich-text rendering | Audit |
| File handling | Authenticated object access, signed expiry, ownership, size/type limits, filename safety, malware scanning and deletion lifecycle | Open; URL scheme protection alone is complete |
| Audit logs | Tamper-resistant records for auth, permissions, payroll, finance, approvals, exports and destructive actions | Audit |

## P1 - Business Integrity and Concurrency

| Area | Risk / required evidence | Status |
|---|---|---|
| Employee/user link | Employee creation must create/link exactly one active authentication user where requested | Fixed for reported login path; uniqueness audit required |
| Invoice lifecycle | Draft/issued/paid/reversed/deleted transitions and permissions | Fixed for linked payment path; full lifecycle audit required |
| Expense claims | Duplicate submission, concurrent approval/reimbursement, receipt ownership and account validation | Idempotency and duplicate submission fixed/tested; remaining approval/receipt audit continues |
| Purchase orders/GRN | Approval races, quantity over-receipt, duplicate bills/payments and immutable history | Over-receipt and bill/payment idempotency fixed/tested; remaining lifecycle audit continues |
| Loans/EMI | Concurrent payment/prepayment, balance floor, journal reconciliation and deletion rules | Concurrent EMI posting and journal cardinality fixed/tested; prepayment/deletion audit continues |
| Vendor commissions | Duplicate settlement, reversal, tax/account validation and tenant isolation | Audit |
| Project deletion | Preserve dependent financial/history records; archive instead of destructive cascades | Partially fixed; dependency matrix audit required |
| Unique identities | Case-insensitive email, employee ID, tenant slug, invoice number and vendor tax identifiers | Employee/document counters and key finance identifiers protected; broader normalization audit continues |
| Time zones | All business dates use Asia/Kolkata while stored timestamps remain UTC; test midnight/month/year boundaries | Shared IST business-date helper applied to audited modules; boundary regression test passes |
| Money precision | Decimal-safe calculations, rounding policy, GST/TDS, currency and reconciliation | Audit |

## P2 - Reliability, DevOps and Operations

| Area | Risk / required evidence | Status |
|---|---|---|
| Database indexes | Index every tenant/filter/uniqueness path; monitor slow queries and index build failures | Integrity indexes fixed/tested; performance/slow-query audit remains open |
| Database capacity | Connection limits, timeouts, pool sizing, storage growth, vacuum/maintenance and corruption alerts | Audit |
| Container hardening | Non-root runtime, read-only filesystem where possible, dropped capabilities, resource limits and health checks | Fixed baseline: backend is non-root/read-only with all capabilities dropped; backend/web use no-new-privileges, init and health checks |
| Dependency security | Automated Python/Node/container CVE scan, lockfiles, update policy and license review | Partial: Python/runtime npm and final images scan clean; npm lockfile is committed; CRA build-only findings, automation and license review remain open |
| CI/CD | Build, lint, unit, integration, migration, security scan, immutable artifact and approval gate before production | Open |
| Deployment safety | Change-aware service replacement, pre-deploy backup, readiness gate, rollback on health failure, and no blanket Compose teardown | Fixed; tracked updater and VPS hook installed |
| Log safety | Structured logs, request IDs, redaction of passwords/tokens/PII and retention/rotation | Audit |
| Alerting/runbooks | Actionable alerts and written response steps for outage, full disk, DB failure, auth spike and certificate failure | Partial: local systemd monitor and deduplicated journal alerts are active; external webhook and broader incident runbooks remain open |
| Scheduled jobs | Single-run locks, retries, idempotency, missed-job recovery and visible failure state | Single-run locks and visible health fixed/tested; retry/alert policy remains open |
| Data exports | Permission checks, tenant scoping, formula injection protection, memory limits and audit records | Audit |
| Email/notifications | No cross-tenant recipient resolution, retries without duplicates, bounce/error handling | Audit |
| AI features | No secret/PII leakage, tenant context boundaries, prompt injection controls, cost/rate limits and graceful key absence | Audit |

## P2 - Frontend and Product QA

| Area | Risk / required evidence | Status |
|---|---|---|
| Production UI cleanup | Remove demo/seed/debug/tip controls while preserving real empty-state guidance and Ctrl/Cmd+K | Requested; full-screen inventory verification required |
| Permission-aware UI | Hidden controls must match backend permissions; backend remains authoritative | Partial; salary/private HR controls fixed |
| Authentication UX | Correct errors, no redirect loops, token refresh/expiry behavior and safe logout | Audit |
| Form safety | Server errors shown clearly, double-submit prevention, validation parity and unsaved-change protection | Audit |
| Accessibility | Keyboard navigation, labels, focus, contrast, table semantics and screen-reader checks | Audit |
| Responsive layout | No clipped controls, overlapping text or unusable tables on supported mobile/desktop widths | Audit |
| Browser compatibility | Current Chrome, Edge, Safari and mobile smoke tests | Audit |
| Performance | Bundle size, lazy loading, pagination, large tenant datasets and API latency budgets | Audit |

## Required Release Gates

1. Backup and verify the backup artifact before every production change.
2. Run focused unit tests plus disposable-database workflow tests for the changed area.
3. Prove unauthorized, same-tenant outsider and cross-tenant requests are denied.
4. Build immutable candidate images and verify startup/readiness before replacement.
5. Restart only affected services and preserve VPS-only Caddy changes.
6. Verify public site, API health, login, role access, logs and database invariants after deployment.
7. Remove all temporary QA data, containers, scripts and images.
8. Record commit, backup path, image rollback tag, tests, database changes and residual risk.
