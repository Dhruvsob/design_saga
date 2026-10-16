# Report 4 - Existing Module Enhancement Plan

## Strategy

Preserve working modules and connect them through explicit state transitions. Each enhancement must add a domain record, permission rule, audit event, testable invariant, or useful workflow outcome. Avoid cosmetic expansion before integrity and usability.

| Existing module | Reuse | Enhancement and connection | Simplify/consolidate | Acceptance evidence |
|---|---|---|---|---|
| Auth/session/RBAC | Current password/Google login, sessions, roles, tenant overrides | MFA/passkey option, recovery codes, admin session revoke, access review, separation-of-duties policies | One identity and permission resolver only | Super Admin, owner and user flows; cross-tenant/role matrix; session revocation E2E |
| Platform tenants | Provisioning and Super Admin panel | Dry-run export/delete, collection registry, entitlements, quotas, tenant health | Central tenant lifecycle service | Every tenant-owned collection counted before/after; legal hold and rollback proof |
| Dashboard | Existing KPIs and permission projection | Role-specific panels, freshness timestamp, definitions, drill-down, exception queues | Remove duplicated vanity metrics | Reconciliation tests from source records to every KPI |
| Leads/clients | Lead board, conversion and client records | SLA, duplicate merge, requirement brief, communication/decision timeline, conversion baseline | Shared party/contact model without risky migration in first phase | Lead-to-project journey with immutable accepted scope |
| Projects | Lifecycle stages, team, files, budget fields | Project template, stage gates, RACI, risks, deliverables, baseline/current dates, closeout gate | One project timeline; avoid separate competing planners | Residential and commercial reference projects pass gate criteria |
| Tasks/follow-ups | Board/table, assignees, status, timeline, reminders | Subtasks, checklists, dependencies, recurrence, review/reject, estimates/time, handover, workload | One task engine for employee/vendor actions with visibility policy | Assignment-to-review journey, concurrency and visibility tests |
| Calendar | ERP event feed and personal Google outbound sync | Recurrence, conflict detection, timezones, preferences, sync-health/admin visibility | ERP owns business object; calendar stores a projection | No private cross-user leak; reconnect/retry/idempotency tests |
| Notifications | In-app records and bell | Channel preferences, digest, quiet hours, escalation, templates, delivery attempts, push/email | One notification service; domain modules publish events | Deduplication, opt-out, failure and tenant-boundary tests |
| Quotations/BOQ | Builder, costing, versions, PDF, conversion code | Accepted immutable baseline, tax/rounding rules, approvals, change-order link, template governance | Remove duplicate basic/advanced paths after usage audit | Quote totals/PDF/project baseline reconcile exactly |
| Accounting/invoices | Double entry, accounts, ledgers, P&L/trial balance, milestones | Decimal money, period locks, numbering, credit notes, aging workflow, bank reconciliation, GST/TDS review | One posting service; routes never write journals ad hoc | Balanced/idempotent/reversal/concurrency tests and accountant sign-off |
| Vendors/bills/payments | Master, ledger, rating, bills, payments | Compliance expiry, maker-checker bank changes, contracts, retention, warranty, onboarding | One vendor/agency/contractor party with type-specific capabilities | Payment cannot bypass vendor/bill/project/approval controls |
| Procurement/PO | PO route/page foundation | Requisition, RFQ comparison, approval, GRN, returns, three-way match, committed cost | Connect existing vendor/expense/accounting records | Requisition-to-payment reference journey with partial receipts |
| Expenses | Claims and approval | Policy limits, advances, OCR assist, duplicates, batch reimbursement, allocation | Reuse document and approval services | Duplicate warning, approval segregation, journal reconciliation |
| Employees/HR | Employee profiles/account links/privacy projection | On/offboarding, skills, document expiry, asset custody, controlled private fields | Employee is profile; User is authentication; maintain explicit link | Creation/login/offboarding and private-field permission tests |
| Attendance/leave | Check-in/out, site/office, corrections, holidays, approvals | GPS accuracy UX, offline draft, device/risk indicators, visit evidence, exception SLA | One attendance engine and business timezone | Hiren-style first-attempt check-in; concurrent and payroll-block tests |
| Payroll/loans | Salary preview/run, journal posting, payslips, loans | Statutory rules, period lock, adjustments/final settlement, bank export, encrypted delivery | Reuse accounting posting and document delivery | Golden payroll cases reviewed by qualified accountant/HR |
| Files/storage | File metadata/link validation | Direct upload, S3 key policy, scan/quarantine, preview, revision/hash, signed download, retention | Shared document service for all modules | Cross-tenant object denial, malware, size/type, expiry and audit tests |
| Search | Global query/command palette | Search new domain registers and recent items with strict ACL | One search service; no client-side secret filtering | Permission fuzz tests; bounded/paginated results |
| Audit | Audit events and integrity chain | Event catalogue, actor/tenant/request IDs, export, retention, alert rules | One append-only audit API | Chain verification, denied access, clock/order and restore tests |
| AI | Existing assistant/quotation callouts | Tenant opt-in, redaction, retrieval ACL, citations, budget, human confirmation | Remove provider-specific business logic from core routes | Prompt-injection/data-exfiltration evals; zero autonomous financial changes |

## Cross-module workflows to build before more pages

1. Lead -> requirement brief -> approved quote -> controlled project baseline.
2. Project deliverable -> task/check/review -> drawing revision -> transmittal -> client/site acknowledgement.
3. Selection -> client approval -> budget/lead-time impact -> requisition -> PO -> receipt -> inspection -> payable.
4. Site visit -> report/photos/issues -> assignment -> verification -> weekly report.
5. Approved milestone -> invoice -> reminder -> receipt -> reconciliation -> project profitability.
6. Employee/user -> attendance/leave exceptions -> locked payroll -> journal -> payslip/bank output.

## UI/UX cleanup

- Remove demo/pro-tip/testing controls while retaining useful empty states and the functional command palette.
- Create consistent list/detail/action patterns, filters, pagination, loading, empty, denied and error states.
- Make field workflows usable on 360-430 px screens under slow/intermittent networks.
- Use role-appropriate navigation and hide unauthorized modules, while keeping backend authorization authoritative.
- Add accessibility acceptance: keyboard operation, focus, labels, contrast, error association and reduced motion.
