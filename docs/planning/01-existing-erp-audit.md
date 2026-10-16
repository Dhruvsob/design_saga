# Report 1 - Existing ERP Audit

## Executive finding

Design Saga is a real multi-module ERP, not a demo shell. It has substantial CRM, project, task, quotation, finance, vendor, attendance, payroll, RBAC, audit, notification, and calendar code. Its strongest evidence is security/financial repair work. Its main product gap is workflow depth: several architecture-specific processes are represented by generic projects, tasks, files, or comments rather than controlled records with revisions, approvals, transmittals, responsibility, and audit history.

## Technology and deployment inventory

| Layer | Actual implementation | Evidence | Assessment |
|---|---|---|---|
| Frontend | React 19, React Router 7, CRA/CRACO, Tailwind, Radix, Recharts, Axios | `frontend/package.json`, `frontend/src/App.js` | Code present; CRA 5 is an aging build base and should be replaced deliberately, not during feature work. |
| API | FastAPI 0.143, Pydantic 2, 322 route declarations | `backend/server.py`, `backend/routes/*` | Broad monolith/modular hybrid; route-by-route controls still need continuous audit. |
| Data access | Motor/PyMongo API through scoped DB wrapper | `backend/core/db.py`, `backend/core/scoped_db.py` | Useful compatibility layer; raw `db` access remains a recurring tenant-safety hazard. |
| Database | PostgreSQL DocumentDB image plus FerretDB 2.7 Mongo protocol | `docker-compose.yml` | PostgreSQL-backed, not Atlas. Compatibility compromises relational integrity and schema clarity. |
| Edge/runtime | Caddy, nginx static frontend, containerized backend | `docker-compose.yml`, `deploy/Caddyfile` | Good small-VPS topology; single-host failure domain. |
| Runtime hardening | Read-only backend, tmpfs, all capabilities dropped, no-new-privileges | `docker-compose.yml` | Verified configuration; web/Caddy hardening and image CVEs still require lifecycle management. |
| Tests | 28 backend test files plus historical live/disposable DB checks | `backend/tests/*`, repair tracker | Stronger than a typical prototype; incomplete frontend E2E, accessibility, load, and restore coverage. |

## Concrete surface inventory

| Surface | Count / files | Audit use |
|---|---|---|
| API declarations | 322 total: `server.py` 83; accounting 39; attendance 35; vendors 29; finance extras 20; tasks 18; platform 17; purchase/expenses 9 each; loans 8; auth 7; payroll/holidays/calendar/master data/notifications/organization 6 each; Google Calendar 5; audit/comments 3 each; search 1 | Shows broad capability, not completion; high-count modules require bounded pagination and authorization coverage. |
| Frontend pages | 29: Accounting, Attendance, AuthCallback, Calendar, ClientDetail, ClientPortal, Clients, CompanySettings, Dashboard, EmployeeDetail, Employees, Expenses, Holidays, Invoices, Leads, Loans, Login, PrivacyPolicy, ProjectDetail, Projects, PurchaseOrders, QuotationBuilder, QuotationsAdv, RBACAdmin, SuperAdminPanel, TaskDetail, TasksBoard, VendorDetail, Vendors | Every page was mapped to a module below; a page is only `Code present` until its complete workflow is proven. |
| Route modules | accounting, attendance, audit, auth, calendar, comments, expenses, finance_extras, google_calendar, holidays, loans, master_data, notifications, organization, payroll, platform, purchase, search, tasks, vendors | New work should follow these boundaries and reduce the remaining `server.py` concentration incrementally. |
| Shared controls | access control, attendance engine, audit, CSV safety, database/scope, downloads, features, finance, Google Calendar, helpers, HTTP security, indexes, jobs, locks, notifications, RBAC, tenancy, URL security | Reuse these controls; test them as product-wide contracts. |
| Data models | accounting, attendance, expense, loan, organization, purchase, task, user, vendor plus inline Pydantic models in `server.py` | Inline/server concentration and schemaless persistence make domain migrations and constraints harder. |

No browser E2E suite equivalent to the backend coverage was identified in this inventory. Historical browser/curl checks are useful evidence but are not a repeatable regression gate.

## Module inventory

