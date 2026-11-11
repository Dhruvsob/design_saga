# GAMAA Architecture ERP — SaaS Product Gap Analysis & Technical Roadmap

Research date: 11/11/2026 (IST). Prepared by Claude (frontend/UX owner) for review by the owner and Codex (backend, multi-tenancy, security and implementation owner).

**Type of work:** research, architecture audit, gap analysis and planning only. No production data was read or changed, no tenant hierarchy was changed, no migration was run and nothing was deployed while preparing this report.

## How to read this report

**Evidence base**

| Source | What was used |
|---|---|
| Live code line | Codex integration branch `codex/integrate-latest-20261110` at `b6d59ef` = production source `a588b05` plus three calendar-privacy commits. Read in its own worktree without modification. **All `file:line` references below point to this commit unless stated otherwise.** |
| Unmerged Claude line | `claude/ux-product-refinement` at `38a7b4c` (three commits not yet on the production line, see Appendix A) |
| Repair tracker | `DESIGN-SAGA-REPAIR-TRACKER.md` on the live line: Canonical Open Backlog and DS-001…DS-121 |
| Measurements | Local disposable QA stack (MongoDB 8 + FastAPI + production build) with a realistic synthetic tenant: 30,000 journal entries, 1,500 clients, 400 projects, 300 vendors, 1,500 vendor bills, 8,000 tasks, 2,000 leads (10/11/2026) |
| Public research | Vendor documentation, help centres and review sites (Appendix B) |

**Labels used:** **Verified** = read in current code or reproduced locally in this pass. **Tracker** = recorded by an earlier session with evidence, not re-run here. **Assumption** = a reasoned estimate that must be confirmed. **Unverified** = not checked in this pass.

**Not done in this pass:** no production database reads (so the real tenant list was not inspected), no penetration test, no load test against FerretDB, no browser run of every module.

---

## Executive summary

1. **The tenant-isolation foundation is genuinely good.** Every business record carries `org_id`. A fail-closed scoped database wrapper injects the tenant filter into finds, counts, updates and aggregations (`backend/core/scoped_db.py:115-197`). Uploaded files are stored per tenant, Super Admin impersonation is per session and audited, each tenant has its own audit hash chain, and 77 backend test files include dedicated isolation suites. **There is no "branch" model anywhere in the code:** independent firms are separate organisations, which is the correct hierarchy.
2. **The platform layer still behaves as if GAMAA *is* Design Saga.** Design Saga is the built-in default organisation that also owns any record missing an `org_id`. The browser title, login screen, API name, Google Calendar events and reminder text all say "Design Saga". Every tenant's employee IDs start with `DS`, and the AI assistant is "Saga AI". Most seriously, **the Super Admin "PLATFORM REVENUE" figure adds up every customer's own accounting income and ranks the top 5 customers by it** (`backend/routes/platform.py:549-593`, `frontend/src/pages/SuperAdminPanel.jsx:139-154`). That is a business-model error and a privacy problem.
3. **The commercial layer is bookkeeping, not billing.** Plans (`starter/pro/enterprise`) are labels only, and billing fields are filled in by hand. Subscription status supports trial, active and expired-to-read-only. There are no GAMAA invoices, payments, renewals, dunning or entitlements.
   - **Plan limits are only partly enforced.** `storage_mb` is never enforced, and converting a lead into a project bypasses `max_projects`.
   - **Phantom modules.** The Super Admin can switch on five modules that have no code at all: inventory, material tracking, site material, labour billing and project costing.
4. **Offboarding is unsafe.**
   - **Tenant purge** is one API call with no export, grace period or confirmation step. It **misses 11 tenant collections and all uploaded files**.
   - **Owner passwords.** The Super Admin types the new tenant owner's password at creation (and on reset), so GAMAA staff know customer passwords.
5. **Operational ceiling.**
   - **One small server.** One 3.9 GB VPS is shared with Tanvika, and GAMAA's containers are capped at about 3 GB.
   - **One API worker.** Rate limits live in process memory, so more workers can't be added yet.
   - **No disaster copy or alerting.** Backups sit on the same host, and nothing alerts anyone when the system fails.

   This is adequate for today's eight tenants but not for selling to many firms. Measured locally, single expensive dashboard and vendor calls can block every tenant on the shared worker.
6. **Product depth is uneven.** Accounting, collections, attendance and payroll are strong; they reflect 120+ repair items. The largest gaps for architecture and interior studios are:
   - a studio **product and material library** with selections and client approvals;
   - **timesheets and project profitability**;
   - **task dependencies and scheduling**;
   - **drawing transmittals and client approvals in the portal**;
   - a **GST CGST/SGST/IGST split with HSN/SAC codes**;
   - **email delivery** of invoices and reminders (none exists).
7. **Integration debt must be cleared first.** Three Claude commits are not on the production line: attendance edge cases, the PIN-unlock speed fix and the Leads fix. They overlap files Codex changed afterwards. A duplicate fix for the same stale test exists on both lines, and `main` is about 129 commits behind.

**Recommended first phase (P0, about 2–3 engineer-weeks plus owner actions): integrate, and make the platform safe to sell.**
1. One integration of the Claude and Codex lines, then the release.
2. Replace cross-tenant "revenue" with commercial metadata.
3. Complete and gate tenant purge: export first, typed confirmation, a scheduled purge, and a collection registry with a test.
4. An automated, OpenAPI-driven cross-tenant isolation regression suite in CI.
5. Time-boxed, reason-logged, read-only-by-default support access.
6. Owner invitation links instead of passwords set by the Super Admin.
7. Consistent limit enforcement, with phantom modules hidden.
8. Owner actions:
   - publish the Google OAuth app;
   - choose an off-site backup and alert destination;
   - separate Tanvika or upsize the VPS;
   - rotate the exposed historic credentials (SEC-01).

---

## Part A — Current system inventory

Status vocabulary: **Implemented** (works, with code evidence) · **Partial** (exists but incomplete for a commercial studio product) · **Broken** (defect found) · **Missing** · **Unverified**.

Scale (Verified): 28 route modules plus 94 inline endpoints in `backend/server.py`, about 425 API endpoints in all. There are 36 pages and 37 shared components, about 53 tenant-scoped collections, about 34k backend and 28k frontend lines, 77 backend test files and 19 Playwright specs.

### A1. Platform / SaaS layer

| Capability | Status | Evidence |
|---|---|---|
| Tenant (organisation) model with `org_id` on records | Implemented | `models/organization.py`, `core/tenancy.py:29`, `core/scoped_db.py` |
| Scoped DB wrapper: tenant filter on find/count/update/delete/aggregate; refuses tenant-unsafe passthroughs | Implemented | `core/scoped_db.py:115-197` (aggregate prepends `$match` at 175-179; `_TENANT_UNSAFE` 194-197) |
| Super Admin: create, update, suspend, deactivate, delete tenant; list users; add admin; reset password; reassign user | Implemented (with risks, see B) | `routes/platform.py:96-543` |
| Plans and limits (`starter/pro/enterprise`; `max_users`, `max_projects`, `storage_mb`) | Partial | Limits stored (`models/organization.py:146-153`). `max_projects` enforced at `server.py:1470` only. `max_users` enforced at `server.py:5048` and `routes/auth.py:607`. `storage_mb` **not enforced**; the global env quota applies instead (`services/local_files.py:18,118`) |
| Module gating (per-tenant module toggles) | Partial | Path→module map in `core/deps.py:139-189`. Toggles exist for modules with no implementation: `inventory`, `material_tracking`, `site_material`, `labour_billing`, `project_costing` (`models/organization.py:33-37`; zero implementation hits in this pass) |
| Subscription state (trial / active / expired → read-only) | Implemented (basic) | `core/subscription.py`; `routes/platform.py:283-318` |
| Platform billing (GAMAA invoices, payments, renewals, dunning) | Missing | Only manual fields in `OrgBilling` (`models/organization.py:69-79`) |
| Platform analytics | **Broken (business-model error)** | Sums every tenant's income journal lines as "platform revenue" plus a top-5 tenant revenue leaderboard (`routes/platform.py:564-583`; UI `SuperAdminPanel.jsx:139-154`) |
| Tenant health snapshot / isolation data check | Implemented (data-hygiene level) | `routes/platform.py:611-701`. Checks `org_id` presence only, not API isolation |
| Impersonation (support access) | Partial | Per-session, audited start/end (`routes/platform.py:736-771`). No reason, expiry, read-only mode or tenant visibility |
| Tenant offboarding (export → purge) | **Broken / Missing** | Purge misses 11 collections and does not delete stored files (`routes/platform.py:368-425`, see B4). No tenant export |
| Public contact requests → platform review | Implemented | `routes/contact.py` (DS-121), `platform.py:352` |
| Tenant self-service onboarding / trial signup | Missing | Tenants are created only by the Super Admin |
| Usage metering (users, storage, AI, API) | Missing | No metering code |
| Tenant-level backup/restore and data export | Missing | Whole-database backups only (tracker: daily, 7-day retention, same host) |

