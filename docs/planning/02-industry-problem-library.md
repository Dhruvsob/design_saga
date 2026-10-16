# Report 2 - Architecture Industry Problem Library

## Scoring

- Frequency: D daily, W weekly, M monthly, O occasional.
- Impact: H can cause material delay, loss, compliance/privacy failure, or rework; M causes recurring inefficiency; L is convenience.
- Coverage: E existing usable foundation, P partial/generic coverage, M missing first-class workflow.
- Effort: S up to one focused sprint, M several sprints, L multi-phase/integration-heavy.
- Priorities follow P0 critical, P1 high value, P2 important, P3 optional.

These are product opportunities, not claims that every firm experiences every issue. Firm-size applicability must be validated during customer discovery.

## CRM, pre-design, and contracts

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 1 | Leads are forgotten after first contact; Director/BD; D-H | P | SLA, next action, aging, escalation, email/calendar link | S | P1-high |
| 2 | Duplicate client/leads fragment history; BD/Admin; W-M | P | Normalize, duplicate warning, governed merge | M | P1-high |
| 3 | Lead source ROI is unknown; Director; M-M | P | Campaign/source taxonomy and conversion dashboard | S | P2-medium |
| 4 | Site survey happens before requirements are complete; Architect; W-H | M | Configurable survey checklist with required evidence | M | P1-high |
| 5 | Client briefs live in chats/docs; Architect/Client; W-H | M | Structured requirement questionnaire and signed baseline | M | P1-high |
| 6 | Feasibility assumptions are not approved; Principal; W-H | M | Feasibility register, risks, approvals, expiry | M | P1-high |
| 7 | Proposal scope differs from delivery scope; Director/PM; W-H | P | Versioned scope library and accepted snapshot | M | P1-high |
| 8 | Fee proposals omit reimbursables/taxes; Finance; W-H | P | Rule-based templates and validation | S | P1-high |
| 9 | Quotation revisions lose negotiation history; Director; W-H | P | Immutable versions, delta view, decision log | M | P1-high |
| 10 | Accepted quote does not create a controlled project baseline; PM; W-H | P | Conversion workflow for budget, milestones, deliverables | M | P1-high |
| 11 | Contract dates/renewals/insurance expire unnoticed; Admin; M-H | M | Obligation register and reminders | M | P1-high |
| 12 | Scope changes are agreed informally; PM/Client; W-H | P | Change request -> cost/time impact -> approval -> baseline | L | P1-very high |

## Project governance and resource planning

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 13 | Project stages advance without required deliverables; PM; W-H | P | Stage gates and completeness checks | M | P1-high |
| 14 | Ownership is unclear; Team; D-H | P | RACI by project/stage/deliverable | S | P1-high |
| 15 | Decisions are buried in meeting notes; Team/Client; D-H | M | Decision register linked to task/drawing/change | M | P1-high |
| 16 | Risks have no owner or due date; Director/PM; W-H | M | Project risk register, score, mitigation, escalation | M | P1-high |
| 17 | Dependencies are remembered manually; PM; D-H | M | Finish/start dependencies and blocked-state alerts | M | P1-high |
| 18 | Deadline changes erase accountability; PM; W-M | P | Baseline/current dates and change reason history | S | P1-high |
| 19 | Employees are overallocated; PM/HR; W-H | M | Capacity by week, allocation %, conflicts | L | P1-high |
| 20 | Skills are ignored when staffing; Principal/HR; M-M | M | Skill/experience matrix with project demand | M | P2-high |
| 21 | Planned and actual effort are unknown; PM; D-H | M | Time entry against task/phase, variance | L | P1-high |
| 22 | Utilization hides unbillable necessary work; Director; M-M | M | Billable/nonbillable categories and targets | M | P2-medium |
| 23 | Project health is subjective; Director; W-H | P | Schedule/cost/approval/risk composite with drill-down | M | P1-high |
| 24 | Lessons are not reused; Principal; O-M | M | Closeout lessons, tags, search, template feedback | M | P2-medium |

