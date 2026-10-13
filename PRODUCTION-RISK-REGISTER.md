# Design Saga ERP Production Risk Register

Last updated: 2026-10-13 (Asia/Kolkata)

This is a living production checklist, not a claim that unknown defects do not exist.
`Fixed` means code and production behavior were verified. `Open` means remediation or
evidence is still required. `Audit` means no defect is confirmed, but the area has not
yet received sufficient adversarial testing.

## P0 - Immediate Security and Availability

| Area | Risk / required evidence | Status |
|---|---|---|
| Tenant login | Super Admin, tenant owner, email, and employee ID must use one authentication system and resolve the correct tenant/role | Fixed and deployed |
| Tenant isolation | Every business query must enforce `org_id`; cross-tenant IDs must return no data | Fixed in shared database scope; ongoing route-by-route audit |
| Project/task/file IDOR | Same-tenant users must not read or modify guessed projects, tasks, follow-ups, reminders, settings, or file links | Fixed, tested, pending deployment in DS-005 |
| Attachment URL injection | Reject `javascript:`, `data:`, `file:`, credential-bearing, malformed, and control-character URLs | Fixed, tested, pending deployment in DS-005 |
| Exposed credentials | Rotate the MongoDB Atlas password previously pasted into chat and revoke the temporary Mongo viewer token; confirm neither is used by production | Open, external account action required |
| Super Admin allowlist | Replace the repository-default `designsaga10@gmail.com` allowlist with an explicitly managed production identity and verify registration/password-reset cannot claim it | Open; production startup warning confirmed |
| SSH access | Key-only login, disabled password/root remote login where operationally safe, restricted users, firewall, brute-force protection | Audit |
| Backups | Encrypted automated database backups, off-server retention, restore drill, documented RPO/RTO | Open: deploy backups exist; automated restore evidence required |
| Disaster rollback | Known image tags, database compatibility, service-specific rollback, preserved Caddy configuration | Partially fixed; test a complete restore drill |
| Monitoring | Uptime, container health, disk, memory, CPU, database capacity, TLS expiry, 5xx rate and backup-failure alerts | Open |

## P1 - Authorization and Data Protection

| Area | Risk / required evidence | Status |
|---|---|---|
| Employee privacy | Salary, bank, government IDs, private documents, performance and payslips restricted by HR/payroll permissions | Fixed and deployed |
| Attendance identity | Employees may check in/out only for themselves except explicit managers; geofence/site authorization enforced | Fixed and deployed |
| Approval races | Concurrent attendance, leave and correction approvals must produce one final decision | Fixed and deployed |
| Payroll integrity | One payroll per period, unresolved attendance blocks payroll, correct account types and idempotent posting | Fixed and deployed |
| Financial posting | Exact linked settlement, correct accounts, atomic idempotency, reversible immutable journal history | Fixed and deployed |
| Remaining module IDOR | Adversarially test clients, leads, quotations, vendors, purchase orders, expenses, loans, holidays, comments, calendar, notifications and search | Audit |
| Role overrides | Test empty/custom permission sets, protected roles, privilege escalation, role changes during active sessions | Audit |
| Session lifecycle | Expiry, logout invalidation, password-change revocation, inactive/suspended tenant revocation, stolen-token resistance | Audit |
| CSRF and cookies | Confirm `Secure`, `HttpOnly`, appropriate `SameSite`, origin checks and no state-changing GET routes | Audit |
| Rate limiting | Login, password reset, OTP, public portal, search, AI and expensive exports need per-IP/account limits | Open |
| Secrets management | No secrets in Git/images/logs; least-privilege environment access; rotation procedure and secret inventory | Audit |
| Stored XSS | Validate/sanitize notes, descriptions, comments, names, SVG/media and any rich-text rendering | Audit |
| File handling | Authenticated object access, signed expiry, ownership, size/type limits, filename safety, malware scanning and deletion lifecycle | Open; URL scheme protection alone is complete |
| Audit logs | Tamper-resistant records for auth, permissions, payroll, finance, approvals, exports and destructive actions | Audit |

## P1 - Business Integrity and Concurrency

| Area | Risk / required evidence | Status |
|---|---|---|
| Employee/user link | Employee creation must create/link exactly one active authentication user where requested | Fixed for reported login path; uniqueness audit required |
| Invoice lifecycle | Draft/issued/paid/reversed/deleted transitions and permissions | Fixed for linked payment path; full lifecycle audit required |
| Expense claims | Duplicate submission, concurrent approval/reimbursement, receipt ownership and account validation | Audit |
| Purchase orders/GRN | Approval races, quantity over-receipt, duplicate bills/payments and immutable history | Audit |
| Loans/EMI | Concurrent payment/prepayment, balance floor, journal reconciliation and deletion rules | Audit |
| Vendor commissions | Duplicate settlement, reversal, tax/account validation and tenant isolation | Audit |
| Project deletion | Preserve dependent financial/history records; archive instead of destructive cascades | Partially fixed; dependency matrix audit required |
| Unique identities | Case-insensitive email, employee ID, tenant slug, invoice number and vendor tax identifiers | Audit |
| Time zones | All business dates use Asia/Kolkata while stored timestamps remain UTC; test midnight/month/year boundaries | Fixed for attendance; audit remaining modules |
| Money precision | Decimal-safe calculations, rounding policy, GST/TDS, currency and reconciliation | Audit |

## P2 - Reliability, DevOps and Operations

| Area | Risk / required evidence | Status |
|---|---|---|
| Database indexes | Index every tenant/filter/uniqueness path; monitor slow queries and index build failures | Partial |
| Database capacity | Connection limits, timeouts, pool sizing, storage growth, vacuum/maintenance and corruption alerts | Audit |
| Container hardening | Non-root runtime, read-only filesystem where possible, dropped capabilities, resource limits and health checks | Partial: limits/health checks exist |
| Dependency security | Automated Python/Node/container CVE scan, lockfiles, update policy and license review | Open |
| CI/CD | Build, lint, unit, integration, migration, security scan, immutable artifact and approval gate before production | Open |
| Deployment safety | Zero/low-downtime backend replacement, readiness gate, rollback on health failure, no blanket Compose teardown | Partial/manual |
| Log safety | Structured logs, request IDs, redaction of passwords/tokens/PII and retention/rotation | Audit |
| Alerting/runbooks | Actionable alerts and written response steps for outage, full disk, DB failure, auth spike and certificate failure | Open |
| Scheduled jobs | Single-run locks, retries, idempotency, missed-job recovery and visible failure state | Audit |
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