| Module | Classification | Evidence | Main gap / next proof |
|---|---|---|---|
| Authentication and sessions | Fully implemented for recorded core paths | `routes/auth.py`, `server.py`, auth tests; production repair record | Add MFA/passkeys, recovery, admin session inventory, formal rate-limit evidence. |
| Tenant provisioning/platform admin | Partially implemented | `routes/platform.py`, `SuperAdminPanel.jsx` | Tenant lifecycle/deletion/export and billing/plan controls need deeper tests; pending local cleanup is undeployed. |
| RBAC and role overrides | Fully implemented for core roles | `core/rbac.py`, `RBACAdmin.jsx`, repair tests | Need policy matrix per new module, separation-of-duties rules, periodic access review. |
| Dashboard | Partially implemented | `/api/dashboard`, `Dashboard.jsx` | Generic KPIs; no role-specific workload, approval, delay, cash forecast, or data-freshness semantics. |
| Leads/CRM | Partially implemented | lead models/routes in `server.py`, `Leads.jsx` | No campaign/source attribution depth, SLA automation, duplicate merge, consent, or full opportunity pipeline analytics. |
| Clients | Partially implemented | `Clients.jsx`, `ClientDetail.jsx`, client routes | Contacts, organizations, communication history, requirements, and conflict checks are shallow. |
| Client portal | Partially implemented/security-sensitive | `ClientPortal.jsx`, portal routes | Token lifecycle and scoped sharing exist historically; needs granular approvals, expiry, watermarking, portal audit, and revocation UX. |
| Projects/lifecycle | Partially implemented | `Projects.jsx`, `ProjectDetail.jsx`, project routes | Generic stages do not enforce architecture lifecycle gates, deliverables, dependencies, or closeout completeness. |
| Tasks/follow-ups | Partially implemented, broad | `routes/tasks.py`, `TasksBoard.jsx`, `TaskDetail.jsx` | Has board/table/status/follow-ups/timeline; lacks first-class subtasks, dependencies, recurrence, effort/time, review gates, and capacity planning. |
| Calendar/reminders | Partially implemented | `routes/calendar.py`, `Calendar.jsx`, `CalendarReminders.jsx` | ERP events work; recurrence/conflicts/timezones/escalations/two-way sync need controlled design. |
| Google Calendar | Implemented for personal outbound sync; rollout incomplete | `core/google_calendar.py`, `routes/google_calendar.py`, tests, commit `be360c8` | Per-user privacy recorded; sensitive-scope OAuth verification and production monitoring remain. No proven full two-way sync. |
| Notifications | Partially implemented | `routes/notifications.py`, `core/notifications.py`, `NotificationBell.jsx` | In-app foundation; delivery preferences, email/push, digesting, escalation, deduplication, and observability missing. |
| Files/documents | Partially implemented | file routes in `server.py`, storage service | Primarily metadata/URL workflows; no production-grade object upload, malware scan, immutable revision, transmittal, preview, retention, or legal hold. |
| Drawings/revisions | Missing as a first-class module | no dedicated page/model/route | Generic files cannot safely represent drawing numbers, revisions, issue purpose, supersession, approvals, and transmittals. |
| Quotations/BOQ | Partially implemented, feature-rich | `QuotationBuilder.jsx`, `QuotationsAdv.jsx`, quotation code/PDF in `server.py` | Historical claims include BOQ/version/approval; needs end-to-end revalidation, tax precision, template governance, and immutable accepted version. |
| Invoices/receivables | Partially implemented | `Invoices.jsx`, invoice/accounting routes | Posting safety improved; recurring billing, credit notes, aging workflow, bank reconciliation, GST/e-invoice decisions need work. |
| Accounting/ledgers | Partially implemented with strong core integrity | `routes/accounting.py`, `Accounting.jsx`, finance tests | Double-entry and reports exist; money uses floats in places, no period close, reconciliation, immutable numbering, GST/TDS depth, or external accountant export proof. |
| Expenses | Partially implemented | `routes/expenses.py`, `Expenses.jsx` | Approval exists; policy, advances, OCR, duplicate receipt detection, mileage/per diem, allocation, and reimbursement batch gaps. |
| Vendors/agencies | Partially implemented | `routes/vendors.py`, vendor models/pages | Master, bills, payments, ledger, ratings exist; vendor portal, onboarding/compliance expiry, bid comparison, contracts, retention/warranty gaps. |
| Purchase orders/procurement | Partially implemented | `routes/purchase.py`, `PurchaseOrders.jsx` | PO surface exists; requisition-to-quote-to-PO-to-GRN-to-bill three-way match and inventory linkage not proven. |
| Inventory/materials | Missing/limited | no dedicated inventory page/module | Need site/store quantities, reservations, receipts, transfers, returns, consumption, wastage, and valuation only if validated as target-market need. |
| Employees/HR records | Partially implemented | employee routes in `server.py`, employee pages | Privacy projections hardened; onboarding/offboarding, document expiry, skill matrix, asset issue, performance governance incomplete. |
| Attendance/geofence | Partially implemented with critical path verified | `routes/attendance.py`, `core/attendance_engine.py`, `Attendance.jsx` | Hiren Panchal path and concurrency were verified; offline capture, anti-spoofing policy, GPS accuracy UX, device risk, and field visit evidence remain. |
| Leave/holidays | Partially implemented | attendance/holiday routes and pages | Rules/workflows exist; carry-forward, encashment, regional policy templates, balances migration and payroll acceptance need deeper proof. |
| Payroll | Partially implemented with posting safeguards | `routes/payroll.py`, tests | Run idempotency/privacy fixed; statutory payroll, payslip delivery, bank files, locks, adjustments, final settlement, and compliance review missing. |
| Loans/advances | Partially implemented | `routes/loans.py`, `Loans.jsx` | Needs payroll schedule integration, approvals, interest/policy rules, settlement and reconciliation evidence. |
| Audit log | Partially implemented, security foundation | `core/audit.py`, `routes/audit.py` | HMAC-chain repair recorded; retention/export/access review, alerts, clock integrity, and tamper-evidence operations need proof. |
| Search/command palette | Partially implemented | `routes/search.py`, `CommandPalette.jsx` | Useful global search; permission filtering must remain regression-tested as modules expand. |
| AI assistant/quotation audit | Optional/integration-dependent | AI routes in `server.py`, Emergent key | Avoid making core workflows dependent on AI; require tenant consent, redaction, cost caps, provenance, and human review. |
| Site reports/inspections/snags | Missing as controlled modules | generic tasks/attendance/photos only | Architecture execution requires site diary, issue, inspection, snag, evidence, assignment, due date, closure, and report records. |
| RFIs/submittals/transmittals | Missing | no dedicated models/routes/pages | High-value AECO gap validated against Autodesk/Newforma workflows. |
| Client selections/approvals | Missing as first-class workflow | no dedicated module | Need option sets, budget/lead-time impact, decision history, lock, change propagation. |
| Contracts/change orders | Partial fragments | quotation change orders/vendor data | Need approved baseline, scope/cost/time impact, signatures, downstream budget/billing update, immutable history. |
| Resource planning/time sheets | Missing/limited | task assignment only | No capacity forecast, planned vs actual hours, utilization, chargeability, or staffing conflict detection. |
| Reporting/analytics | Partially implemented | dashboards, finance reports | No governed semantic layer, scheduled reports, data quality indicators, portfolio forecasting, or export catalog. |

