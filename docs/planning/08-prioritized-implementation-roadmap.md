# Report 8 - Prioritized Implementation Roadmap

## Phase gates

No phase starts without approved scope, owner, threat model, acceptance tests, staging data, migration/rollback plan and observability. No phase is deployed merely because code exists.

## Phase 0 - Production safety and trustworthy baseline (P0)

**Scope:** External credential revocation, review the pending local tenant fixes, off-site backups and restore drill, monitoring/alerts, CI gates, route-by-route tenant/IDOR sweep, upload threat model, money precision plan, database decision record, data inventory and baseline performance.

**Reuse:** Current scoped DB, audit, tests, Docker health checks and repair runbooks.

**Changes:** Primarily controls/tests/operations; minimal schema indexes/metadata only after preflight. No domain redesign.

**Permissions:** Validate every role/resource combination and platform boundary.

**Tests:** Cross-tenant fuzz matrix, session/CSRF/XSS/download/upload abuse, concurrency, backup restore, smoke, baseline load.

**Rollback:** Per-service immutable images; reversible index/config changes; verified DB backup.

**Acceptance:** External secrets rotated; restore meets approved RPO/RTO; critical alerts reach owner; no known P0 isolation/integrity defect; pending local diff either verified/committed/deployed or rejected with reason.

## Phase 1 - Tasks, calendar, reminders and delivery operations (P1)

**Scope:** Subtasks/checklists, recurrence, dependencies, review/rejection, deadline history, notification preferences/digest/escalation, email and push, Google Calendar production verification, sync health/replay, role-focused “My Work.”

**Reuse:** Existing tasks, calendar, notifications, job scheduler and per-user Google connection.

**Data/API/UI:** Add recurrence/dependency/review metadata, notification preferences and delivery attempts; version endpoints; My Work and integration-health views.

**Integration:** SES (or selected provider), Web Push/FCM, existing Google Calendar. No two-way sync initially.

**Tests:** Privacy, idempotency, recurrence/timezone/DST, retries, dedupe, quiet hours, reconnect, mobile/browser delivery.

**Migration:** Defaults preserve current behavior; backfill no external events without user opt-in.

**Rollback:** Feature flags by tenant and channel; queue consumers can stop without losing core tasks.

**Acceptance:** Assigned user sees only authorized work; reminders deliver through selected channels; failures are visible/retryable; no duplicate Google events; private events remain private.

## Phase 2 - Document, drawing, selection and approval control (P1)

**Scope:** Object storage/scanning, document/drawing register, revisions, issue status, transmittals, client selections and approval portal, change requests.

**Reuse:** Projects, files, quotation BOQ, client portal, audit, comments and notifications.

**Data/API/UI:** New document/revision/transmittal/selection/approval records; current-version queries; secure uploads/previews; register/detail/review screens.

**Permissions:** Confidential projects, discipline reviewers, client-viewable versions, external recipient grants.

**Tests:** Supersession, immutable issued packages, cross-tenant objects, scan quarantine, signed URL expiry, approval evidence, budget delta.

**Migration:** Existing URL files remain legacy links; optional controlled import, never silent conversion.

**Acceptance:** Site/client can identify the current issued version; every approval identifies actor/version/time; selection change propagates through approved change workflow.

## Phase 3 - Site operations, agencies and procurement (P1)

**Scope:** Daily site report, inspections, snags/issues, offline drafts, RFI/submittal, requisition/RFQ/comparison, PO/GRN/returns, three-way match, retention/warranty.

**Reuse:** Attendance/geofence, tasks, vendors, POs, expenses, accounting and document service.

**Permissions:** Site/project membership, external agency grants, procurement maker-checker, finance approval.

**Tests:** Offline replay/conflicts, GPS accuracy exceptions, partial delivery/return, quantity/amount tolerances, duplicate bill/payment and external isolation.

**Migration:** POs continue; new workflow applies prospectively unless a specific open PO is opted in.

**Acceptance:** A purchase can be traced from approved need to receipt/inspection/bill/payment; a snag/RFI has one accountable current state and evidence.

## Phase 4 - Finance, receivables and compliance maturity (P0/P1)

**Scope:** Decimal money, period close, numbering, credit notes, receivables workflow, bank import/reconciliation, cash forecast, GST/TDS requirements approved by Indian accounting professional.

**Reuse:** Existing double-entry, ledgers, reports, invoices, milestones and vendor postings.

**Tests:** Golden accounting cases, migrations reconcile balances to the paisa, concurrency/idempotency/reversal, closed-period denial, permission segregation.

**Migration:** Shadow calculations and reports first; signed reconciliation; rollback snapshot and no destructive source rewrite.

**Acceptance:** Trial balance and subledgers reconcile; no float drift; closed periods immutable; source-to-journal trace complete.

## Phase 5 - HR, attendance and payroll maturity (P0/P1)

**Scope:** On/offboarding, skills/assets, attendance offline/risk/exception UX, statutory payroll rule packs, adjustments/final settlement, bank output and secure payslip delivery.

**Reuse:** Existing employee/user link, attendance engine, leave/holiday, payroll journal and privacy projection.

**Tests:** First-attempt check-in under real devices, timezones, GPS uncertainty, concurrent approvals, exception blocking, privacy and accountant/HR golden cases.

**Acceptance:** Employee lifecycle removes access predictably; payroll cannot run over unresolved inputs; bank/payslip totals reconcile and remain private.

## Phase 6 - Portals, resource planning and selected connectors (P2)

**Scope:** External agency/vendor access, resource allocation/time, client closeout, one accounting export/connector, Microsoft Calendar if demanded, payment links.

**Reuse:** Portal token/grant patterns, RBAC, projects, payments and integration operations.

**Acceptance:** External parties see only explicitly shared resources; capacity and profitability reconcile; each connector has revocation, health, cost and replay controls.

## Phase 7 - Analytics and optional AI (P3)

**Scope:** Governed portfolio metrics, forecasting, OCR/transcription pilots, retrieval assistant with citations, anomaly suggestions.

**Guardrails:** Opt-in, budgets, redaction, ACL-filtered retrieval, human confirmation, no autonomous finance/payroll/approval actions.

**Acceptance:** Evaluation dataset demonstrates useful accuracy and no cross-tenant retrieval; spend caps and disable switch work.

## First approved implementation slice proposed

Approve **Phase 0A only** first: rotate external secrets, establish off-site restore evidence, add external/queue alerts, review and test the ten-file pending local tenant fix, and create a route authorization coverage map. This is the smallest work that reduces immediate business risk and makes later feature work safer.
