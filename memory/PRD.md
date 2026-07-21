# Design Saga – PRD

**Original problem statement:** Build a SaaS-grade platform for architecture/interior design firms covering CRM, projects, tasks, files, client portal, billing, AI assistant, dashboards. MVP "lite" version covering all modules. Roles: Admin + Employee. Auth: Emergent Google. Integrations: PDF gen, AI (Claude), SendGrid email, Stripe payments. Visual: modern bold + distinctive (delivered as Swiss/editorial with Klein Blue #002FA7 accent + Cabinet Grotesk + IBM Plex Sans).

**Latest expansion (Feb 21, 2026):** **Phase-1 completion sweep — Site Visit Attendance + Payroll → Accounting + RBAC Finance Gate.**

- **Site-visit attendance**: check-in now supports `attendance_type=office|site_visit`; site visits land as `pending_approval` and require HR approval via `POST /api/attendance/{id}/approve`. New HR-only tab `Site Approvals` on `/attendance` with 1-click Approve / Reject.
- **Payroll engine (HR → Accounting loop closed)**: `GET /api/employees/{eid}/salary/preview` computes gross → deductions → additions → net from the stored salary structure + optional bonus / overtime / advance recovery. `POST /api/employees/{eid}/pay-salary` posts a balanced JE (DR Employee Salary · CR Cash/Bank) and stores an idempotent `payroll_runs` doc so the same month can't be paid twice. New "Run Payroll" block appears on the Employee → Salary & Bank tab (visible only to roles with `payroll.create`).
- **RBAC finance gate**: introduced `finance.*` and `payroll.*` permission families. `/api/accounting/*` and `/api/accounts` are router-gated by `finance.read` (Admin/Director/Accountant only — HR blocked, Designer/PM/Employee blocked). `/accounting` frontend route is guarded by `requirePerm="finance.read"` so the menu item hides itself for non-finance roles. Verified live: Designer session 403s on 4/4 finance endpoints, 200s on tasks/projects/dashboard.
- Existing modules preserved (Auth, Projects, Tasks, Employees, Quotations, Leads, Attendance, Accounting). Verified via curl smoke tests. Testing agent NOT run this iteration by user request to conserve AI credits — extensive curl coverage instead.

**Latest expansion (Feb 17, 2026 — session 2):** **Attendance + Accounting modules.**

Attendance (`/app/backend/routes/attendance.py`, `/app/frontend/src/pages/Attendance.jsx`):
- Daily **check-in / check-out** with client IP capture (`x-forwarded-for` aware) — creates/updates one attendance doc per (employee_id, date). Auto-derives half-day when worked <4h.
- **Leave workflow**: apply → HR approve/reject → on approval, back-fills attendance as `leave` for every date in range.
- Configurable **leave rules** (allowances per type, working days per week, week-off days) with sensible defaults (12 casual, 12 sick, 18 earned, …).
- **Monthly sheet** (HR-only) returns per-employee `counts{present,absent,half_day,leave,holiday,week_off}` + `worked_hours` — payroll-ready.
- Endpoints: `/api/attendance/check-in`, `/check-out`, `/me/today`, `/me/summary`, `/monthly`, `/override`, `/leave-rules`, `/meta`; `/api/leaves` CRUD + `/action` + `/balance/{eid}`.
- Frontend tabs: My Attendance · My Leaves · Monthly Sheet (Admin) · Pending Leaves (Admin).

Accounting (`/app/backend/routes/accounting.py`, `/app/frontend/src/pages/Accounting.jsx`):
- **True double-entry**: every financial event lands in `journal_entries` as balanced lines. Wrappers `POST /accounting/income` and `/expense` auto-build the journal so users don't think in DR/CR.
- **Chart of Accounts**: 36-account default (Assets/Liabilities/Income/Expense/Equity) seeded on first read; unlimited custom accounts.
- **Ledgers** derived at read-time (never denormalized): `/ledger/account/{id}`, `/client/{id}`, `/project/{id}`, `/vendor/{id}` — running balance, DR/CR totals.
- **Reports**: `/reports/pl` (period + project filter), `/reports/trial-balance` (Trial DR always == CR).
- **Finance Dashboard**: Cash/Bank per account, month P&L, outstanding, overdue, today's collections, upcoming payments (30d), recent transactions.
- **Payment milestones** per project (fixed amount or % of budget); paying via `/accounting/income` with `milestone_id` marks it paid.
- Vendor master (`/vendors`) — future POs/inventory wire-up-ready.

Testing: **36/36 pytest cases pass** (`/app/backend/tests/test_attendance_accounting.py`), Trial Balance DR=CR verified live in the browser, all previous modules (Auth, Projects, Employees, Tasks, Quotations, RBAC) unaffected.

**Latest expansion (Feb 17, 2026):** **Task Management upgrade + Phase-1 backend refactor.** Backend split into modular `core/` (db, helpers, deps, rbac), `models/`, and `routes/` packages while `server.py` continues to serve all other modules (zero breaking changes). Tasks module rebuilt from scratch:
- **Dual workflows**: Employee tasks (2D/3D/BOQ/site visit/estimation/…) and Agency/Vendor tasks (carpenter/painter/electrician/marble/lighting/…) share one collection but filter independently.
- **Excel-style table** view alongside Kanban with inline editing, bulk update, CSV export, and multi-column filters (project/area/category/priority/status/search).
- **13 granular statuses** (`Pending`, `Selection Required`, `Vendor Required`, `Quotation Requested`, `Ordered`, `Work Started`, `On Hold`, `Inspection Pending`, etc.) that auto-map to 4 Kanban lanes.
- **Unlimited follow-ups** per task with reminder date/time, notes, next-follow-up, assigned employee — reminder-based endpoint feeds the dashboard.
- **Timeline audit** (`timeline[]`) auto-writes on every material change and is never deleted.
- **Custom Areas / Categories per project** (project-scoped `custom_areas`, `custom_categories`) merged with defaults.
- **Future-compat placeholders** (`procurement_link`, `po_id`, `inventory_id`, `vendor_payment_status`) baked into every task doc so procurement/PO/inventory modules can integrate later without a migration.
- Frontend: `/tasks` upgraded with Employee ⟷ Vendor tabs, Kanban ⟷ Table toggle, bulk-select bar, CSV export, new task form with vendor-contact block; new `/tasks/:id` detail page with **Overview · Follow-ups · Timeline · References** tabs.
- Backend regression suite (`/app/backend/tests/test_tasks_module.py`) — **20/20 pass**.

**Latest expansion (Apr 29, 2026):** Quotation module upgraded to **enterprise-grade**...

## User personas
- **Studio Admin** – owns finances, sees full P&L, signs off proposals, sends invoices.
- **Designer/PM (Employee)** – works through projects, tasks, files, drafts quotations.
- **Client** – accesses a token-gated portal to follow progress, view files & invoices.

## Core requirements (static)
1. Multi-module SaaS (CRM → Projects → Tasks → Files → Quotations → Invoices → Portal).
2. Google Auth (Emergent-managed) – first user becomes admin, rest employees.
3. Enterprise quotation engine with BOQ, rooms, materials, payment plan, timeline, terms, versions, approval, PDF.
4. AI assistant (Claude Sonnet 4.5 via Emergent LLM key) – studio Q&A + quotation audit.
5. Premium PDF output (cover, exec summary, scope, BOQ, rooms, materials, costing, payment, timeline, terms, signature).
6. Token-shareable client portal (no auth).

## What's been implemented
**Apr 17 – MVP build**
- Backend: FastAPI + Mongo with Auth, Dashboard, Leads (Kanban + drag-drop + convert), Projects (lifecycle stages), Tasks, Clients, Files, Invoices/Quotations (basic), AI chat, Client portal endpoints, Seed data.
- Frontend: Login (split screen, Klein Blue), Dashboard (KPIs, funnel, alerts, utilization), CRM kanban, Projects + detail with stage tracker, Tasks kanban, Clients table, Invoices/Quotations with live PDF preview, Client portal, AI floating widget.
- PDF via fpdf2 with latin-1 sanitization.

**Apr 29 – Quotation enterprise upgrade**
- 4 quotation types (turnkey/consultancy/execution/hybrid) with type-specific defaults for payment plan, timeline, deliverables.
- BOQ engine: 5 prebuilt template categories (Kitchen, Wardrobe, Electrical, Civil & Finishes, Bathroom) with per-line code/unit/qty/rate/margin/room/brand_tier/vendor.
- Room-wise cost mapping (auto-derived from BOQ room tags).
- Material specification system (Premium/Standard/Budget brand tiers with selectable preference per category).
- Cost summary engine (subtotal → discount → contingency → tax → grand total) recomputed server-side on every save.
- Payment Plan Builder (% must total 100%, derived amounts from grand total, default presets per type).
- Timeline generator with phase/start/duration + visual gantt-like bars.
- Smart Terms blocks (6 default sections, fully editable, reset-to-default).
- Version control (snapshot current; log with grand_total delta vs current).
- Approval workflow (internal + client decisions, status auto-progresses).
- Change orders (description, cost_delta, timeline_delta).
- One-click Convert to Project (auto-creates project + tasks from BOQ categories and timeline phases).
- Cost vs Actual endpoint (compares quoted vs project paid+sent invoices).
- AI Quotation Auditor (3 focuses: missing_items / cost_optimisation / premium_upgrades).
- Premium 10-section PDF (cover, exec summary, scope, BOQ, rooms, materials, costing, payment, timeline, terms, signature).
- Frontend: new `/quotations` list + `/quotations/:id` builder with 10 tabs (Overview, BOQ Builder, Rooms, Materials, Costing, Payment Plan, Timeline, Terms, Versions, Preview).
- Existing modules untouched.

## Backlog (P0 → P2)
- **P0 – Modules 3-5 (HR & Finance core)**
  - Attendance system (check-in/out, IP capture, leave rules)
  - Payroll engine (salary slip PDF, bank transfer sheet, run history)
  - Accounting core (COA, cash/bank book, journal, ledgers, P&L)
  - Expense management (office + site, approval workflow)
- **P0 (carry over)**
  - Stripe payment links on milestones (test key already in pod env)
  - SendGrid email notifications (quote sent, payment due) — needs API key
  - File upload (S3/local) — currently only URL link metadata
- **P1**
  - Drag-drop ordering of payment milestones / timeline phases
  - Per-room photo / mood image upload
  - Vendor master and price book (replace inline vendor field)
  - Multi-tenant org/branch isolation
  - Multi-language PDF (Hindi/regional)
- **P2**
  - Mobile site supervisor app (React Native)
  - WhatsApp daily site updates / approvals
  - Workflow rule builder (auto-escalations)
  - Advanced analytics (profit per project, win-loss analysis)
  - White-label branding for enterprise tier

## Test credentials
See `/app/memory/test_credentials.md`.
