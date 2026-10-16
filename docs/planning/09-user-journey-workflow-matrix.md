# Report 9 - User Journey and Workflow Matrix

## Measurable coverage model

Do not claim a percentage from screen count. A journey step is “covered” only when it has: usable UI, authorized API, validated persistence, audit/history where material, notifications/integration behavior, automated tests, and production/staging evidence. Score each dimension 0 absent, 1 partial, 2 proven. A workflow is production-ready only if no security/integrity dimension is below 2 and total is at least 12/14.

| Dimension | Proof required |
|---|---|
| UI | Complete create/read/change/error/empty/mobile path |
| API | Validated contract, pagination and idempotency where needed |
| Data | Constraints, tenant scope, migration and reconciliation |
| Authorization | Role plus resource visibility, negative tests |
| Audit/delivery | Actor/state history and required notifications |
| Automated QA | Unit/integration/E2E/concurrency as risk requires |
| Operational | Monitoring, backup/restore, runbook and live/staging evidence |

## Role journeys

| Persona | Trigger -> successful outcome | Current foundation | Critical gaps | Acceptance scenario |
|---|---|---|---|---|
| Director | Lead arrives -> approved scope -> resourced project -> visible profitability/cash/risk -> closeout | Leads, quotations, projects, dashboard, accounting | Requirement baseline, resource plan, risk/decision registers, cost forecast, closeout | One project traces accepted quote, approved changes, labour/direct cost, invoices/receipts and final margin |
| Principal architect | Brief -> concept/deliverables -> drawing review/issue -> client/consultant decisions -> design freeze | Projects, tasks, files, comments | Drawing register, revision/check/approve, transmittal, RFI/submittal, design-freeze gate | Superseded drawing cannot be mistaken as current; issued package and approvals reconstruct exactly |
| Project manager | Project template -> assignments/dependencies -> meetings/site/procurement -> exceptions -> handover | Projects/tasks/calendar/vendors/POs | Dependencies, recurrence, workload, meeting actions, site/RFI/procurement handoffs | Overdue/blocked work escalates; every external commitment has owner/date/evidence |
| Designer | My work -> access current brief/drawing -> produce -> submit -> review/revise -> complete/time record | Tasks, project detail, files, calendar | My Work, controlled revision, review state, checklists, time/effort, handover | Designer sees only assigned/authorized resources and completes a reviewed deliverable without side-channel files |
| Site supervisor | Schedule -> geofence check-in -> offline daily report/photos -> issues/snags -> material receipt -> checkout | Attendance/site visit, tasks, vendors/PO | Offline/site report, GPS exception UX, issues/snags, GRN/inspection | First-attempt check-in handles accuracy honestly; offline records sync once; issue closes with before/after proof |
| Accountant | Approved commercial event -> invoice/bill -> journal -> payment -> reconcile -> close/report | Double entry, invoices, vendor bills/payments, ledgers/P&L | Decimal, period lock, bank reconciliation, GST/TDS, aging and credit notes | Source documents, subledgers, bank and GL reconcile; closed period blocks edits; reversal preserves history |
| HR administrator | Hire -> user/employee link -> attendance/leave -> payroll exceptions -> pay -> offboard | User creation, employees, attendance, leave, payroll | On/offboarding, statutory rules, assets, secure delivery, risk/offline | Owner and employee login work; private data stays scoped; payroll blocks unresolved attendance; offboarding revokes sessions |
| External agency | Invitation -> limited project scope -> submit deliverable/RFI response -> track approval/payment visibility | Vendor/agency records, tasks; portal patterns | External identity/grants, document submission, RFI/submittal, contract/work order | Agency sees only explicitly granted project records and cannot enumerate staff/finance/other projects |
| Vendor | Onboard/compliance -> quote -> PO -> delivery/GRN -> bill -> payment/retention/warranty | Vendor master, bill/payment/ledger, PO | Secure portal, RFQ comparison, GRN/return, bank-change check, retention | Vendor sees own documents/status; bank change needs independent verification; payment cannot exceed matched liability |
| Client portal user | Secure invitation -> view approved progress/current files -> select/approve -> pay -> handover | Token portal, files, invoices | Fine-grained grants/expiry, selection/drawing approval, watermark/download audit, payment link, closeout | Client cannot see internal/private/other-client data; approval is tied to exact version; revoked link stops immediately |

## End-to-end workflow matrix

| Workflow | Owner | Upstream -> downstream records | Current coverage | Target evidence |
|---|---|---|---|---|
| Lead conversion | Director | lead -> brief -> quote -> client/project baseline | Partial | Accepted version and scope become immutable baseline; duplicates handled |
| Design deliverable | Principal | stage -> task -> drawing revision -> review -> transmittal | Missing/partial | Current revision and issue manifest; reviewer and recipient acknowledgment |
| Client selection | Designer | selection options -> approval -> BOQ/budget -> requisition | Missing | Exact option/version, budget delta, due date and lock/change history |
| Site issue | Supervisor | visit/report -> issue/snags -> task -> verification | Missing/partial | Offline evidence, owner/SLA, before/after proof and audit |
| Procurement | PM/Accountant | need -> approval -> RFQ -> PO -> GRN -> bill -> payment | Partial/disconnected | Quantity/value tolerances and three-way match; partial/return/reversal cases |
| Receivables | Accountant | milestone/deliverable -> invoice -> reminders -> receipt -> reconciliation | Partial | Aging/communications, idempotent receipt and bank match |
| Attendance/payroll | HR | check-in/leave/correction -> locked payroll -> journal/bank/payslip | Strong partial | Device/accuracy/offline proof, statutory golden cases, secure delivery |
| Calendar delivery | User | authorized task/event -> queue -> personal calendar/push/email | Partial | Per-user privacy, consent, idempotency, retry/reconnect and delivery telemetry |
| Tenant lifecycle | Platform admin | provision -> operate -> export/suspend/delete | Partial | Collection/object/job inventory, dry run, retention/legal hold and verification |
| Project closeout | PM | final inspection -> snags -> as-built/warranty -> handover -> archive | Missing | Completeness gate, signed handover, retention and searchable lessons |

## Mobile and field acceptance matrix

| Condition | Required behavior |
|---|---|
| 360 px phone | No overlap; primary action and current state visible; tables become purposeful lists, not clipped grids |
| Slow 3G/high latency | Skeleton/progress, bounded payloads, compressed media, no duplicate submission |
| Offline/intermittent | Explicit local draft and queued state; resumable upload; conflict resolution; no false “saved” message |
| GPS uncertainty | Display accuracy, wait/retry, allowed radius policy and auditable manager exception |
| Camera/media | Strip unnecessary metadata where policy requires, preserve evidence hash/time, compress preview and retain original only by policy |
| iOS/Android/PWA | Test permission prompts, background limitations and notification behavior separately; never promise watch delivery |

## Product discovery required

Before Phase 2, interview at least two representatives from each relevant size band: solo/1-4, 5-15, 15-50, and 50-150 staff. Observe real artifacts and quantify delay/rework, not just requested features. Validate terminology, approval authority, document numbering, procurement tolerance, accounting handoff, site connectivity and mobile device constraints.
