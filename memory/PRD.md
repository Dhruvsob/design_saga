# Design Saga – PRD

**Original problem statement:** Build a SaaS-grade platform for architecture/interior design firms covering CRM, projects, tasks, files, client portal, billing, AI assistant, dashboards. MVP "lite" version covering all modules. Roles: Admin + Employee. Auth: Emergent Google. Integrations: PDF gen, AI (Claude), SendGrid email, Stripe payments. Visual: modern bold + distinctive (delivered as Swiss/editorial with Klein Blue #002FA7 accent + Cabinet Grotesk + IBM Plex Sans).

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