## Tasks, meetings, calendar, and communication

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 25 | Large tasks hide actionable work; Designers; D-M | P | Subtasks/checklists and completion rules | M | P1-high |
| 26 | Recurring operational work is recreated; Admin/PM; W-M | P | Recurrence engine with exceptions | M | P1-high |
| 27 | Overdue work does not escalate; PM; D-H | P | configurable reminders/escalation with quiet hours | M | P1-high |
| 28 | Assignment is not acknowledged; PM/Employee; D-M | P | accept/decline/request clarification SLA | S | P2-high |
| 29 | Review/rejection is modeled as comments; Designer/Reviewer; D-H | P | submit-review-revise-approve states | M | P1-high |
| 30 | Handover loses context; Employee/PM; W-H | M | transfer checklist, files, decisions, acceptance | M | P1-high |
| 31 | Meetings produce no accountable actions; All; D-H | M | agenda, minutes, decisions, actions, follow-up | M | P1-high |
| 32 | Calendars conflict with site visits/deadlines; PM; D-M | P | availability/conflict check before scheduling | M | P2-high |
| 33 | Personal calendar details leak to colleagues; All; D-H | E | preserve per-user OAuth, private visibility, busy-only sharing | M | P0-critical |
| 34 | Calendar sync failures are silent; All; D-M | P | queue dashboard, retries, reconnect alerts | S | P1-high |
| 35 | Notification volume causes alert fatigue; All; D-M | P | preferences, priority, digest, dedupe | M | P1-high |
| 36 | Chat decisions never enter system of record; PM; D-H | M | email/chat capture to project with consent and classification | L | P2-high |

## Drawings, documents, RFIs, and approvals

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 37 | Site uses superseded drawing; Site/Contractor; D-H | M | drawing register, revision, current stamp, superseded warning | L | P1-very high |
| 38 | Drawing numbers/names are inconsistent; Designer; D-M | M | configurable numbering and metadata validation | M | P1-high |
| 39 | Review responsibility is unclear; Architect; D-H | M | checker/approver workflow and due dates | M | P1-high |
| 40 | Issued packages cannot be reconstructed; PM; W-H | M | immutable transmittal manifest and recipients | L | P1-high |
| 41 | Client approval lacks evidence; Client/PM; W-H | M | portal approval, comments, timestamp, version hash | L | P1-high |
| 42 | PDF markups are detached from revisions; Designer; D-M | M | revision-linked annotation set and resolution | L | P2-high |
| 43 | Large files rely on unsafe public links; Team; D-H | P | S3-compatible object storage and signed URLs | M | P0-critical |
| 44 | Files may contain malware or wrong content; All; D-H | P | MIME/size validation, scan, quarantine, safe download | M | P0-critical |
| 45 | Email attachments create parallel versions; Team; D-H | M | project email filing and canonical document links | L | P2-high |
| 46 | RFIs lack formal responsibility and answer; Site/Consultant; W-H | M | draft-submit-review-official response-close workflow | L | P1-high |
| 47 | Submittals/material samples miss review deadlines; PM/Vendor; W-H | M | submittal register, reviewers, revisions, ball-in-court | L | P1-high |
| 48 | Consultant submissions are not coordinated; Architect; W-H | M | discipline deliverables and coordination matrix | L | P1-high |
| 49 | Municipal approvals and validity dates are missed; PM; M-H | M | approval register, dependencies, expiry alerts | M | P1-high |
| 50 | Closeout documents are incomplete; PM/Client; O-H | M | handover manifest and mandatory completion gate | M | P1-high |

## Client selections and design decisions

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 51 | Selection options are shared in unstructured chats; Designer/Client; D-H | M | selection boards with structured alternatives | L | P1-high |
| 52 | Budget impact is hidden at approval; Client/Finance; W-H | M | live delta to allowance/BOQ | L | P1-high |
| 53 | Lead time is ignored; Procurement/PM; W-H | M | availability and required-by date warning | M | P1-high |
| 54 | Final selection changes without trace; Client/Designer; W-H | M | lock, revision and reapproval | M | P1-high |
| 55 | Finish/colour/model details are incomplete; Site; D-H | M | required attributes by selection category | M | P1-high |
| 56 | Sample approval differs from installed item; Site/Client; W-H | M | approved sample evidence linked to receipt/inspection | L | P1-high |
| 57 | Selection does not update procurement; PM; W-H | M | approved selection -> requisition/BOQ line | L | P1-high |
| 58 | Client delays block project invisibly; Director/Client; W-H | M | decision SLA, reminders and schedule impact | M | P1-high |

