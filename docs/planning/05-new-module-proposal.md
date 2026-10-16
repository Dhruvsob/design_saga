# Report 5 - New Module Proposal

These are first-class domain modules justified by workflows that generic tasks/files cannot safely represent. Build them in this order only after Phase 0 safety gates.

| Rank | Module | Why first-class | Minimum useful scope | Reused foundation | Complexity / priority |
|---|---|---|---|---|---|
| 1 | Document and Drawing Control | Wrong revision creates expensive rework and liability | drawing/document number, discipline, revision, status, checker/approver, issue purpose, current/superseded, transmittal, immutable history | projects, files, users, audit, notifications, object storage | L / P1 |
| 2 | Site Operations and Quality | Attendance alone does not manage execution | daily report, photos, progress, site issue, inspection, snag, owner/due date, verify/close, offline drafts | attendance location, projects, tasks, files | L / P1 |
| 3 | Client Selections and Approvals | Interior projects depend on traceable decisions | category, options, attributes, images, price, lead time, allowance delta, approval/lock/revision | client portal, BOQ, vendors, files | L / P1 |
| 4 | RFI, Submittal and Transmittal Register | AECO communication needs formal ball-in-court and official response | draft/submit/review/respond/close, watchers, references, revision, due date, export | projects, users, external portal, files, audit | L / P1 |
| 5 | Procurement and Material Control | Existing POs do not prove end-to-end control | requisition, RFQ/bid comparison, approval, PO, GRN, return, three-way match, committed cost | vendors, POs, expenses, accounting | L / P1 |
| 6 | Change and Variation Control | Scope, cost and time changes are financially material | request, reason, affected baseline, estimate, approval, change order, downstream budget/schedule/billing | quotations, projects, tasks, invoices | L / P1 |
| 7 | Resource Planning and Time | Firms sell professional capacity; task count is inadequate | weekly allocations, skills, planned/actual time, workload, utilization, chargeability | employees, projects, tasks, payroll cost permissions | L / P2 |
| 8 | Contracts, Obligations and Closeout | Dates, retention, insurance, warranties and handover are otherwise lost | contract metadata, obligation/expiry, retention, warranty, closeout checklist, handover manifest | clients/vendors/projects/files/notifications | M / P2 |
| 9 | Integration and Delivery Operations | SaaS needs visible, controllable external delivery | per-user/tenant connections, token state, queue, attempts, quotas, costs, reconnect/replay | jobs, audit, Google Calendar code | M / P1 |
| 10 | SaaS Entitlements and Metering | Commercial plans require fair, observable limits | plans, feature flags, seats, storage/API usage, grace state, audit, invoices later | tenants, platform admin | L / P2 |

## Modules to defer

- Full CAD/BIM authoring or model editing: specialist desktop/cloud products already dominate; integrate viewers/files only after demand.
- General chat/messaging: duplicates established channels and creates retention/moderation burden.
- Full warehouse/manufacturing ERP: outside core architecture-studio scope unless execution businesses validate it.
- Custom email/calendar clients: use provider integrations.
- Autonomous AI project manager or accountant: unacceptable accuracy, privacy and audit risk.

## Shared domain services required

- Approval engine with ordered/parallel steps, delegation, expiry, rejection, comments and audit.
- Document/object service with revisions, hashes, malware state, previews, signed delivery and retention.
- Workflow event/outbox service for notifications and integrations.
- Money/value objects using decimals, currency and explicit rounding.
- Party/contact model for clients, vendors, agencies and consultants without collapsing authentication identities.
- Configurable numbering/template service scoped per tenant.