### A2. Identity, access and security

| Capability | Status | Evidence |
|---|---|---|
| Password login (email / employee ID), bcrypt, lockout, session cookies | Implemented | `routes/auth.py:348-411` |
| Personal App PIN with 5-minute idle lock (server-enforced) | Implemented | `core/session_lock.py`, `routes/auth.py:417-556` |
| Workspace-aware login (tenant selector / slug) | Missing | Login resolves across all tenants. Duplicate tenant-local employee IDs (every tenant starts at `DS0001`) yield a 409 "sign in with email" (`routes/auth.py:366-377`) |
| One person in several tenants | Missing | `users.email` is globally unique (`core/indexes.py:16`). Adding an email that exists in another tenant returns "Email already registered" (`routes/auth.py:598`, `platform.py:451`), which also discloses existence |
| RBAC with per-tenant role overrides | Implemented | `core/rbac.py`, `core/deps.py:15-44` |
| Tenant audit log with per-tenant hash chain, verify, export | Implemented | `core/audit.py` |
| Rate limiting | Partial | In-process memory buckets (tracker DB-02); blocks horizontal scaling |
| Secret hygiene | Partial | SEC-01: exposed historical Atlas password/token not yet rotated (Tracker, externally blocked) |
| Upload validation | Implemented | Type sniffing, size and per-tenant quota (`services/local_files.py`). No malware scan (SEC-07) |

### A3. Business modules

| Module | Implemented | Partial / Missing | Evidence |
|---|---|---|---|
| **Dashboard** | Role-aware KPIs, pipeline, alerts, utilisation, My Day, setup checklist | Speed fix (one wave, aggregation, setup-status) exists only on the Claude line | `server.py` `dashboard_stats`; Claude `a4fdfd7` |
| **CRM / Leads** | Kanban stages, notes thread, convert to client + project (atomic claim, no duplicates), sources | Duplicate merge and lead scoring missing (CRM-02). Converted-lead UI fix only on the Claude line | `server.py` leads routes; Claude `38a7b4c` |
| **Clients** | CRUD, archive, client detail with statement PDF (DS-120) | Contacts per client and communication log are minimal (Unverified depth) | `server.py` clients routes |
| **Quotations / BOQ / proposals** | Room-wise BOQ (preset room list), consultancy letter proposals, versions, approval, **change orders**, **cost vs actual**, convert to project, PDF, **AI suggest** | Product library feed, e-signature and client approval via portal missing | `/quotations-adv/*` incl. `/change-order`, `/cost-vs-actual`, `/ai-suggest`; rooms `server.py:273-277` |
| **Projects** | Lifecycle stages, phase templates with fee/dates/deliverables (DS-085), areas and categories, milestones, team, fee structures, archive/restore, share token | Task dependencies, Gantt/timeline, capacity, timesheets and profitability missing | `/projects/*` (28 endpoints) |
| **Tasks / Workboard** | Kanban and list, assignees, follow-ups, bulk update, reminders, visibility rules | Dependencies, subtasks hierarchy, time logs and recurring tasks missing (Unverified for recurring) | `/tasks/*` |
| **Calendar** | Studio/project scopes, events, reminders, personal Google sync with reconnect status | Google OAuth app in **Testing** → 100-user allowlist and 7-day token expiry (owner action) | `/calendar/*`, `core/google_calendar.py`; tracker DS-121 |
| **Drawings** | Register per project, revision upload, approve/reject decision, Excel register | Transmittals, portal approval, preview/compare and retention policy missing | `/drawings/*`, `/projects/{id}/drawings*` |
| **Files / documents** | Tenant-scoped upload/download with validation | No folders/permissions per file, versioning outside drawings, or object storage | `services/local_files.py`, `/files/*` |
| **Site visits / Snags** | Geotagged check-in/out with photos, live map; snags with photo evidence and verified closure | Site diary as a structured daily log (weather, manpower) missing | `/site-visits/*`, `/snags/*` |
| **Vendors** | Directory, documents, ratings, commissions and settlements, ledger, 360 view | Vendor portal and quotation comparison missing | `routes/vendors.py` (38 endpoints) |
| **Procurement** | Purchase orders, GRN, 3-way match, vendor bills and payments, PO PDF | Material library linkage, delivery tracking per project item, RFQ comparison missing | `routes/purchase.py`, `/vendor-bills`, `/grns` |
| **Invoices / Collections** | Invoices with footing to the paisa, payment reminders (PDF + WhatsApp link), collections due with aging, receipts, received payments, receipt PDF | **No email sending**, no payment links/UPI, no GST CGST/SGST/IGST split or HSN/SAC, no e-invoice (IRN) | `server.py` invoices; `routes/money_in.py`; `core/collection_reminders.py` |
| **Accounting** | Chart of accounts, journals/daybook, ledgers, P&L, balance sheet, trial balance, cash flow (with CSV), bank statement import and reconciliation, period close and Excel export, integrity report, cash/accrual basis | TDS returns, credit notes, Tally export, budgets vs actuals at company level, cash-flow forecast missing | `routes/accounting.py` (52), `routes/period_close.py`, `/bank-reconciliation/*` |
| **Expenses / Loans / Advances** | Claims with receipts and multi-level approval, recurring expenses, loans and EMI, employee advances recovered through payroll | Corporate card import missing (low priority) | `routes/expenses.py`, `routes/loans.py`, `routes/employee_advances.py` |
| **Employees / HR** | Profiles, login accounts, documents, warnings, rewards, salary history, revisions and increments, advances, pay salary | Onboarding/exit checklists, appraisal records, document-expiry alerts, self-service profile edits (Unverified) | `/employees/*` (27 endpoints) |
| **Attendance / Leave** | Check-in/out with geofence and office locations, corrections, late approvals, short leave, monthly sheet, monthly paid-leave allowance with automatic LOP, holidays, live map | Leave carry-forward/encashment (HR-03). Joining-date and "today" edge-case fixes only on the Claude line | `routes/attendance.py` (36), `core/attendance_engine.py`; Claude `77119ec` |
| **Payroll** | Attendance-linked preview, runs, correction/reversal with journals, payslips | PF/ESI/PT/TDS are **manual amounts** with no statutory rules, challans or returns (HR-02); no bank payout file | `routes/payroll.py:118-140` |
| **Notifications / Reminders** | In-app notifications with preferences, due/overdue scans, collection reminders, calendar reminders | No email/SMS/WhatsApp-API delivery channel | `core/notifications.py`, `routes/notifications.py` |
| **Client portal** | Read-only project view by share token, client message | No client login, approvals, selections, invoices/payments or drawings sign-off | `/portal/{token}` (2 endpoints) |
| **Reports** | Accounting statements, commission report, drawing register, period workbooks | No report builder, scheduled reports or cross-module project profitability | see above |
| **Masters / Settings** | Master data (stages, types, categories), company branding (logo, colours, signature, stamp), invoice prefixes, bank details, RBAC, audit log | Tenant-configurable employee ID prefix and number formats beyond invoices | `routes/master_data.py`, `routes/organization.py` |
| **AI** | "Saga AI" chat with visibility-aware project context; quotation AI suggest | Via a third-party proxy key (Emergent). No tenant opt-in, metering or cost cap | `server.py:2837-2924`; `/quotations-adv/{qid}/ai-suggest` |
| **Product & material library** | — | **Missing** (no code) | capability scan, Part C |
| **Timesheets / capacity / profitability** | Cost vs actual inside quotations only | **Missing** as a practice-management capability (PRJ-03) | capability scan |