## Site execution, quality, safety, and attendance

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 59 | Daily site progress is inconsistent; Supervisor/PM; D-H | M | offline-capable daily report template | L | P1-high |
| 60 | Photos lack project/location/context; Site; D-H | M | capture metadata, category, timestamp, annotation | M | P1-high |
| 61 | Progress percentage has no evidence; PM/Client; W-H | M | BOQ/area/activity progress with evidence | L | P1-high |
| 62 | Site issues have no closure workflow; Site/PM; D-H | M | issue owner, due date, severity, evidence, verify/close | M | P1-high |
| 63 | Snags recur or close without proof; Site/Contractor; D-H | M | snag list, location, before/after evidence, reviewer | M | P1-high |
| 64 | Inspections use informal checklists; Architect; W-H | M | versioned inspection templates and sign-off | M | P1-high |
| 65 | Safety observations are lost; Site; D-H | M | severity, immediate action, escalation and trend | M | P1-high |
| 66 | Offline/weak signal prevents updates; Site; D-H | M | local draft queue, resumable upload, conflict policy | L | P1-high |
| 67 | GPS accuracy causes legitimate check-in failures; Employee/HR; D-H | P | accuracy radius, retry, auditable exception approval | M | P0-critical |
| 68 | GPS spoofing creates false attendance confidence; HR; O-H | P | risk signals and policy; never claim GPS infallibility | L | P1-high |
| 69 | Site visit and office attendance are conflated; HR/PM; D-M | P | visit purpose/project/evidence separate from payroll presence | M | P1-high |
| 70 | Contractor commitments are not tracked; PM; D-H | P | commitment log, promised date, delay reason/escalation | M | P1-high |
| 71 | Measurements are disputed; QS/Contractor; W-H | M | measurement sheets, version, joint verification | L | P1-high |
| 72 | Weekly reports take hours to compile; PM; W-M | M | generate from validated daily records | M | P2-high |

## Procurement, materials, vendors, and contracts

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 73 | Purchase starts without approved need; PM/Finance; D-H | P | requisition and budget-owner approval | M | P1-high |
| 74 | Quotes are compared manually; Procurement; W-H | P | normalized comparison incl. tax/freight/lead time | M | P1-high |
| 75 | Lowest quote hides quality/terms risk; PM; W-H | P | weighted bid evaluation and exception reason | M | P1-high |
| 76 | PO exceeds budget; Finance/PM; W-H | P | committed-cost check before approval | M | P1-high |
| 77 | Partial deliveries are poorly tracked; Site/Procurement; D-H | P | GRN by PO line, balance, rejection | L | P1-high |
| 78 | Bill paid without matching receipt; Finance; W-H | P | PO-GRN-bill three-way match | L | P0-critical |
| 79 | Returns/damages do not adjust liability; Site/Finance; W-H | M | return note, debit note, stock and payable update | L | P1-high |
| 80 | Material consumption/wastage is unknown; PM; D-H | M | issue/consume/return records by site/area | L | P1-high |
| 81 | Vendor compliance expires; Procurement; M-H | P | GST/PAN/bank/insurance expiry alerts | M | P1-high |
| 82 | Bank detail change enables payment fraud; Finance; O-H | P | maker-checker verification and audit | M | P0-critical |
| 83 | Retention is forgotten; Finance/Vendor; M-H | M | retention schedule, release conditions, aging | M | P1-high |
| 84 | Warranty/defect liability dates are lost; PM/Client; M-H | M | warranty register and pre-expiry inspection | M | P1-high |
| 85 | Contractor rates vary without history; QS; W-M | P | effective-dated rate cards and comparison | M | P2-high |
| 86 | Vendor performance is subjective; PM; M-M | P | evidence-based quality/time/commercial score | M | P2-high |

