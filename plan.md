# Design Saga ERP (v3.6) — Product-Level Audit & Advanced Improvement Plan

## 1) Objectives
- Audit the **existing 16-module ERP** end-to-end (no rebuild) and produce a prioritized, versioned fix/improvement backlog.
- Make the system **production-ready**: tenant-safe, correct calculations, consistent workflows, premium UX, strong RBAC, and test coverage.
- Seed **realistic multi-tenant sample data** to validate flows across CRM→Projects→Tasks→Calendar/Notifications and Finance→Accounting.
- Strengthen **SuperAdmin/Tenant Management** (tenant CRUD, suspend, plan limits, health, isolation verification).
- Keep Google Calendar sync **deferred**; deliver a unified **native calendar + reminders** experience.

---

## 2) Implementation Steps

### Phase 1 — Core POC (Isolation): Multi-tenant + Accounting correctness + Notifications/Calendar emitters
**Goal:** prove the hardest failure-prone core (tenant isolation + JE source-of-truth + event emission) works before broad polish.

**POC actions**
1. Create a **seed script** (idempotent) to generate **2 orgs** (Consultancy + Turnkey), users (Admin/Employee/Accountant), clients, projects, tasks, vendors, quotations, invoices, payments, attendance events, expenses, purchase orders/GRNs, journal entries.
2. Add an **isolation verification script** that:
   - calls key list endpoints with each org context and asserts **no cross-tenant leakage**
   - checks indexed queries use `org_id` filters
3. Add an **accounting verification script** that:
   - asserts Trial Balance balances, Balance Sheet `delta==0` (or recon works), ledger running balances correct
   - checks orphan records (paid invoice without JE, vendor commission reversal correctness)
4. Add a **notifications/calendar emitter smoke test**:
   - create task with due date → notification bell + calendar entry
   - invoice due date/payment → notification + calendar
5. Run scripts; fix until green.

**User stories (POC)**
1. As a SuperAdmin, I can switch between two tenants and never see the other tenant’s records.
2. As an Accountant, I can run Trial Balance and it always balances.
3. As an Admin, I can reconcile a Balance Sheet delta with one action and see diagnostics.
4. As a PM, creating a due-date task triggers a notification and shows on the calendar.
5. As a finance user, recording a vendor commission reversal automatically corrects reports.

**Exit criteria**: Seed + isolation + accounting + emitter scripts pass; key endpoints verified with sample data.

---

### Phase 2 — Deep Audit + Prioritized Report (across all modules)
**Goal:** inspect every screen + endpoint + DB relation with seeded data; produce a ranked backlog.

**Audit steps**
1. Map **frontend pages ↔ API routes ↔ models/collections**; identify missing CRUD, dead UI, disconnected features.
2. Validate calculations: totals, taxes, discounts, milestones, JE postings, ledgers, payroll/attendance math.
3. RBAC: verify backend guards on every write + sensitive read; confirm super-admin boundaries.
4. Multi-tenant: find missing `org_id` filters, cross-tenant global collections, unsafe indexes.
5. UX: tables/forms (filters/search/sort), empty/loading/error states, inconsistent labels, hardcoded dropdowns.
6. Output a **prioritized audit report** (P0/P1/P2) with: scope, reproduction, fix approach, test plan.

**User stories (Audit)**
1. As an Admin, I can complete each module’s core workflow without hitting a dead end.
2. As an Employee, I only see actions I’m allowed to perform.
3. As a finance user, every money-affecting action has an auditable trail.
4. As a PM, I can navigate from client→project→tasks→files quickly via related links.
5. As a SuperAdmin, I can confirm tenant isolation with a single health check.

**Exit criteria**: audit report delivered + top P0 fixes merged + tests added for each P0.

---

### Phase 3 — Data Integrity + Architecture Hardening (cross-module, master data)
**Core work**
1. Enforce `org_id` + RBAC at route layer (shared dependency) and add missing indexes.
2. Master Data: move hardcoded dropdowns to tenant-config collections (stages, categories, payment terms, tax rates, task types, expense categories).
3. Unified **activity/audit timeline** primitives (created/updated/by, status transitions) reused by major records.
4. Repair/guard rails: prevent orphan states (e.g., invoice payment without JE; GRN without PO links).