## Security, reliability, and data findings

| Finding | Status | Decision |
|---|---|---|
| Previously pasted Atlas password and viewer token | Open external action | Rotate/revoke now even though production is reported not to use Atlas. Never copy secrets into reports. |
| Tenant-scoped database wrapper | Deployed foundation; one pending local precedence fix | Treat any raw business-collection access as a review finding; test malicious `org_id` inputs. |
| Same-host backups | Insufficient for disaster recovery | Add encrypted off-site backups, retention, restore automation, and quarterly restore drill. |
| Monitoring/alerting | Partial | Add external uptime, 5xx/latency, queue failures, disk/memory, backup age, cert, database and security-event alerts. |
| Upload security | Incomplete product surface | Object storage, signed URLs, type/size checks, malware scan, content disposition, tenant prefixes, lifecycle policies. |
| CSRF/XSS/session abuse | Partially hardened | Add browser E2E abuse cases, CSP review, SameSite matrix, mutation CSRF proof, output encoding and dependency policy. |
| Database model | Transitional | Decide native PostgreSQL migration after schema/domain mapping; do not mix ad hoc relational and document assumptions. |
| Financial precision | Risk | Replace floating-point monetary calculations with decimal/minor-unit rules through staged, reconciled migration. |
| Single VPS | Availability risk | Good for early stage; define RPO/RTO, external backups, warm rebuild runbook, then separate DB/storage as load warrants. |
| CI/CD | Incomplete | Require lint, unit, tenant-boundary, migration, dependency, container, and smoke gates before deploy. |

## Completion summary

The ERP is strongest as an internally operated small-firm system with substantial repaired foundations. It is not yet a commercially mature, workflow-complete multi-tenant AECO SaaS. The first product investment should be reliability and workflow connection, followed by document/drawing control and site execution. A broad rewrite would destroy useful work and is not recommended.