## Finance, accounting, payroll, and office operations

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 87 | Project budget, committed and actual costs differ; Director; D-H | P | one cost-control view and reconciliation rules | L | P1-very high |
| 88 | Profitability ignores staff time; Director; M-H | P | loaded labour cost + external/direct cost | L | P1-high |
| 89 | Milestone invoices are raised late; Finance/PM; W-H | P | trigger from approved deliverable with review | M | P1-high |
| 90 | Receivables follow-up is inconsistent; Finance; D-H | P | aging workflow, promises, reminders, escalation | M | P1-high |
| 91 | Payment receipts are reconciled manually; Finance; D-H | M | bank import/match and exception queue | L | P1-high |
| 92 | Floats cause rounding drift; Finance; D-H | P | Decimal/minor units and reconciliation migration | L | P0-critical |
| 93 | Periods can change after reporting; Finance; M-H | M | period close/lock and controlled reopen | M | P0-critical |
| 94 | GST/TDS handling is inconsistent; Finance; D-H | P | jurisdiction rules reviewed by accountant | L | P0-critical |
| 95 | Expense receipt duplicates pass review; Finance; W-M | P | hash/OCR duplicate warning | M | P2-high |
| 96 | Employee advances remain unretired; Finance/HR; M-H | P | advance ledger, due date, payroll/reimbursement link | M | P1-high |
| 97 | Payroll runs before attendance exceptions resolve; HR; M-H | E | retain blocking controls and visible exception queue | S | P0-critical |
| 98 | Statutory payroll changes are manual; HR/Finance; M-H | P | versioned rule packs and professional review | L | P0-critical |
| 99 | Payslips/bank files lack controlled delivery; HR; M-H | P | encrypted delivery, access log, bank export approval | M | P1-high |
| 100 | Assets issued to staff are untracked; Admin; M-M | M | asset register, custody, maintenance, return | M | P2-medium |

## SaaS, security, reliability, and analytics

| # | Problem / affected role / frequency-impact | Coverage | Improvement, automation, integration | Effort | Priority/value |
|---|---|---|---|---|---|
| 101 | Raw DB calls can bypass tenant scope; All tenants; D-H | P | repository/service boundary plus static/behavioral tests | L | P0-critical |
| 102 | Tenant deletion/export misses linked collections; Admin; O-H | P | collection registry, dry run, legal hold, verification | M | P0-critical |
| 103 | One host is a single failure domain; All; O-H | P | off-site backup, rebuild runbook, staged separation | M | P0-critical |
| 104 | Backup success is assumed without restore; All; M-H | P | automated verification and quarterly drill | M | P0-critical |
| 105 | Queue/scheduler failures are invisible; All; D-H | P | health, dead-letter, age and error alerts | M | P0-critical |
| 106 | Admin cannot see integration health/cost; Admin; D-M | M | per-tenant connection, quota, error and spend dashboard | M | P1-high |
| 107 | APIs return unbounded datasets; All; D-M | P | cursor pagination, limits, indexes, payload budgets | L | P1-high |
| 108 | SaaS plans cannot enforce fair use; Owner; D-M | M | entitlement and metering service, grace policy | L | P1-high |
| 109 | Metrics disagree between screens; Director; W-H | P | governed definitions and reconciliation tests | L | P1-high |
| 110 | AI can expose data or hallucinate actions; All; D-H | P | opt-in, redaction, retrieval ACL, citations, no autonomous posting | L | P0-critical |
| 111 | Accessibility blocks some staff; All; D-M | P | WCAG 2.2 AA audit and keyboard/screen-reader tests | M | P1-high |
| 112 | Mobile web fails under field conditions; Site; D-H | P | responsive/offline/performance test matrix | L | P1-high |
| 113 | No formal retention/export policy; Owner/Client; O-H | M | tenant-configured retention, export, deletion proof | L | P0-critical |
| 114 | Security fixes depend on manual memory; Engineering; W-H | P | CI gates, threat model, release checklist, patch SLA | M | P0-critical |
| 115 | Support cannot diagnose without exposing data; Support; W-H | M | audited impersonation alternative, metadata-only diagnostics | L | P1-high |
| 116 | Product adoption is unknown; Owner; M-M | M | privacy-respecting workflow telemetry and funnel metrics | M | P2-high |

## Highest-value pattern

The repeated operational failure is not the absence of another dashboard. It is the absence of a controlled handoff: lead to project, drawing to issue, selection to procurement, site evidence to completion, approved work to invoice, attendance to payroll, and every external integration back to an auditable tenant/user identity. Roadmap priority should follow those handoffs.