**User stories**
1. As an Admin, I can configure project stages per tenant and they appear everywhere consistently.
2. As an Accountant, I cannot create a transaction that leaves books unbalanced.
3. As a user, I can see who changed a record and when.
4. As a PM, I can jump from a project to all related invoices/POs/vendors/tasks.
5. As a SuperAdmin, I can run tenant integrity checks and get a clear report.

**Exit criteria**: no known orphan patterns; master data drives all dropdowns; integrity tests pass.

---

### Phase 4 — Core Module Improvements (production-quality workflows)
**Targets**
1. Records: Edit/Archive/Restore/Delete rules + attachments + related records + history.
2. Tasks: assignment clarity, follower/visibility rules, reminders, SLA-like overdue handling, board + list parity.
3. Attendance: policy UX, geo accuracy errors, approval queue, exports, tamper-resistant audit.
4. Projects: lifecycle per tenant, milestones, team roles, health signals, document hub.
5. Quotations/Invoices: mode-specific templates (Consultancy vs Turnkey), remove blanks, consistent PDFs.
6. Vendors: single vendor master, commissions + bills + ledger coherence.
7. Accounting: validation dashboard, duplicate detection, reconciliation workflows, KPI correctness.

**User stories**
1. As a PM, I can set task reminders and they reliably notify me.
2. As HR, I can review and approve outside-geo check-ins with full context.
3. As a Director, I can see project health (budget/progress/risks) at a glance.
4. As a sales user, I can generate a clean quotation PDF with no empty sections.
5. As an Accountant, I can trace any dashboard KPI back to source journal entries.

**Exit criteria**: each module’s “happy path” + key edge cases validated with tests and seeded data.

---

### Phase 5 — Cross-Module Integration (notifications + native calendar + tenant mgmt)
**Work**
1. Unify Notification Center + Calendar: consistent event types, deep links, snooze/mark done.
2. Emitters: tasks, meetings, invoice due, PO/GRN milestones, approvals (attendance/expenses).
3. SuperAdmin panel: tenant CRUD, suspend/reactivate, plan limits, usage counters, tenant health + isolation checks.

**User stories**
1. As a user, I can see all actionable items in one bell and jump to the exact record.
2. As a user, I can view my week across tasks, meetings, invoice due dates in one calendar.
3. As a SuperAdmin, I can suspend a tenant and block logins immediately.
4. As a SuperAdmin, I can set plan limits and see usage warnings.
5. As a SuperAdmin, I can run an isolation check and get PASS/FAIL with details.

**Exit criteria**: unified event model; tenant mgmt features live; regression tests for emitters.

---

### Phase 6 — UI/UX Refinement (product-wide polish)
**Work**
1. Consistent table patterns: filters, sort, pagination, CSV export, empty/loading/error states.
2. Form quality: validation, inline help, smart defaults, reduce clicks, remove dead controls.
3. Navigation consistency; mode-based UI (Consultancy/Turnkey/Hybrid) without feature clutter.

**User stories**
1. As a user, I always understand what to do next on an empty screen.
2. As a user, I can find any record quickly using consistent filters/search.
3. As a user, forms prevent mistakes with clear validation.
4. As a mobile user, critical flows remain usable.
5. As a user, the UI feels fast and consistent across modules.

**Exit criteria**: UI consistency checklist passes; no broken layouts; perceived performance improved.

---

### Phase 7 — Smart Automation + Global Productivity
**Work**
1. Global search improvements + saved views + quick actions.
2. Inline edits where safe + bulk actions (archive/assign/status).
3. Smart reminders (overdue tasks, unpaid invoices, pending approvals).

**User stories**
1. As a user, I can save a filtered view and reuse it daily.
2. As a PM, I can bulk-assign tasks and set due dates in minutes.
3. As finance, I get reminders for unpaid invoices before they become overdue.
4. As HR, pending approvals surface automatically.
5. As an Admin, I can do frequent actions from quick actions without deep navigation.

**Exit criteria**: automation adds measurable speed without feature bloat; all automated actions auditable.

---

### Phase 8 — Final Security / Performance / QA
**Work**
1. Auth/session hardening, rate limits, CSRF/cookie settings, password policy verification.
2. RBAC + tenant isolation test suite (API + UI smoke).
3. Performance pass: indexes, query shapes, payload sizes, frontend bundle hotspots.
4. End-to-end testing with testing agent each phase; fix regressions.