---

## Part B — Critical architectural problems (commercial multi-tenancy)

Ordered by priority. Owner: **Codex** = backend/architecture/integration; **Claude** = frontend/UX.

### B1. GAMAA and Design Saga are conflated (P0/P1)
- **Evidence (Verified):**
  - **Default org.** The default organisation `org_default` is created as "Design Saga" (`server.py:5700-5712`). Records without `org_id` are attributed to it (`core/scoped_db.py:40-45`, `core/tenancy.py:59-60`), and Design Saga is the only undeletable tenant (`routes/platform.py:376-377`).
  - **Product naming.** The browser title, meta description and login screen say "Design Saga" (`frontend/index.html:7,11`, `Login.jsx:81`). So does the API title (`server.py:86`).
  - **Shared texts.** Google Calendar events say "Open in Design Saga" and "Design Saga event" (`core/google_calendar.py:333-348`). Collection reminders say "Design Saga > Accounting" (`core/collection_reminders.py:189`).
  - **Employee IDs.** Every tenant's IDs are `DS0001…` (`routes/auth.py:92,108`).
  - **Default branding and AI.** Design Saga's taupe is every tenant's default colour (`models/organization.py:53`), and the AI assistant introduces itself as "Saga AI".
- **Risk:** Other customers see a competitor's brand in their ERP, calendar and messages. Legacy records without `org_id` would surface inside Design Saga's view instead of failing closed.
- **Fix:**
  - **Platform identity.** Introduce a platform identity (GAMAA name and neutral platform theme) for the public site, login and shell. After login, apply the tenant's own branding.
  - **Remove literals.** Replace shared-text literals with the tenant's display name.
  - **Employee ID prefix.** Make it tenant-configurable; Design Saga keeps `DS`.
  - **Legacy records.** Migrate any `org_id`-less legacy records to an explicit org, then remove the "no `org_id` ⇒ default org" fallback.
  - **Brand rule.** Design Saga's own palette stays exactly as is (brand rule) and simply becomes Design Saga's tenant theme.
- **Migration:** One audited backfill (count first; tracker reports the `isolation-check` PASS state, to be re-run). No data shape change for Design Saga.
- **Owner:** Codex (backend, migration), Claude (shell/login theming).

### B2. Customer accounting revenue presented as platform revenue (P0)
- **Evidence (Verified):** `GET /api/platform/analytics` loops over **all tenants' journal entries** and sums income lines into `revenue_total`, plus a top-5 per-tenant leaderboard (`routes/platform.py:564-583`). The UI labels it "PLATFORM REVENUE" and "REVENUE LEADERBOARD · TOP 5" (`SuperAdminPanel.jsx:139-154`).
- **Risk:**
  - **Wrong commercial picture.** The figure is wrong as GAMAA's commercial data.
  - **Privacy.** Unrestricted platform access to customers' financial records.
  - **Performance.** Full scan of every tenant's journal on each dashboard load.
- **Fix:**
  - **Remove both widgets.** GAMAA revenue must come only from a new platform billing ledger (B6).
  - **Commercial metadata.** Platform analytics should show tenants by plan/status, seats used vs entitled, storage used, renewals due, overdue platform invoices and support tickets.
- **Migration:** None (read-only change).
- **Owner:** Codex + Claude.

### B3. Super Admin data access is not governed (P0)
- **Evidence (Verified):**
  - **Impersonation.** Sets `impersonated_org_id` on the session with an audit start/end (`routes/platform.py:736-771`). There is no reason, ticket, expiry, read-only mode or tenant-visible record. The impersonating Super Admin keeps `*.*` permissions inside the tenant.
  - **Tenant creation.** Takes `admin_password` from the Super Admin (`models/organization.py:85-87`), and `/orgs/{id}/users/{uid}/reset-password` sets a password chosen by the Super Admin (`platform.py:470`), so GAMAA staff know customer credentials.
- **Fix:**
  - **Support-access grants.** Each grant needs a reason and auto-expires (for example 60 minutes). It is read-only unless the tenant owner grants write. It is visible in the tenant's own audit log, with optional tenant notification.
  - **Owner invitations.** Single-use, time-limited set-password links for owners and admins; Super Admin resets send a reset link.
- **Owner:** Codex (+ Claude UI).

### B4. Tenant offboarding is incomplete and unsafe (P0)
- **Evidence (Verified):**
  - **One-call purge.** `DELETE /platform/orgs/{id}?purge=true` hard-deletes in one call (`routes/platform.py:368-425`).
  - **Missed collections.** The explicit purge list misses **11 tenant collections**: `collection_receipts`, `collection_receivables`, `drawings`, `employee_advances`, `payment_reminders`, `period_closes`, `period_exports`, `project_phases`, `reminder_alerts`, `snags` and `vendors`.
  - **Files and safeguards.** No uploaded files are deleted (no file removal in `platform.py`). There is no export, typed confirmation, grace period or pre-purge backup.
- **Risk:** A "deleted" customer's financial and drawing data survives (a broken deletion promise and a privacy liability), while a real customer can be destroyed by one mistaken call.
- **Fix:**
  - **Collection registry.** Derive purge and export lists from a single registry of tenant collections. Add a unit test that fails when a collection used via `sdb` is not registered.
  - **Three-step offboarding:**
    1. **Suspend.**
    2. **Export.** A complete tenant export: JSON or Excel per collection plus a zip of files, with a checksum.
    3. **Scheduled purge** after a retention window, requiring typed confirmation of the tenant slug. Purge also removes the tenant's file folder.
- **Owner:** Codex.

### B5. Limits, plans and modules are inconsistent (P0/P1)
- **Evidence (Verified):**
  - **`storage_mb` not enforced.** It is editable but never read. Uploads use one global `FILE_STORAGE_TENANT_MAX_BYTES` (512 MB) for every tenant (`services/local_files.py:18,118`).
  - **Lead conversion bypasses `max_projects`.** The limit is checked only in `create_project` (`server.py:1470`); `convert_lead_to_project` (`server.py:1102`) and quotation `convert-to-project` do not check it (Verified for lead conversion; quotation path Unverified).
  - **Plans are only labels.** A plan name doesn't drive entitlements.
  - **Phantom modules.** Toggles exist for five modules that have no code (A1).
- **Fix:**
  - **Entitlements service.** One entitlements service (plan → modules, limits, AI credits, support tier) with per-tenant overrides. Enforce it in every create path through one helper.
  - **Storage quota.** Use the tenant's own storage quota.
  - **Module toggles.** Hide toggles for unimplemented modules until they exist.
- **Owner:** Codex (+ Claude Super Admin UI).