**User stories**
1. As an Admin, I can trust that users cannot access unauthorized records.
2. As a SuperAdmin, I can prove tenant separation for compliance.
3. As a finance user, sensitive reports are protected and audited.
4. As a user, pages load quickly and reliably.
5. As a QA reviewer, I can run tests and get consistent results.

**Exit criteria**: security checklist satisfied; perf targets met; full regression suite green.

---

## 3) Next Actions
1. Implement **seed + isolation + accounting + emitter POC scripts** and run until green.
2. Generate Phase 2 **audit report** from seeded runs (P0/P1/P2 backlog).
3. Begin Phase 3 hardening (org_id/RBAC enforcement + master data) focusing on P0 first.

---

## 4) Success Criteria
- No cross-tenant leakage (automated checks + manual spot checks pass).
- Accounting integrity: TB balances; BS/CF/PL consistent; reconciliation works; orphan detection in place.
- Every module supports complete CRUD + archive/restore where appropriate; no dead ends.
- Unified notifications + native calendar cover core events (tasks, finance, approvals).
- SuperAdmin panel supports tenant lifecycle + plan limits + health/isolation verification.
- UX is consistent, fast, and production-grade; automated tests validate each phase.

---
## PROGRESS LOG (auto-updated)

### Phase 1 — Deep Audit ✅ (complete)
- Seeded 2 tenants via APIs: Atelier Vista (consultancy) + BuildCraft Interiors (turnkey), full business data
- Audit scripts: /app/tests/seed_and_audit.py + /app/tests/flow_audit.py
- Findings: P0 cross-tenant milestone leak, notifications invisible to non-default orgs, cross-org broadcasts, invoice paid ≠ accounting JE, invoice status w/o permission, validation metrics broken (issue_date), unscoped vendor_ratings/commission_settlements, suspended orgs could re-login, no plan limit enforcement, no automated reminder scan

### Phase 2 — Data integrity + architecture ✅ (complete)
- payment_milestones fully tenant-scoped (accounting.py, notifications.py)
- emit() stamps recipient org_id; emit_admins/finance/hr org-scoped; attendance/scan call sites pass org
- Notifications read path = user_id scoped (correct + safe)
- Invoice paid → auto JE (source=invoice_payment) + reversal on un-pay + paid_date + issue_date; permission gate invoices.update
- Milestone paid → auto JE (source=milestone_payment) + reversal; create_income(invoice_id) closes loop
- Orphan repair endpoint: POST /api/accounting/repair/orphan-invoices (verified — repaired 2 legacy orphans)
- Automated notification scan scheduler (startup task, every 6h, all orgs, org-scoped)
- tasks/scan assignee-by-name lookups org-scoped; vendor_ratings/commission_settlements org-stamped
- master data now feeds tasks meta (task_area/task_category) + employees meta (department/designation)

### Phase 3/4 — Tenant management (priority) ✅ backend+UI
- Suspension enforced at login + every request (deps.require_user)
- Plan limits: PATCH /platform/orgs/{id}/limits + enforcement (auth/register 402, create_project 402)
- GET /platform/orgs/{id}/health (counts, usage, warnings, last login)
- GET /platform/isolation-check (PASS/FAIL across 20 collections)
- SuperAdminPanel UI: isolation check card, health modal + plan/limits editor
- Quotation PDFs: org-branded (name/tagline/color), blank sections skipped, consult vs turnkey verified visually

### NEXT
- Phase 3 remainder: verify vendor commission flow, calendar UI check, tasks board UX
- Phase 5: UI/UX refinement pass
- Phase 6: global productivity (saved views/quick actions where valuable)
- Phase 7: security/perf QA + testing agent full run

### Phase 5/6 — UI/UX + productivity ✅
- Tasks board filters compacted to one row (input-flat width overrides)
- Calendar month-nav bug fixed (Aug 31 + 1mo rolled to Oct 1 — now normalises to day 1)
- Calendar verified rendering unified feed: tasks, invoice dues, milestones, holidays
- Employee → ERP Access tab: view linked login, create login (admin, plan-limit aware), change role, activate/deactivate (kills sessions)
- rbac last-admin guard now org-scoped (was counting admins across all tenants)
- AI assistant persona now tenant-branded; ai history user-scoped (verified safe)
- Login page: google button type=button hardening
- Holidays bulk seed corrected (year field) — both orgs seeded
- Global search verified (projects/clients/invoices), notification deep links verified