### B6. No platform billing domain (P1)
- **Evidence (Verified):** Only free-text billing fields exist (`OrgBilling`, `models/organization.py:69-79`). Subscription status is set by hand (`platform.py:283-318`).
- **Fix:** A separate platform schema, never mixed with tenant accounting:
  - **Collections.** `platform_plans`, `platform_subscriptions`, `platform_invoices`, `platform_payments` and `platform_events`.
  - **Lifecycle.** States: trial → active → grace → read-only → suspended → cancelled.
  - **GAMAA's invoices.** GAMAA's own GST invoices and receipts (GAMAA's GSTIN, sequence and PDF).
  - **Reminders and recovery.** Renewal reminders, dunning and reactivation.
  - **Payments.** Manual payments first, with a gateway later (decision G5).
- **Owner:** Codex (+ Claude UI).

### B7. Login and identity model is not multi-tenant friendly (P1)
- **Evidence (Verified):**
  - **Employee ID logins.** Tenant-local IDs collide across tenants, and login falls back to "use your email" (`routes/auth.py:366-377`).
  - **One email, one tenant.** Email is globally unique (`core/indexes.py:16`), so one person cannot belong to two companies.
  - **Existence disclosure.** The duplicate-email error discloses that the address exists in another tenant.
- **Fix:**
  - **Workspace-aware sign-in.** Use a workspace URL (`gamaa.in/w/<slug>`, later subdomains) so employee-ID login is unambiguous.
  - **Memberships.** A `memberships` model (user ↔ org, role per org) with a workspace switcher.
  - **Neutral error.** A generic "cannot use this email" message.
- **Owner:** Codex (data model), Claude (sign-in and switcher UI). Decision G2/G3.

### B8. Cross-tenant performance interference (P0/P1)
- **Evidence:**
  - **Single worker (Verified).** One uvicorn worker (`backend/Dockerfile:26`), with rate limits in process memory (Tracker DB-02).
  - **Blocking work (measured locally, Verified).** bcrypt PIN/password checks ran on the event loop and blocked every other request for about 0.4 s. Dashboard stats shipped the whole journal to Python (859 ms on the synthetic tenant), `/vendors` ran one query per vendor (696 ms for 300 vendors), and the admin setup checklist downloaded four full lists (462 KB).
  - **Prod latency (Tracker DB-01).** Production was fine on 09/11: max 234 ms over 24 h on small data.
- **Risk:** One large tenant's heavy page slows every other customer. FerretDB-over-PostgreSQL makes each round trip costlier than MongoDB.
- **Fix:**
  - **Integrate the existing fix.** Claude's `a4fdfd7` covers bcrypt in a thread, a concurrent dashboard, database-side sums, the vendor N+1 and the setup-status endpoint.
  - **Next steps.** Then a shared rate-limit store (Redis or the database) so the API can run 2–4 workers. Move scheduled jobs to a separate worker process, and add per-tenant request timing to the access log.
- **Owner:** Codex.

### B9. Backups, restore and monitoring (P0 before paid onboarding)
- **Evidence (Tracker):**
  - **Backups.** Daily database and file backups with checksums and a tested isolated restore. They have 7-day retention **on the same host**; off-server replication (OPS-02) and external alerting (OPS-03) are externally blocked.
  - **Per-tenant tooling.** No per-tenant restore or export.
- **Fix:**
  - **Off-site copies.** Encrypted off-site copies (any S3-compatible bucket) with 30–90-day retention.
  - **Alerting.** External uptime, 5xx, disk and backup alerting.
  - **Per-tenant restore.** Via the B4 export into a staging tenant.
- **Owner:** Codex + owner decision G8.

### B10. Shared VPS capacity (P0 decision / P1 work)
- **Evidence (Tracker):**
  - **Shared memory.** The VPS has 3.9 GB of RAM shared with Tanvika Nexus (ClamAV was rejected for lack of memory).
  - **Container caps.** Compose caps sum to about 3.0 GB for GAMAA (`docker-compose.yml`: postgres 1.5 GB, ferretdb 512 MB, backend 768 MB, web 128 MB, caddy 128 MB).
  - **Disk.** About 70% used after log compression.
- **Assumption:** The current host can serve roughly 5–15 small studios (up to about 20 active users each) with light concurrency. Beyond that, or with drawing-heavy tenants, memory and disk become the limit before CPU.
- **Fix:** Move GAMAA to its own VPS sized at about 8–16 GB RAM, or move Tanvika. Put uploads on object storage (Part C, Drawings). No Kubernetes or microservices are needed at this stage.

### B11. AI data flow and cost control (P1)
- **Evidence (Verified):**
  - **Proxy key.** `/api/ai/chat` sends visible project names, stages and client names to a model through a third-party proxy key (`EMERGENT_LLM_KEY`, `server.py:28,63,2882-2886`).
  - **No controls.** There is no tenant opt-in, usage limit or metering, and the persona is "Saga AI".
- **Fix:**
  - **Tenant controls.** Tenant-level opt-in and a monthly AI credit per plan.
  - **Direct provider.** A direct, contracted provider integration with a data-processing agreement.
  - **Logging and isolation.** Per-tenant usage logs, and never cross-tenant retrieval (Part D).

### B12. Isolation is verified by data checks, not by API tests (P0)
- **Evidence (Verified):** `GET /platform/isolation-check` checks only that records have a valid `org_id` (`platform.py:665-701`). Isolation tests exist for specific modules (77 test files), but nothing enumerates **every** route.
- **Fix:** An OpenAPI-driven CI suite on a disposable database:
  1. Seed tenants A and B.
  2. For every route that has a path ID, call it with tenant A's session and tenant B's object IDs, and expect 403/404. Lists, exports, PDFs and file downloads must never contain B's IDs.
  3. Include Super Admin and support-access paths.
- This complements the tracker's existing manual/live evidence and follows the OWASP guidance that the tenant must come from the authenticated context, never from client input (Appendix B).

### B13. Background jobs and integrations isolation (P1 audit)
- **Evidence (Verified):** Scheduled jobs and integrations use the raw `db`:
  - collection reminders (`core/collection_reminders.py:310-339`);
  - Google sync (`core/google_calendar.py:273-666`);
  - recurring expenses (`server.py:5919-5934`);
  - notifications (`core/notifications.py:135-139`).

  Spot checks show explicit `org_id`/owner filters (for example `server.py:5934`, `routes/notifications.py` owner filter). Codex's latest commits further isolate Google sync per person (`baf946c`, `2095f8a`, `b6d59ef`).
- **Fix:** Add each job to the B12 suite with two-tenant fixtures, and give jobs a per-tenant loop with a tenant-scoped context instead of raw queries where possible.

### B14. Data residency of files (P2)
- **Evidence (Verified):** Files live on the VPS disk under per-tenant folders (`services/local_files.py:99-119`). This is fine now, but drawing libraries will grow quickly.
- **Fix:** Migrate to S3-compatible object storage with tenant prefixes, short-lived signed URLs, per-tenant quota accounting and lifecycle rules. Keep the same `storage_key` interface so the migration is mechanical.

### Shared database vs separate databases — recommendation
- **Keep a shared database with enforced tenant isolation** for all standard plans. The existing scoped wrapper, per-record `org_id`, per-tenant audit chain and planned API isolation suite give strong isolation at the lowest operating cost, which suits a small team on one VPS.
- **Do not move every tenant to its own database now.** That would multiply migrations, backups, index builds and connection pools for no current customer requirement.
- **Hybrid later:** for an enterprise customer that contractually requires it, route that tenant's scoped collections to a separate database name (the wrapper is the single choke point, so this is feasible). Back it with its own backup and restore set. Price it as an enterprise add-on.

---

## Part C — Advanced feature opportunities

Priority uses the roadmap tiers (P0–P3). Complexity: **S** ≤ 1 week, **M** 1–3 weeks, **L** 3–6 weeks, **XL** over 6 weeks (one engineer; Assumption).

| Module | Existing capability | Missing / proposed feature | Business value | Complexity | Dependencies | Priority |
|---|---|---|---|---|---|---|
| Platform | Tenant CRUD, status, manual billing fields | Platform billing ledger: plans, subscriptions, GAMAA invoices, renewals, dunning, reactivation (B6) | Required to sell | L | Entitlements (B5) | P1 |
| Platform | Contact requests | Trial signup → demo tenant → owner invite → setup checklist → CSV employee import | Faster sales, less manual setup | M | Invitations (B3), entitlements | P1 |
| Platform | Whole-DB backups | Tenant export (JSON/Excel + files zip) and staging restore | Portability, trust, offboarding | M | Collection registry (B4) | P0/P1 |
| Platform | — | Usage metering per tenant/month (seats, storage, AI calls, PDFs) | Fair plans, upsell signals | M | Entitlements | P1 |
| Platform | — | In-app announcements and support tickets linked to support-access grants | Support operations | M | B3 | P2 |
| Identity | Email/ID login | Workspace URL, memberships and workspace switcher (B7) | Sell to firms with shared consultants; clean employee-ID login | L | Decision G2/G3 | P1 |
| Identity | — | Optional 2FA (TOTP) for owners/admins; Google sign-in per tenant | Security expectation of buyers | M | — | P2 |
| CRM | Kanban, notes, convert | Duplicate detection/merge, follow-up cadence, source ROI report | More conversions | M | — | P2 |
| Clients | CRUD, statement PDF | Multiple contacts, communication log, client approvals history | Relationship clarity | M | Portal | P2 |
| Quotations | BOQ, proposals, versions, change orders, cost vs actual | Pull items from the Product Library; e-sign acceptance in portal; margin per line | Faster, consistent quotes | M | Product Library, portal | P2 |
| **Product & Material Library (new)** | — | Tenant-owned catalogue with manufacturer, supplier (vendor), category, model/SKU, images, specs, dimensions, finish, price history, warranty, datasheets, alternatives; web-clipper/URL import later | Studios reuse favourite products; core differentiator vs generic ERPs (Programa/Houzz Pro have it) | L | Object storage, vendors | P2 |
| **Project selections (new)** | Project areas exist | Room/area-wise selections from the library → client approval (portal) → BOQ lines → PO lines → delivery/installation status; price snapshot per selection; approved substitutions | Single flow from design intent to procurement; fewer errors | XL | Library, portal approvals, PO | P2 |
| Projects | Phases, milestones, areas, fee structures | Task dependencies plus timeline/Gantt view with phase bars and milestone diamonds; baseline vs actual dates | Delivery predictability | L | — | P2 |
| Projects | Cost vs actual in quotations | **Timesheets** (by project/phase/activity; billable vs non-billable; weekly approval) | Know where time goes; basis for profitability and fee billing | L | — | P2 |
| Projects | — | Capacity planning (people × weeks) and workload heatmap | Avoid overload, staff projects realistically | L | Timesheets | P2 |
| Projects | Fee structures, invoices | Project profitability: fees billed/received vs labour cost (timesheets × cost rate) + vendor costs + expenses | Owner's #1 business question | M | Timesheets | P2 |
| Projects | Change orders (quotations) | Variations register linked to client approval and invoices | Protect fees on scope creep | M | Portal approvals | P2 |
| Projects | — | RFIs/site queries (validate demand first, DOC-02) | Contractor coordination | M | — | P3 |
| Drawings | Register, revisions, decisions, Excel | **Transmittals** (issue sets with purpose, recipients, acknowledgement, PDF); portal sharing and client sign-off; PDF preview; superseded watermarking | Professional document control expected by clients/contractors | M | Object storage, portal | P2 |
| Drawings | — | Visual compare of two PDF revisions (overlay) | Catch unintended changes | M | Preview | P3 |
| Files | Per-tenant local files | Object storage, folders per project, retention policy, virus scan when memory allows | Scale and safety | M | Decision G9 | P2 |
| Site | Visits with photos, snags | Structured daily site diary (manpower, weather, deliveries, issues), snag export for contractors | Site accountability | M | — | P3 |
| Procurement | PO, GRN, 3-way match, bills | RFQ to several vendors with comparison; expected delivery tracking per selection | Better prices, on-time delivery | M | Product Library | P2 |
| Invoices | Invoices, reminders (PDF/WhatsApp link) | **Email delivery** (invoices, reminders, payslips) via a transactional email provider | Basic expectation; removes manual sending | M | Decision G10 | P1 |
| Invoices | Single tax amount | **GST CGST/SGST vs IGST** by place of supply, HSN/SAC per line, GSTR-1-ready export | Compliance for Indian studios (ACC-02) | M | Tenant/client state fields | P1 |
| Invoices | — | Payment links/UPI QR on invoices (gateway optional) | Faster collections | M | Decision G5 | P2 |
| Invoices | — | E-invoice (IRN) only for tenants above the ₹5 cr turnover threshold | Compliance for larger firms | L | GST split | P3 |
| Accounting | Statements, period close, bank rec | TDS on vendor bills with 194C/194J sections and quarterly summary; credit notes; Tally export | CA-friendly books | M | Decision ACC-05 | P2 |
| Accounting | Cash flow statement | Deterministic cash-flow forecast from collections due, bills, payroll and loans | Plan cash months ahead | M | — | P2 |
| Accounting | — | Budgets vs actuals by account and by project | Spending control | M | — | P2 |
| HR | Profiles, documents, warnings, rewards, revisions | Onboarding/exit checklists, document-expiry alerts, lightweight appraisal notes (no automated scoring) | Smoother HR, fewer misses | M | — | P2 |
| Payroll | Manual PF/ESI/PT/TDS amounts | Statutory rules (PF/ESI/PT by state, TDS slabs), challan and return summaries, bank payout file | Removes spreadsheet work (HR-02) | L | Decision HR-02 | P2 |
| Attendance | Geofence, corrections, monthly allowance | Leave carry-forward/encashment, comp-off rules (HR-03) | Policy completeness | S | Decision HR-03 | P2 |
| Notifications | In-app | Email + WhatsApp Business API channels with per-user preferences and tenant templates | Reach people where they are | M | Providers (G10) | P2 |
| Client portal | Read-only view + message | Client login (magic link), approvals (drawings, selections, change orders), invoices and receipts, documents | Fewer emails/calls; competitive parity (Houzz Pro, Programa) | L | Approvals model | P2 |
| Reports | Accounting + registers | Saved report views, scheduled email reports, project portfolio report | Management visibility | M | Email | P3 |
| Mobile | Responsive web | PWA install + offline-tolerant attendance/site capture | Field use | M | — | P3 |

**Studio Product Library — proposed data model (Assumption, for Codex review)**

| Collection | Key fields | Notes |
|---|---|---|
| `products` | org_id, id, name, brand, category, model/SKU, specs{}, dimensions, finish, images[], datasheets[], warranty, default_vendor_id, status (active/discontinued), tags | Tenant-owned; images/datasheets via file storage |
| `product_prices` | org_id, product_id, vendor_id, price, currency, valid_from/to, source (quote/PO/manual), quote_file | Append-only price history |
| `project_selections` | org_id, project_id, area, product_id, **snapshot** (name/spec/price at selection), qty, unit, status (proposed → client_approved/rejected → ordered → delivered → installed), alternatives[], approval_id | Snapshot keeps history stable when the library changes |
| `approvals` (shared) | org_id, project_id, subject_type (drawing_revision/selection/change_order), subject_id, requested_to (client contact), decision, comment, decided_at, channel (portal) | One approvals model reused by drawings, selections and variations |

Flow: Library → Selection (by area) → Client approval (portal) → BOQ/estimate line → PO line → GRN/delivery → Installed. Budget impact = Σ(approved selections) vs project budget.

---

## Part D — AI opportunities

Principles:
- **Deterministic first.** Use business rules wherever they suffice.
- **Tenant opt-in.** AI is opt-in per tenant and metered per plan.
- **Tenant-only context.** Context is built only from the requesting user's permitted, tenant-scoped records.
- **No cross-tenant artefacts.** No shared embeddings, logs or prompts across tenants.
- **No unattended financial changes.** AI never posts, edits or deletes financial records. It produces **drafts** that a permitted user approves, and every acceptance is audited.

| Use case | Benefit | Data needed | Complexity | Model cost | Privacy / isolation | Error risk | Human approval | Plan |
|---|---|---|---|---|---|---|---|---|
| Bill / receipt / quotation **document extraction** → draft expense, vendor bill or price entry | Removes typing; feeds the Product Library prices | Uploaded PDF/image | M | Medium (vision) | Document stays in tenant; provider DPA | Medium (amounts, GSTIN) | **Mandatory** review screen; validation against totals | Pro+ |
| **Project summary** (status, overdue, money, next steps) | Owner/PM briefing in seconds | Project, tasks, milestones, collections | S | Low | Visibility-aware context (already pattern in `ai/chat`) | Low–medium | Informational | Pro+ |
| **Meeting notes → tasks** (paste or audio transcript) | Faster follow-up | Notes text | M | Low–medium | Tenant-only | Medium (assignees/dates) | User confirms each task | Pro+ |
| **Reminder / client message drafting** (payment follow-ups, approval nudges) | Polite, consistent messages | Invoice/collection facts | S | Low | Only the facts of that record | Low | User sends | All paid |
| **Natural-language search** ("drawings for Villa Serena issued for construction") | Find anything quickly | Tenant index | M | Low–medium | Per-tenant index; filters enforced server-side | Low (retrieval) | — | Pro+ |
| **Product / vendor comparison** (specs, price history, lead time) | Better selections | Library + price history | M | Low | Tenant-only | Medium | Informational | Pro+ |
| **Financial insights** in plain language (why cash is low; top overdue) | Understandable finance | Reports (already computed deterministically) | S | Low | Finance permission required; opt-in for financial context | Medium (explanations) | Informational; numbers come from reports, not the model | Pro+ |
| **Workload suggestions** (rebalance tasks) | Avoid overload | Tasks, timesheets, capacity | M | Low | Avoid surveillance framing; no scoring of individuals | Medium | Manager decides | Enterprise |
| **Project delay prediction** | Early warning | Historical phase durations (needs months of timesheet/phase data) | L | Low | Tenant-only models/features | High early on | Informational | P3 later |
| Expense categorisation, duplicate detection, missing-entry and budget-overrun alerts | Clean books | Journals, bills | S | **None — rules** | — | Low | Flags only | All |
| Attendance anomaly flags | Catch errors | Attendance | S | **None — rules** | No invasive monitoring | Low | Flags only | All |

**Implementation notes (Assumption):**
- **Provider.** Replace the proxy key with a direct, contracted provider integration (for example the Anthropic API) whose models are configurable, and log tokens per tenant and month.
- **Credits.** Enforce monthly credits from entitlements.
- **Redaction.** Strip bank details and IDs from prompts by default.
- **Retention.** Keep AI request logs in the tenant scope with retention limits.

---

## Part E — SaaS commercial model (no prices)

### E1. Plan structure (configurable, entitlement-driven)

| Entitlement | Starter | Professional | Enterprise |
|---|---|---|---|
| Users (seats) | Small team cap | Larger cap | Custom |
| Active projects | Cap | Higher cap | Custom |
| Storage | Base quota | Larger quota | Custom + add-on blocks |
| Modules | Core: CRM, clients, quotations, projects, tasks, calendar, invoices, attendance | + accounting, payroll, procurement, drawings, portal approvals | + product library advanced, multi-workspace, SSO/2FA policy |
| AI credits / month | None or trial | Included allowance | Custom |
| Integrations | Google Calendar | + email/WhatsApp channels | + API access |
| Support | Email, business hours | Priority | Named contact, onboarding |
| Data isolation | Shared DB | Shared DB | Optional dedicated database (hybrid add-on) |

Every value lives in `platform_plans` and can be overridden per tenant. Turnkey vs consultancy business modes continue to preset modules.

### E2. Subscription lifecycle (configurable defaults; decision G7)
1. **Trial** (for example 14 days) with sample data in a separate demo tenant.
2. **Active** (monthly or annual).
3. **Renewal reminders** at T-30, T-7 and T-1.
4. **Grace** (for example 7 days) with full access and a banner.
5. **Read-only** (already implemented).
6. **Suspended** (login only to export and pay).
7. **Cancelled.**
8. **Retention window** (for example 90 days), then export offer and scheduled purge (B4).

**Upgrades** apply immediately (pro-rata credit on GAMAA's invoice). **Downgrades** apply at the next renewal and are blocked while usage exceeds the target plan's caps. **Reactivation** restores state without data loss.

### E3. Lifetime licensing — sustainable options

| Option | What the customer buys | What is NOT included | Recommendation |
|---|---|---|---|
| **Perpetual software licence (self-hosted)** | Right to run a version on own server | Hosting, updates beyond the version, support | **Not recommended now.** One codebase plus FerretDB ops make customer-hosted installs costly to support |
| **Lifetime hosted access** | One-time licence fee for the software on GAMAA's cloud, **plus mandatory annual hosting & maintenance (AMC)** that includes a defined storage/user allowance, security updates and support | Unlimited storage or users; free infrastructure forever; major new paid modules | **Offer if needed for the Indian market**, with written caps and AMC terms |
| **One-time setup / onboarding fee** | Data migration, configuration, training | — | Charge separately from subscriptions |
| **Storage / seat add-ons** | Extra blocks | — | Monthly or annual add-on lines |
| **Upgrade entitlement** | Included while subscription/AMC is active | After AMC lapses: stays on last version read-only (hosted) or no updates | State explicitly in the contract |

### E4. Onboarding flow (target)
1. **Enquiry.** Public contact form (exists).
2. **Demo.** A shared, resettable demo tenant.
3. **Plan selection.** Super Admin creates the tenant from a plan; entitlements are applied.
4. **Owner invitation.** A set-password link (B3).
5. **Company setup.** Logo, address, GSTIN, bank details, prefixes; the checklist exists.
6. **Employee onboarding.** CSV import plus invitations.
7. **Activation.** First project from a phase template.

The Super Admin keeps exclusive control of plans, entitlements, tenant status, platform invoices, support-access grants, purge and platform analytics.

### E5. Operational requirements before selling
- **Platform identity.** Platform brand separation (B1).
- **Billing.** Billing ledger (B6).
- **Data protection.** Off-site backups and alerting (B9), plus the isolation CI suite (B12).
- **Infrastructure.** Its own VPS (B10).
- **Policies.**
  - Customer contract and privacy policy, including a sub-processor list (hosting, email, AI provider).
  - Support SLA per plan.
  - Incident-response note.
  - Release notes channel.

---

## Part F — Development roadmap

Effort is in engineer-weeks for one developer (Assumption). Owner: **C** = Codex (backend, architecture, integration, security); **Cl** = Claude (frontend/UX); **O** = owner action.

### P0 — Integrate and make the platform safe to sell (about 2–3 weeks + owner actions)

| # | Item | Owner | Effort | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| P0.1 | Integrate `claude/ux-product-refinement` (`77119ec`, `a4fdfd7`, `38a7b4c`) into the Codex integration line. Resolve overlaps in `attendance_engine.py`, `server.py`, `App.js`, `AppPinLock.jsx`. Drop the duplicate test fix (`7761f56`) in favour of Codex's DS-120 CDX-03. Fast-forward `main` to the release | C (+Cl review) | 0.5–1 | — | One release branch; backend gate and Playwright suite green; tracker DEPLOY entry; `main` = release |
| P0.2 | Remove cross-tenant revenue and leaderboard. Platform dashboard shows commercial metadata only | C + Cl | 0.5 | — | No platform endpoint reads tenant financial collections; test asserts it |
| P0.3 | Collection registry → complete export and purge (files included), typed confirmation, scheduled purge after retention | C | 1–1.5 | — | Unit test fails if a scoped collection is unregistered; purge of a two-tenant fixture leaves zero B records/files and all A records |
| P0.4 | OpenAPI-driven cross-tenant isolation suite in CI (two seeded tenants; every ID route; lists, exports, PDFs, files; Super Admin/support paths) | C | 1–1.5 | — | Suite runs in CI; any cross-tenant 200 fails the build |
| P0.5 | Support-access grants (reason, expiry, read-only default, tenant-visible audit) | C + Cl | 1 | — | Expired grant returns 403; read-only grant blocks writes; tenant audit shows each access |
| P0.6 | Owner/admin invitations and reset links; remove Super Admin-chosen passwords | C + Cl | 0.5–1 | Email channel (or copyable one-time link until then) | No API accepts a Super Admin-chosen password for a tenant user |
| P0.7 | Consistent limits: `max_projects` on every create path, per-tenant storage quota, hide phantom modules | C + Cl | 0.5 | — | Tests for each create path; storage quota follows the tenant setting |
| P0.8 | Publish the Google OAuth app (or allowlist all employees) | O | hours | — | Employees connect; no 7-day expiry |
| P0.9 | Off-site encrypted backups and external alerting (OPS-02/03) | O + C | 0.5 | Provider choice | Restore drill from off-site copy recorded |
| P0.10 | Rotate exposed historic credentials (SEC-01) | O | hours | — | Secret inventory updated |

### P1 — Tenant management, subscriptions and essential workflows (about 6–9 weeks)

| # | Item | Owner | Effort | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| P1.1 | Platform identity: GAMAA public/login/shell brand, tenant theme after login, tenant display name in shared texts, configurable employee ID prefix, legacy `org_id` backfill and removal of the default-org fallback | C + Cl | 1.5–2 | P0.1 | No "Design Saga" literal outside Design Saga's own tenant data; Design Saga's palette unchanged; isolation check PASS with fallback removed |
| P1.2 | Entitlements service (plan → modules, limits, AI credits, support) with per-tenant overrides | C + Cl | 1–1.5 | P0.7 | All gates read entitlements; Super Admin edits plans and overrides |
| P1.3 | Platform billing ledger, GAMAA invoices/receipts, renewal reminders, grace → read-only → suspension, reactivation | C + Cl | 2–3 | P1.2, email channel | End-to-end test of the full lifecycle on a fixture tenant; platform revenue derives only from this ledger |
| P1.4 | Workspace-aware sign-in and memberships with switcher | C + Cl | 1.5–2 | Decision G2/G3 | Same email in two tenants works; employee-ID login is unambiguous per workspace |
| P1.5 | Onboarding: trial/demo tenant, invitation, CSV employee import | C + Cl | 1–1.5 | P0.6 | New firm reaches "first project" without Super Admin intervention beyond approval |
| P1.6 | Usage metering (seats, storage, AI, PDFs) and Super Admin usage view | C + Cl | 1 | P1.2 | Monthly usage per tenant visible and exportable |
| P1.7 | Transactional email channel (invoices, reminders, payslips, invitations) with tenant sender name | C + Cl | 1 | Decision G10 | Delivery logged per tenant; bounces visible |
| P1.8 | GST CGST/SGST vs IGST by place of supply, HSN/SAC on lines, GSTR-1-ready export | C + Cl | 1.5–2 | Decision ACC-02 | Accountant-approved fixtures foot to the paisa |
| P1.9 | Shared rate-limit store, 2–4 API workers, separate job worker, per-tenant timing in the access log | C | 1 | Infra decision G8 | Load test: one heavy tenant does not raise others' p95 above budget |

### P2 — Studio depth: projects, product library, drawings, HR, accounting (about 12–18 weeks; can run in parallel streams)

| # | Item | Owner | Effort | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| P2.1 | Object storage migration (tenant prefixes, signed URLs, quotas, lifecycle) | C | 1–1.5 | G9 | All file paths served from object storage; old disk files migrated with checksums |
| P2.2 | Product & Material Library (data model above) | C + Cl | 3–4 | P2.1 | Library CRUD, images and datasheets, price history, tenant-isolated, covered by P0.4 suite |
| P2.3 | Project selections → shared approvals model → BOQ → PO → delivery status | C + Cl | 3–4 | P2.2, P2.6 | One selection traceable from library to installed with an audit trail |
| P2.4 | Timesheets (billable/non-billable by phase), weekly approval, cost rates | C + Cl | 2–3 | — | Hours roll up to phases and projects; approval locks entries |
| P2.5 | Project profitability and capacity planning | C + Cl | 2 | P2.4 | Profitability per project matches source documents; capacity heatmap per person/week |
| P2.6 | Client portal v2: magic-link login, approvals (drawings, selections, variations), invoices/receipts | C + Cl | 2–3 | Shared approvals | Client approves a drawing revision; decision appears on the drawing and in audit |
| P2.7 | Drawing transmittals, previews and portal sign-off | C + Cl | 1.5–2 | P2.1, P2.6 | Transmittal PDF with acknowledgement status; superseded revisions marked |
| P2.8 | Task dependencies and timeline/Gantt with baselines | C + Cl | 2–3 | — | Dependent dates move with predecessors; baseline vs actual shown |
| P2.9 | HR: onboarding/exit checklists, document-expiry alerts, appraisal notes; leave carry-forward (HR-03); statutory payroll (HR-02) if decided | C + Cl | 2–4 | Decisions | Policy tests per rule |
| P2.10 | Accounting: TDS on bills with section summaries, credit notes, Tally export, budgets vs actuals, cash-flow forecast | C + Cl | 3–4 | ACC-05 decision | CA review of exports; forecast reproducible from source rows |
| P2.11 | Notifications: email + WhatsApp Business API channels with preferences and templates | C + Cl | 1.5 | P1.7, provider | Per-user channel preferences respected; delivery log |

### P3 — AI automation, analytics and differentiators

| # | Item | Owner | Effort | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| P3.1 | AI platform layer: direct provider, tenant opt-in, credits, redaction, per-tenant logs | C | 1–1.5 | P1.2, P1.6 | No AI call without opt-in and credit; logs tenant-scoped |
| P3.2 | Document extraction → draft bills/expenses/prices with mandatory review | C + Cl | 2–3 | P3.1, P2.2 | No draft posts without approval; accuracy measured on a labelled sample |
| P3.3 | Project summaries, meeting notes → task drafts, reminder drafting | C + Cl | 2 | P3.1 | Drafts only; user confirms |
| P3.4 | Natural-language search across tenant records and drawings | C + Cl | 2–3 | P3.1, P2.1 | Results respect permissions (tested with restricted roles) |
| P3.5 | Portfolio analytics, scheduled reports, delay early-warning (after data exists) | C + Cl | 2–4 | P2.4/P2.5 | Reports reproducible from source data |
| P3.6 | PWA/offline site capture; RFIs and daily site diary (after demand validation); PDF revision compare; e-invoice (IRN) for large tenants | C + Cl | each 1–3 | Various | Per feature |

---

## Part G — Management decisions needed (with recommended defaults)

| # | Decision | Recommended default | Trade-off |
|---|---|---|---|
| G1 | Platform identity: GAMAA brand on public site, login and app shell; each tenant's brand inside its workspace | **Yes.** Design Saga keeps its exact palette as its tenant theme | Neutral shell is required to sell; small one-time UI work |
| G2 | Sign-in model | **Workspace URL** (`gamaa.in/w/<slug>`) now; subdomains later | Subdomains need wildcard TLS and DNS changes to the protected Caddy config |
| G3 | Same person in several companies | **Allow** through memberships | Requires an identity migration; avoids duplicate accounts |
| G4 | Super Admin access to customer data | **Only through time-boxed, reason-logged, read-only-by-default grants visible to the tenant** | Slightly slower support; much stronger trust |
| G5 | How customers pay GAMAA | **Manual invoices + bank transfer/UPI first**, gateway (for example Razorpay subscriptions) later | Manual work at small scale vs gateway fees and integration effort |
| G6 | Lifetime offering | **"Lifetime hosted access" = one-time licence + mandatory annual hosting/maintenance with written caps**; no self-hosted perpetual licence now | Upfront cash vs long-term hosting cost; caps protect margins |
| G7 | Lifecycle timings | Trial 14 days; grace 7 days; read-only up to 30 days; retention 90 days before scheduled purge | Longer windows are friendlier but cost storage |
| G8 | Hosting | **Give GAMAA its own VPS (about 8–16 GB RAM)** or move Tanvika, before onboarding paying firms; off-site backups to an S3-compatible bucket; external alerting | Monthly cost vs shared-host risk |
| G9 | File storage | **S3-compatible object storage** with tenant prefixes | Small monthly storage cost; enables large drawing libraries |
| G10 | Email / WhatsApp providers | One transactional email provider now; WhatsApp Business API in P2 | Provider fees; sub-processor disclosure |
| G11 | AI policy | **Opt-in per tenant; no financial records sent unless the tenant enables it; credits per plan; direct provider with a DPA** | Fewer "magic" features by default; clear privacy story |
| G12 | Existing open decisions in the tracker | SEC-02/06 (employee visibility of clients and leads), ACC-02 (GST split and rounding), ACC-05/06 (TDS, credit notes, Tally, email, payment links), HR-02/03 (statutory payroll, leave carry-forward) | Each needs owner or CA input before build |

---

## Appendix A — Git and deployment state (verified 11/11/2026)

| Item | State | Action |
|---|---|---|
| Production | Live source `a588b05` (backend) and web image `8647b84` on `srv2020574` per tracker DS-121 (10/11). Release history includes VPS-only merge commits | Release only through Codex's guarded updater |
| Codex integration line | `codex/integrate-latest-20261110` / `origin/codex/repair-release` at `b6d59ef`: adds calendar privacy commits `baf946c`, `2095f8a`, `b6d59ef` after `a588b05` | Next release candidate |
| Claude line | `claude/ux-product-refinement` at `38a7b4c`; 3 commits not on the production line: `77119ec` (attendance edge cases, fee at creation, group fee updates), `a4fdfd7` (PIN-unlock and dashboard speed), `38a7b4c` (Leads converted-lead fix). Codex's `96628c2` touched the same files | **P0.1 integration.** A fast-forward release of the Claude line is impossible (verified: production head is not an ancestor) |
| Duplicate fix | `claude/fix-consultancy-defaults-test` (`7761f56`) duplicates Codex's DS-120 CDX-03 test correction | Drop in favour of Codex's version during P0.1 |
| `main` | Far behind (`origin/main` 24/10); about 129 commits behind the Claude line | Fast-forward to the release after P0.1 |
| Old worktrees/branches | `design_saga-github` on `production` (14/10), scratch worktree `base397` (detached), remote `conflict_*` and `copilot/*` branches from July/April | Archive after the integration owner confirms nothing unique remains |
| Local artefacts | `ds-ux-*.bundle` files in the Claude worktree; `frontend/test-results/` (gitignored Playwright traces, which crash the Vite dev dependency scan) | Delete bundles after P0.1; exclude `test-results` from the dev scan |
| Owner hand-offs pending | Do **not** run the earlier `ship-release.ps1` / bundle steps for `38a7b4c` (they would stop at the fast-forward and deploy nothing) | Superseded by P0.1 |

## Appendix B — Competitor research (public sources)

Feature claims are vendor-published unless stated. Nothing was copied; these inform workflow comparisons only.

| Product | Verified relevant features | GAMAA gap it highlights | Sources |
|---|---|---|---|
| Monograph (A&E practice management) | Timers and weekly timesheets (billable/non-billable) structured by phase, role and activity; planning of schedules, budgets and resources; Gantt/timeline; fixed-fee and hourly invoicing tied to time | Timesheets, phase budgets, profitability, capacity | [Time tracking](https://monograph.com/features/time-tracking), [Project management](https://monograph.com/features/project-management), [Capterra](https://capterra.com/p/178124/Monograph/) |
| BQE CORE (A&E ERP) | Time and expense, project accounting, budgeting and resource allocation, recurring/batch invoicing, CRM | Time-driven billing and resource planning | [Software Advice](https://www.softwareadvice.com/project-management/bqe-core-project-management-profile/), [BQE](https://www.bqe.com/project-management-software-ppc) |
| Houzz Pro (interior designers) | Mood boards, product web clipper, branded client dashboard (boards, selections, invoices), e-signatures and approvals, payment schedules and deposits | Product sourcing, selections, client approvals in portal | [Houzz Pro for designers](https://pro.houzz.com/for-pros/software-interior-designer), [Houzz Pro workflow](https://www.houzz.com/pro-learn/blog/perfect-your-designer-workflow-with-houzz-pro1), [DesignFiles comparison](https://blog.designfiles.co/houzz-pro-vs-studio-designer/) (competitor-written) |
| Studio Designer (interior design business platform) | Proposals → purchase orders, vendor tracking and receiving, A/R and A/P, reconciliation, income and cash-flow statements, QuickBooks integration | Proposal → PO chain for product selections | [Accounting features](https://www.studiodesigner.com/features/interior-design-accounting-software/), [Business of Home](https://businessofhome.com/articles/how-new-initiatives-led-studio-designer-to-10-000-users-and-counting), [Capterra](https://capterra.com/p/217839/Studio-Designer/) |
| Programa (interior design) | Studio product library (clipper, URL paste), image-rich schedules replacing spreadsheets, branded client dashboard with approvals and comments without logins | Product Library + schedules + approvals | [Features](https://programa.design/features), [Schedules](https://programa.design/features/schedule-software-for-interior-designers-architects-clients) |
| Procore (construction) | RFIs and submittals with reminders, drawings with revision access and markup distribution, daily logs, punch lists with photo verification | Transmittals, RFIs, site diary (validate demand) | [Procore platform features](https://v2.support.procore.com/product-manuals/procore-for-government/procore-for-government-platform-features), [TrustRadius review](https://www.trustradius.com/reviews/procore-2020-01-13-09-55-01) |
| Autodesk Construction Cloud — Docs | Publish sheets, reviews, transmittals, file issues, version compare (overlay / side-by-side) | Transmittals and revision compare | [About Autodesk Docs](https://help.autodesk.com/cloudhelp/ENU/Docs-About-ACC/files/about-acc/About_Autodesk_Construction_Cloud_Docs.html), [Design review module](https://www.autodesk.com/learn/ondemand/module/project-or-get-started-in-the-classroom-with-docs-and-build/unit/5AY7G3L8TvCEp38zwzMZ23) |
| Odoo | Timesheets from tasks with one-click approval, planned-vs-worked analysis, planning/shifts, subscriptions with renewals and alerts | Timesheet approval; a reference for subscription lifecycle mechanics | [Timesheet features](https://www.odoo.com/page/timesheet-features), [Services docs](https://www.odoo.com/documentation/master/applications/services.html) |
| Zoho Books (India) | GST rates/treatments, e-way bill detection; partner sources report e-invoice (IRN/QR) and TDS 26Q support (Unverified) | GST split, HSN/SAC, e-invoice readiness | [GST accounting](https://www.zoho.com/in/books/gst-accounting-software/), [All features](https://www.zoho.com/in/books/accounting-software-features/) |

**Security and platform references**

| Topic | Note | Source |
|---|---|---|
| Multi-tenant security | Tenant identifiers from clients are selectors only; authorise the principal for the tenant; isolate database, cache, storage and compute; secure onboarding/offboarding. Official cheat sheet not fetched in this pass, so verify the text | [OWASP Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html) (reference), [OWASP Cloud-10 Multi Tenancy](https://wiki.owasp.org/index.php/Cloud-10_Multi_Tenancy_and_Physical_Security), [Cheat-sheet proposal](https://github-users.yhajoa.workers.dev/OWASP/CheatSheetSeries/issues/1928) |
| Google OAuth Testing mode | Up to 100 test users; test-user authorizations and refresh tokens expire after 7 days; publishing removes the allowlist | [Manage app audience](https://support.google.com/cloud/answer/15549945), [Production readiness](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview) |
| GST e-invoicing | Mandatory above ₹5 crore aggregate turnover (from 1 Aug 2023, PAN-level, any FY since 2017-18) per secondary sources; confirm against the CBIC notification before building | [Tally e-invoicing threshold](https://tallysolutions.com/gst/e-invoicing-threshold/), [TaxGuru](https://taxguru.in/goods-and-service-tax/mandatory-gst-e-invoicing-rules-deadlines.html) |

**Where GAMAA is already stronger than most interior-design tools (keep and market):**
- Integrated Indian-context accounting: collections due with aging, period close, bank reconciliation, the cash/accrual basis.
- Attendance with geofencing, site visits with photos, and payroll that is linked to attendance.
- Room-wise BOQ with change orders and cost vs actual.
- Per-tenant audit hash chain.
- Phase templates with fee shares.

## Appendix C — Local measurements behind B8 (10/11/2026)

The dataset is synthetic on local MongoDB 8 (FerretDB adds per-query overhead in production), median of 3 runs.

| Call | Before | After `a4fdfd7` (Claude line, not yet released) |
|---|---|---|
| `/dashboard/stats` | 859 ms | 327 ms (identical figures, parity-checked field by field) |
| `/vendors` (300 vendors) | 696 ms, one query per vendor | 65 ms, one query |
| Admin setup checklist | 4 list downloads, 462 KB | 1 call, 0.1 KB |
| PIN unlock blocking other requests | about 0.42 s | about 0.02 s (bcrypt in a worker thread) |
| Unlock → dashboard fully loaded (production build) | 2 sequential waves | 1 wave, 1.9 s locally |
