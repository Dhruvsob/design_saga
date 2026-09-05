# Design Saga – PRD

**Original problem statement:** Build a SaaS-grade platform for architecture/interior design firms covering CRM, projects, tasks, files, client portal, billing, AI assistant, dashboards. MVP "lite" version covering all modules. Roles: Admin + Employee. Auth: Emergent Google. Integrations: PDF gen, AI (Claude), SendGrid email, Stripe payments. Visual: modern bold + distinctive (delivered as Swiss/editorial with Klein Blue #002FA7 accent + Cabinet Grotesk + IBM Plex Sans).

**Continuation contract:** Treat the ERP as an established product (~70% complete). No rebuilds; every iteration is a versioned enhancement. User-approved Phase-2 order:
  1. **Vendor / Agency Management + Vendor Ledger  ✅ v2.1  (Jul 21, 2026)**
  1.5 **System audit fix pack — data integrity + demo purge + Admin approval + password login  ✅ v2.2  (Jul 21, 2026)**
  2. **Notification Center — global bell + module emitters  ✅ v2.3  (Jul 21, 2026)**
  3. Attendance Policies (office hours, grace mins, weekly off, holidays)
  4. **Salary Slip PDF (fpdf2, logo-ready, org-branded)  ✅ v3.0  (Jul 25, 2026)**
  5. **Multi-Tenant SaaS retrofit — Organizations, SuperAdmin, Branding  ✅ v3.0  (Jul 25, 2026)**
  6. **Accounting improvements — Balance Sheet + Cash Flow + Extended Dashboard + CSV exports  ✅ v2.3 (partial · Jul 21, 2026)**
       Remaining P6 items (project/client/employee ledgers polish, archive/restore accounts, advanced filters) deferred to v3.1.
  7. ERP intelligence (AI-driven suggestions after 1-6 land)

Multi-tenant note: every new schema from v2.1 onward carries an optional `org_id` field so a future tenant switch is a filter change, not a migration.

**Latest expansion (Aug 31, 2026 — v4.0): FULL PRODUCT AUDIT + PRODUCTION HARDENING (7-phase pass).**

**v4.0 — Product-Level Audit & Advanced Improvement** (Aug 31, 2026)
- **Deep audit with seeded multi-tenant data.** Two realistic tenants created via APIs (Atelier Vista — consultancy; BuildCraft Interiors — turnkey) with employees, clients, leads, projects, tasks, vendors, quotations, invoices, milestones, JEs, PO/GRN, holidays. Reusable scripts: `tests/seed_and_audit.py` (seed + isolation + RBAC + endpoint sweep + accounting integrity), `tests/flow_audit.py` (cross-module flows).
- **P0 tenant-isolation fixes.** `payment_milestones` was read/updated/deleted UNSCOPED (dashboard KPIs leaked across orgs; any org could modify another's milestones) — now fully `sdb`-scoped. `vendor_ratings` + `commission_settlements` org-stamped. Task/scan assignee-by-name lookups org-scoped. `rbac` last-admin guard now counts same-org admins only.
- **Notifications fixed for multi-tenant.** `emit()` stamps each recipient's org_id; reads are user_id-scoped (recipient-based security); `emit_admins/finance/hr` accept `org_id` and never broadcast cross-tenant; scan callers pass caller org. **Automated scheduler**: startup task runs the due/overdue scan for every active org every 6h (idempotent dedup keys) — no manual bell-click needed.
- **Accounting = source of truth (closed the loop).** Invoice marked paid → auto-JE `source=invoice_payment` (DR Bank/CR Income, client+project tagged, `journal_id`+`paid_date` stored); un-pay → balanced reversal JE. Same for milestones (`milestone_payment`). `create_income(invoice_id)` marks the invoice paid + links the JE. `POST /accounting/repair/orphan-invoices` backfills JEs for legacy paid invoices (idempotent). Validation dashboard fixed (issue_date fallback → invoice counts correct; orphan detection verified working). Invoice status changes now require `invoices.update`.
- **Tenant management (SuperAdmin) upgraded.** Suspension now blocks LOGIN + every request (`deps.require_user` org gate) — previously only killed sessions. Plan limits: `PATCH /platform/orgs/{id}/limits` + enforcement at user-registration and project-creation (HTTP 402). `GET /platform/orgs/{id}/health` (counts/usage/warnings/last-login). `GET /platform/isolation-check` (20 collections, PASS/FAIL). SuperAdminPanel UI: isolation-check card, per-org Health modal with plan/limits editor.
- **Employee → ERP identity (new).** `GET/POST /employees/{eid}/account` + `/account/status`: view linked login, create login in one step (plan-limit aware, links user_id back), change role, activate/deactivate (kills sessions). New "ERP Access" tab in EmployeeDetail.
- **Quotation PDFs org-branded + blank-section skipping.** Generator takes org (name/tagline/primary colour); Executive Summary / Scope / BOQ / Cost Summary pages are skipped entirely when empty; zero-value adjustment rows hidden. Verified visually: consultancy (fee-schedule format) vs turnkey (BOQ + margins + materials) both professional.
- **Master data actually feeds the UI.** `tasks/meta` merges tenant `task_area`/`task_category`; `employees/meta` merges `department` + returns `designations`.
- **Calendar bug fixed.** Month nav normalises to day 1 (Aug 31 + 1mo used to land on Oct 1). Unified feed verified rendering tasks, invoice dues, milestones, holidays.
- **UX polish.** Tasks filters compacted to one row; login Google button `type=button` hardening; AI assistant persona tenant-branded.
- Seed fix: `seed_demo` upsert stamps org_id; startup backfill covers 13 more collections.
- **Testing:** 2 testing-agent rounds. Round 2: backend 100%, frontend 12/13 → re-verified 27 passed, 0 critical/minor/UI/integration bugs, isolation-check PASS.

**Latest expansion (Feb 7, 2026 — v3.6): Attendance hardening + Holiday Calendar + mode-based Vendor UI.**

**Fix Pack v3.6** (Feb 7, 2026)
- **Holiday Calendar module** — new `routes/holidays.py` + `Holidays.jsx`. Per-org CRUD with 5 kinds (national/festival/optional/company/regional), recurring same-MM-DD holidays that auto-materialise for any future year, and bulk-seed endpoint for onboarding. Auto-syncs into Attendance: when today is a company holiday or weekly-off, `check-in` short-circuits and marks the day with status `holiday`.
- **GPS + Geo-Fencing hardening**
  - New `max_gps_accuracy_m` policy — rejects check-ins whose reported accuracy is worse than the threshold (default 100m) with code `gps_accuracy_low`. Frontend surfaces an amber banner with a "Retry with better GPS" CTA.
  - Late-arrival reason enforcement — if the employee is more than `grace_minutes` late and `require_late_reason=true`, check-in returns 422 `late_reason_required`. UI collects the reason inline and re-submits with `late_reason`.
  - Device fingerprinting — `device_id` (persisted in localStorage), `device_label`, and full `user_agent` captured on every check-in for audit.
  - Existing multi-office / multi-site radius, GPS coords, and IP capture retained.
- **Mode-based Vendor UI** — `VendorDetail.jsx` now derives its tab list from `currentOrg.business_mode`. Consultancy shows only Overview / Commercial / Commissions / Projects / Documents / Performance (no bills/payments/AP ledger). Turnkey and Hybrid keep the full tab set.
- Tests: `backend/tests/test_holidays_and_attendance.py` — holiday CRUD + recurring materialisation + bulk seed + kind validation + policy carries the two new fields.

**Deferred to a dedicated iteration**
- **Google Calendar Sync per-tenant** — deferred; requires a full OAuth playbook (per-tenant token store, refresh flow, event push on project/task lifecycle). Requested user preserve credit budget so we booked it for a focused follow-up run.

**Phase C · Accounting Deep Upgrade** (Feb 5, 2026)
- **Financial-year engine.** New `core/finance.py` implements the Indian Apr–Mar FY convention (`current_fy_label`, `fy_range`, `resolve_period`). `GET /api/accounting/fy/list` returns dropdown-ready choices (5 back, current, 1 forward).
- **FY / date-range on every report.** `/accounting/reports/pl`, `/trial-balance`, `/balance-sheet`, `/cash-flow`, and `/journal-entries` list all accept `fy=YYYY-YY` OR explicit `from_date`/`to_date`. Custom-range wins if either date is supplied. Responses include a `period_label`.
- **Unified per-entity ledgers with running balance.** `/accounting/ledger/{client|vendor|employee|project}/{id}` returns `opening_balance / inflow / outflow / net_movement / closing_balance` + per-entry running balance. Sign convention derives from the entry's cash/bank lines with income/expense fallback. Project ledger additionally exposes `revenue / expense / profit / milestones`. New employee ledger endpoint.
- **Multi-entity tagging on Income / Expense.** JEs, `IncomeIn` and `ExpenseIn` all now carry `client_id + vendor_id + employee_id + project_id`. UI: Income/Expense modal now shows all four entity dropdowns so a single transaction can flow into every relevant ledger.
- **Silent validation mode.** New Admin-only `/accounting/dashboard/validation` runs both engines side-by-side (accounting JE aggregation vs legacy invoices+milestones) and returns per-source totals, delta, `match_within_1pc` verdict, plus diagnostics (orphan-paid invoices, income JEs missing client/project). Frontend "Validation" tab surfaces the report and hides duplicate KPIs from normal users.
- **Ledgers tab.** New Accounting → Ledgers view with entity-type toggle (Client / Vendor / Employee / Project), entity picker, and 4-card summary (Opening / Inflow / Outflow / Closing) + full running-balance table.
- Fixed a latent positional-arg bug in the CSV export chain that the new `fy` parameter would have broken (all internal calls now use kwargs).
- Tests: `backend/tests/test_phase_c_accounting.py` — 14 tests covering FY list, FY on P&L/BS/CF/TB, entity ledgers structure, running-balance math, income entity-tagging, validation report shape + RBAC.

**Latest expansion (Feb 4, 2026 — v3.4): Accounting integrity fixes + object-storage-backed logo upload.**

**Fix Pack v3.4** (Feb 4, 2026)
- **P1 · Vendor Bill soft-cancel now reverses commission JE.** When a vendor bill is cancelled *after* its commission was already received, a balanced reversing journal entry is automatically posted (DR Vendor Commission Income · CR Bank) so the P&L, Balance Sheet and Cash Flow accurately reflect that the income is void. The commission row is marked `reversed` with `reversal_je_id`, and the operation is idempotent (repeat cancellations do not double-reverse). Commission ledger/dashboard/report endpoints now exclude both `cancelled` and `reversed` rows from their totals. Hard-deleting a bill with a received commission takes the same path.
- **P2 · Balance-Sheet reconciliation utility.** `GET /accounting/reports/balance-sheet` now returns `delta` and `unbalanced_journal_entries[]` alongside the existing `balanced` flag, so any imbalance is diagnosable in one call. New `POST /accounting/reports/balance-sheet/reconcile` parks the residual delta on a reserved equity account (`Opening Balance Adjustment`, seeded into the default COA) — audit-friendly and one-click from the Balance Sheet tab. UI now surfaces a red-banner Δ and a `Reconcile` button plus an expandable list of unbalanced JEs.
- **P2 · Logo upload moved to Emergent Object Storage.** `services/storage.py` wraps the objstore v1 API; `POST /org/current/logo` streams data-URL and multipart uploads to storage, saves only a `/api/org/logo/{path}` proxy URL in Mongo (mimes gated to png/jpg/webp/svg, 2MB cap), and `GET /api/org/logo/{path}` is a public proxy for pre-auth branding. Falls back to inline storage if the object store is offline. Bootstraps once at server startup via `init_storage()`.
- Tests: `backend/tests/test_p1_p2_fixes.py` covers the JE reversal (incl. idempotency), balance-sheet reconciliation, and logo upload (happy path + rejected mime + oversize).

**A · Purchase Orders + GRN + 3-way match** (`routes/purchase.py`, `models/purchase.py`)
- `db.purchase_orders` + `db.goods_receipts` collections; auto per-org sequence `PO-2026-NNNN` and `GRN-2026-NNNN`.
- POST /api/purchase-orders — line items, taxes, auto totals, status: draft.
- POST /purchase-orders/{id}/send  |  /cancel (blocked when GRN exists).
- PATCH  updates lines/dates/terms while status ∈ {draft, sent}.
- POST /api/grns — records receipts against a PO, rejects over-receiving, auto-creates "Inventory" (asset) + "GRN Clearing" (liability) accounts, posts JE (**DR Inventory / CR GRN Clearing**), advances PO status to partial → received.
- GET /api/purchase-orders/{id}/match — 3-way variance report (ordered vs received vs billed) with `all_matched` flag; pulls linked vendor bills where `bill.po_id` matches.
- Frontend `/purchase-orders` page: PO ledger, create form with live subtotal/tax/total, PO detail modal with Send/Cancel actions, Record GRN modal (pre-fills remaining qty), 3-way match table with green ✓/red variance.

**B · Expense claims + multi-level approval** (`routes/expenses.py`, `models/expense.py`)
- `db.expenses` + `db.expense_policies` collections. Default policy: L1=ProjectManager > ₹5k, L2=Director > ₹25k, receipt required > ₹1k, allowed categories: travel/meals/materials/utilities/site/office/other.
- POST /api/expenses (any user) — auto-routes by amount vs policy: `auto_approve_below` → approved, `needs_l2` → pending_l1 → pending_l2, missing receipt → `receipt_required`.
- POST /api/expenses/{id}/decision {decision:'approve'|'reject', comment} — enforces `pending_approver_role`, records approval trail, escalates to L2 if needed.
- POST /api/expenses/{id}/reimburse {paid_from_account_id} — Accountant/Admin only; posts JE (**DR expense category account × N / CR bank**) with `_ensure_account` for auto category mapping (travel→"Travel & Conveyance", site→"Site Expenses", …), flips status to `reimbursed`.
- GET /api/expenses (filters: mine, status, project_id) + `/summary/dashboard` (pending / approved / reimbursed_this_month / my_pending) + `/approvers` (policy + approver users).
- Frontend `/expenses` page: 4 KPI cards, tabbed views (All / My Expenses / Awaiting My Approval), submit modal with dynamic line items + running total, detail modal with approval trail + inline decide + reimburse control.

**C · Attendance Policies + GPS Geo-Fencing** (extended `routes/attendance.py`)
- `db.attendance_policies` — office_start/end, grace_minutes, half_day/full_day min hours, weekly_off_days, holidays[], geo_fencing_enabled, require_geo_for_office, approval_required_when_outside, default_office_lat/lng/radius_m.
- `db.office_locations` — named geo-fences {name, kind (office|site|warehouse|client|vendor), lat, lng, radius_m, project_id?}. Admin CRUD via `/api/attendance/locations`.
- `GET /api/attendance/policy` + `PUT` (Admin) — company-wide config.
- `GET /api/attendance/geo-check?lat=&lng=&kind=` — Haversine distance check, returns `{inside, matched_location, distance_m, reason}`.
- **Check-in flow (user's spec):**
  1. Employee opens ERP → picks `attendance_type` ∈ office / site_visit / client_meeting / warehouse / vendor_visit.
  2. Browser requests GPS → `{lat, lng, accuracy_m}` sent with request.
  3. Backend runs `_resolve_geo_fence(kind, lat, lng)` — nearest active fence of matching kind within its radius.
  4. **Inside** → check-in succeeds. Office = `status: present, approval_status: auto`; non-office = `pending_approval`.
  5. **Outside** → HTTP 422 with `detail = {code:'outside_geofence', message, distance_m, matched_location, options:['Request Approval','Retry','Contact Admin']}`.
  6. Employee taps "Request Approval" → same POST with `force_outside:true` → recorded as `status:'pending_approval'` for HR review.
- Existing site-visit approval endpoints reused for HR to approve/reject outside-fence check-ins.
- **Frontend** — 5-button attendance-type selector, GPS auto-requested on button click, "Outside authorized location" red banner with Request Approval / Retry / Contact Admin buttons matching the spec. Check-in row now shows `📍 <location> (<distance>m)`.

**D · Audit-log expansion**
- New hooks: `po.create`, `po.send`, `po.cancel`, `grn.create`, `expense.submit`, `expense.approve`, `expense.reject`, `expense.reimburse`, `expense_policy.update`, `attendance_policy.update`.

**E · Indexes added** — purchase_orders (org_id, status), (org_id, vendor_id), (po_number sparse); goods_receipts (org_id, po_id), (grn_number sparse); expenses (org_id, status), (org_id, claimant_id), (org_id, pending_approver_role); office_locations (org_id, kind); attendance (org_id, date, geo_inside).

**Testing** — iteration_12: **27/27 PASSED** covering full CRUD, JE auto-posting, policy-based routing, multi-level approval gating, GPS enforcement with outside-fence 422 + force_outside path, audit trail, and 9 backward-compat endpoints.




**A · Loans & EMI module (new)**
- New `db.loans` collection: `{id, org_id, lender_name, loan_type, principal, interest_rate_pa, tenure_months, emi_amount, start_date, emi_day, schedule[], loan_account_id, interest_expense_account_id, disbursement_account_id, status, disbursement_journal_id, ...}`.
- `models/loan.py`: `LoanCreateIn`, `LoanUpdateIn`, `PayEMIIn`, `PrepayIn` with pydantic validation.
- `routes/loans.py` — full CRUD + amortization engine (reducing-balance EMI, rounding-safe last row).
  - `POST /api/loans` — creates loan, auto-creates "Loan – <lender>" liability account (idempotent), posts disbursement JE (DR Bank / CR Loan), returns 12/24/36/N-month schedule.
  - `POST /api/loans/{id}/pay-emi` — posts 3-line JE (DR Loan Principal + DR Interest Expense + CR Bank), marks schedule row paid, advances outstanding. `extra_principal` reduces upcoming rows. Auto-closes loan on last EMI.
  - `POST /api/loans/{id}/prepay` — lump-sum reduction, posts JE, recalculates schedule tail.
  - `GET /api/loans` / `GET /api/loans/{id}` — with outstanding/next_due_date/totals rollup.
  - `GET /api/loans/summary/dashboard` — active_loans + total_outstanding + next_emi_due_date + next_emi_amount.
  - `DELETE /api/loans/{id}` — only if no EMIs paid; reverses disbursement JE.
- Frontend: new `/loans` page with 4 KPI cards, ledger table, "Add Loan" modal with live EMI + total-payable preview, detail modal with full amortization schedule, per-row "Pay" button, prepay input, "Pay From" account selector. Sidebar nav updated.
- Every loan is tenant-scoped via sdb; JEs are also stamped with org_id.

**B · Append-only Audit Log**
- `core/audit.py::audit()` — non-throwing helper. Records `{action, target, target_type, actor_id, actor_email, actor_role, org_id, meta, at}` in `db.audit_log`.
- `routes/audit.py` — `GET /api/audit-log?action=&actor_id=&limit=` with SuperAdmin cross-org / Admin own-org scoping.
- Hooks in place for: `loan.create`, `loan.pay_emi`, `loan.prepay`, `loan.delete`, `org.suspend`, `org.activate`, `org.deactivate`, `org.purge`.

**C · Platform ops improvements**
- `GET /api/platform/pending-signups` — surfaces Google users whose email domain didn't match any org.
- `POST /api/platform/users/{user_id}/reassign-org` — SuperAdmin moves user into a target workspace, sets role, auto-approves.
- Frontend Super Admin panel: new "Pending Google Signups" card with amber warning tone + inline "Assign to Workspace" modal (org + role selectors).

**D · Password policy + security**
- `models/user.py::_validate_password()` — min 8 chars + must contain letters AND digits. Enforced on register, change-password, admin reset, SuperAdmin org-creation.
- Deploy warning: if `ENV=production` and `SUPER_ADMIN_EMAILS` is still the default `designsaga10@gmail.com` only, logs a warning at startup.

**E · Mongo indexes (production perf)**
- `core/indexes.py::ensure_indexes()` — idempotent creation of 33 compound indexes on hot fields:
  - Auth: `users.email` unique, `users(org_id, role)`, `user_sessions.session_token` unique, `user_sessions.expires_at` TTL.
  - Tenancy: `organizations.slug` unique, `organizations.org_id` unique.
  - CRM / Delivery: `leads(org_id, stage)`, `projects(org_id, stage)`, `tasks(org_id, project_id, status)`, `tasks(org_id, assignee_id)`, `tasks.reminder_date` sparse.
  - Billing: `invoices(org_id, status)`, `quotations_adv(org_id, status)`.
  - Vendors: `vendors_acc(org_id, name)`, `vendor_bills(org_id, vendor_id, status)`, `vendor_commissions(org_id, vendor_id, status)`.
  - People: `employees(org_id, employee_id)`, `attendance(org_id, employee_id, date)`, `leave_applications(org_id, employee_id, status)`, `payroll_runs(org_id, employee_id, year desc, month desc)`.
  - Accounting: `journal_entries(org_id, date desc)`, `accounts(org_id, type)`.
  - New: `loans(org_id, status)`, `loans(org_id, next_due_date)`, `audit_log(org_id, at desc)`, `audit_log(actor_id, at desc)`.

**F · Housekeeping**
- Deleted dead `/app/frontend/src/pages/Tasks.jsx` (2-line orphan); `/tasks` route now uses the correct `TasksBoard`.

**Testing** — iteration_11: 33/33 PASSED covering loans full CRUD + EMI + prepay + audit log + reassign-org + password policy + index functional + backward compat. `/app/backend/tests/test_loans_audit_iter11.py` created for regression.


**Prior expansion (Feb 4, 2026 — v3.2): Phase 1 critical fixes + Loans/EMI module.**




**A · Strict tenant isolation** — full retrofit across the ERP.
- New `core/scoped_db.py` — a `sdb` proxy that wraps every business collection with automatic `tenant_filter(user)` injection on reads (find/find_one/count_documents/update_one/update_many/delete_one/delete_many/aggregate/distinct) and `stamp_org(doc)` on writes (insert_one/insert_many). Scope is set once per request via a `ContextVar`, then transparently applied to all subsequent Mongo calls.
- `core/deps.get_current_user`, `core/deps.require_user`, and `server.get_current_user` now call `set_scope_from_user(user)` so every authenticated request activates its tenant scope.
- Bulk mechanical rename `db.<coll>. → sdb.<coll>.` across 21 business collections in `server.py` + `routes/*.py` (315 total call sites): leads, clients, projects, tasks, invoices, files, milestones, quotations, quotations_adv, employees, vendors_acc, vendor_bills, vendor_payments, vendor_commissions, journal_entries, accounts, payroll_runs, attendance, leave_applications, leave_rules, notifications.
- Platform / auth collections (`organizations`, `users`, `user_sessions`, `login_attempts`) continue to use plain `db` (SuperAdmins need cross-org access here).
- **Verified end-to-end (iteration_10)**: create fresh org "Iso Test" → its admin sees 0 projects/vendors/leads/tasks, dashboard revenue = 0. Create a project → stamped with correct `org_id`. Design Saga admin sees only their 3 original projects (Iso Test invisible). Direct GET on Iso Test's project ID by Design Saga admin returns 404 (cross-org access silently blocked, not 403 — better security posture). SuperAdmin's `/platform/analytics.projects` counts across all tenants.

**B · Google Auth domain routing**
- `/api/auth/session` now inspects the email domain on first sign-in. If any organisation has that domain registered on `org.email_domain` (or list in `org.email_domains`), the new user is auto-assigned to that org (`approval_status: "pending"`, awaits that org's Admin approval). Otherwise falls back to `org_default`.
- Existing whitelisted super-admin emails still auto-elevate to `SuperAdmin` with `org_id: null`.

**C · Session-level scope isolation**
- Session tokens tied to suspended/deactivated orgs are killed instantly (already existed in platform `/status` endpoint) — the scoped proxy defence-in-depth ensures even a valid session with a stale org_id gets scoped to that suspended org and returns empty for reads.

**Testing** — iteration_10: 18 passed, 1 skipped (payroll slip — no runs in DB), 0 failed. Zero regressions on legacy default-org data.



**Prior expansion (Jul 25, 2026 — v3.1): Universal tenant enforcement + Google domain matching.**  *(see v3.1 section at top of file — moved up chronologically)*



**Prior expansion (Jul 25, 2026 — v3.0): Enterprise Multi-Tenant SaaS + Company Branding + Salary Slip PDF.**

**A · Multi-Tenant Foundation**
- New `db.organizations` collection: `{org_id, slug, name, display_name, industry, plan, address, branding{logo_url,primary_color,accent_color,tagline,pdf_footer}, features, gstin, pan, is_active, is_suspended, is_default}`.
- Backend startup hook idempotently seeds default "Design Saga" org (`org_id="org_default"`) and backfills `org_id` onto every legacy doc across 20+ collections (users, projects, tasks, vendors_acc, journal_entries, notifications, etc). Verified 161 docs migrated in-place with zero downtime.
- New `core/tenancy.py` module: `tenant_filter(user)`, `stamp_org()`, `require_org_context`, `require_super_admin`, `is_super_admin`, `ensure_org_active`.
- New **`SuperAdmin`** role in `core/rbac.py` with `platform.*` permission. Whitelisted `SUPER_ADMIN_EMAILS` (default `designsaga10@gmail.com`) auto-elevate on every Google sign-in and cannot be demoted.
- `_pack_user` / `_user_with_perms` now emit `org_id` and `is_super_admin` on every auth response.

**B · Super Admin Panel (`/api/platform/*` + `/super-admin` route)**
- `GET /api/platform/orgs` — list all workspaces + per-org user/project/client counts.
- `POST /api/platform/orgs` — create new tenant + initial Company Admin (email + password + name).
- `PATCH /api/platform/orgs/{id}` — update name/plan/GSTIN/PAN/industry/branding/address.
- `POST /api/platform/orgs/{id}/status` — activate | suspend | deactivate (auto-logs out all users in that org).
- `DELETE /api/platform/orgs/{id}[?purge=true]` — soft delete by default; `purge=true` hard-deletes org + drops 15+ scoped collections. Default org protected.
- `POST /api/platform/orgs/{id}/admins` — add another Admin to an org.
- `POST /api/platform/orgs/{id}/users/{uid}/reset-password` — reset any user's password, revokes sessions.
- `GET /api/platform/orgs/{id}/users` — list all users in an org.
- `GET /api/platform/analytics` — total orgs, users, projects, tasks, platform-wide revenue (from all journal_entries income accounts) + top-5 leaderboard per-org.
- `POST /api/platform/impersonate/{id}` — SuperAdmin steps into a tenant context.
- **Frontend `/super-admin`**: KPI strip (Active Workspaces / Users / Projects / Platform Revenue), Revenue Leaderboard, Workspaces table with badges (DEFAULT, plan, status), row actions (Edit / Suspend|Activate / Manage Admins / Delete). Create modal (2-step: workspace info + first admin). Edit modal. Manage-admins modal with inline reset-password. Danger-zone delete confirmation with type-to-confirm.

**C · Company Branding (`/api/org/*` + `/settings/company` route)**
- `GET /api/org/current` — resolve the current user's org + branding.
- `PATCH /api/org/current` — update display name / phone / website / GSTIN / PAN / address / branding (partial merge on branding).
- `POST /api/org/current/logo` — accept base64 data URL up to 2MB.
- `GET /api/org/public/{slug}` — anon endpoint for the future subdomain-based login theming.
- **Frontend `/settings/company`**: two tabs (Brand & Colours, Company Profile). Brand tab: logo upload, primary + accent color pickers, tagline, PDF footer. Live preview panel showing sidebar / button / invoice-header rendered with the pending changes. Profile tab: display name, phone, website, GSTIN, PAN, and full address block.
- **AuthContext** now exposes `currentOrg`, `isSuperAdmin`, `refreshOrg()`; propagates `--org-primary` / `--org-accent` CSS variables at document root.
- **Layout** dynamically renders org logo / brand name / tagline in the sidebar and breadcrumb. New SuperAdmin nav item (visible only to SuperAdmins) with `Crown` icon in gold.
- **PDFs branded**: `generate_invoice_pdf(doc, org)` and salary slip both read org branding (primary color for title + TOTAL row, org name, tagline, GSTIN, PDF footer note).

**D · Salary Slip PDF**
- `GET /api/payroll/runs/{run_id}/slip.pdf` — enterprise-grade slip with org-branded header band, employee block (name, ID, department, designation, DOJ, bank A/C, PAN), attendance summary (working days / present / leaves / absent / half-days), side-by-side Earnings & Deductions tables, Gross / Total Deductions row, Net Pay callout with primary color, footer note. Latin-1 sanitised for FPDF. Own slip accessible by employee; others need `payroll.read`.
- Frontend: `EmployeeDetail → Salary tab` shows a "Download salary slip" link next to the PAID badge (opens PDF inline in a new tab).

**E · RBAC updates**
- `ROLES` catalogue now includes `SuperAdmin` with `platform.*` + `*.*`. `LEGACY_ROLE_MAP` maps `superadmin/super_admin/platform_admin` → `SuperAdmin`.
- Google Auth path now assigns `role="SuperAdmin"` for whitelisted emails (and first-ever user) instead of `role="Admin"`.
- Role assign endpoint refuses to demote a super-admin below Admin / SuperAdmin.

**Testing (iteration_8 backend + iteration_9 frontend)** — 20/20 backend endpoints pass (auth/me tenant fields, platform CRUD, analytics, org branding, RBAC catalogue, payroll slip 404, backward compat with dashboard/leads/projects/tasks/vendors/balance-sheet/notifications). Frontend 19/20 pass (SA panel + Company Settings + gating + workspace CRUD end-to-end). One redirect edge fixed post-test: SuperAdmin session was being defaulted to `org_default` by `_pack_user`; now forced to `None` unless impersonating. Zero regressions on existing modules.


**Latest expansion (Jul 21, 2026 — v2.3): Notification Center + Accounting Upgrade.**

**A · Notification Center (P2)**
- New `db.notifications` + `core/notifications.py` emit helpers (`emit`, `emit_admins`, `emit_finance`, `emit_hr`) — idempotent via per-user `dedup_key`.
- REST surface: `GET /api/notifications`, `GET /api/notifications/unread-count`, `POST /api/notifications/{id}/read`, `POST /api/notifications/mark-all-read`, `DELETE /api/notifications/{id}`, `POST /api/notifications/scan` (idempotent daily scanner — emits vendor_bill/invoice/milestone due & overdue + overdue-tasks per assignee).
- Emitters wired into: task creation (`task_assigned` to assignee, skip self), leave submit (`leave_request` to HR+Admin), leave decision (`leave_decided` to requester), RBAC approve (`account_approved`).
- **Frontend**: top-right `NotificationBell` component polls every 30s, red badge (99+ cap), dropdown with kind pills, clickable deep-links, per-row Read/Dismiss + Mark-all-read + manual Scan. Guarded so pending/rejected users don't poll.
- Architecture ready for WebSocket push later — no call-site changes needed, only extend `emit()`.

**B · Accounting P6 partial**
- `GET /api/accounting/reports/balance-sheet?as_of=` — Assets vs Liab + Eq + Net Income, with `balanced` reconciliation flag.
- `GET /api/accounting/reports/cash-flow?from_date=&to_date=` — Opening → inflows (income/client_payment/other) → outflows (expense/vendor_payment/payroll/other) → net change → closing.
- `GET /api/accounting/dashboard/extended` — Receivables + payables (with overdue splits from real invoices/vendor bills), 12-month income/expense/profit trend, top-10 expense breakdown for current month.
- **5 CSV exports** — `/api/accounting/reports/pl.csv`, `/trial-balance.csv`, `/balance-sheet.csv`, `/cash-flow.csv`, and `/api/journal-entries.csv` (with project/client/vendor/source/date filters). All gated by `finance.read`.
- **Frontend Accounting** — two new tabs (`Balance Sheet`, `Cash Flow`) with KPI strips + colored sections. Reports tab gets three CSV download buttons.

**Testing** — 18/18 backend pytest (`backend/tests/test_notifications_accounting.py`) + full frontend E2E green. Zero regressions.

**Latest expansion (Jul 21, 2026 — v2.2): System audit fix pack (Tiers A/B/C/D).**
- **A1 · Dashboard revenue** now sourced from `journal_entries` income accounts (single source of truth) — was previously double-counting via paid invoices.
- **A2 · Task ↔ Vendor master** — new `vendor_id` FK on TaskIn/TaskUpdate; task creation auto-backfills `vendor_contact` from the vendor master; vendor detail's `tasks` array picks up FK-linked tasks and legacy name-matched ones.
- **A3/A2b · Vendor pickers** replace text fields on the Accounting Expense form and the Vendor-type Task form (`expense-vendor-select`, `task-vendor-picker`).
- **A4 · Dashboard team utilisation** is now a priority-weighted (urgent=3, high=2, medium/low=1) real signal, not a raw open-task count.
- **B1/B2 · Demo cleanup** — three seed endpoints (`/api/seed`, `/api/employees/seed`, `/api/quotations-adv/seed`) are gated behind `ENABLE_SEED_DEMO=true`; existing fake leads/projects/tasks/invoices/clients purged from DB.
- **C1/C2 · Admin approval workflow** — new Google sign-ins land as `approval_status="pending"`, `is_active=false`; `require_user` (both server.py and core/deps) return 403 for pending/rejected users; `/api/rbac/pending` + `/api/rbac/users/{id}/approve` (decision: approve|reject) manage the queue. Super-admin & first user bypass approval. Frontend: dedicated Pending / Deactivated screens in ProtectedShell (`pending-approval-screen`).
- **D1 · Password login** (`POST /api/auth/login-password`) accepts email OR employee_id + password; bcrypt (passlib). Brute-force protection: 5 fails / 15 min → 429. Same session_token cookie as Google flow, so downstream code is untouched.
- **D2 · Admin creates users with passwords** (`POST /api/auth/register`) — auto-assigns sequential `DS0001`, `DS0002`… employee IDs. Reset-password kills victim's sessions. Self-service change-password with old→new. Fully wired in `/admin/rbac` (Create user modal + Reset password per row).
- **Refactor · Deduped ROLE_PERMISSIONS** — server.py now imports directly from `core/rbac.py` (was two drifting maps). Director + Accountant now correctly have `vendors.*` + `finance.*`.
- **Login page** kept the Emergent Google button and preserved the `DO NOT HARDCODE URL` guardrails; added a password form below.
- **AuthContext** now exposes `isPending`, `isRejected`, `loginWithPassword`. Bug in initial fix (pending user mis-branded as rejected) was caught by testing agent and corrected: `isRejected = status==='rejected' || (is_active===false && status !== 'pending')`.
- **Testing** — 18/18 backend pytest pass (`backend/tests/test_audit_fix_pack.py`), frontend flows verified (login-by-email, login-by-employee_id, RBAC admin approve/reject/create/reset, pending screen, both vendor pickers). Zero regressions on vendor module.

**Latest expansion (Jul 21, 2026 — v2.1): Vendor / Agency Management + Vendor Ledger.**

New backend module `routes/vendors.py` + `models/vendor.py` — extends (does not replace) the existing `db.vendors_acc` collection.

- **Vendor master (extended)**: agency_type (`vendor|agency|contractor|sub_contractor|supplier|consultant|freelancer|other`), contact_person, GSTIN, PAN, TDS applicability + rate, full banking block (bank/account/IFSC/branch/UPI), category, city/state/pincode, tags, notes, aggregate rating, `documents[]` (with kind + expires_on), `active` soft-delete, `org_id` ready.
- **Vendor bills** (`db.vendor_bills`): items + tax + tds, server-computed subtotal/tax_amount/tds_amount/total, status auto-transitions received → partially_paid → paid, overdue when due_date passes. Hard delete only when unpaid; otherwise soft-cancel to preserve audit.
- **Vendor payments** (`db.vendor_payments`): posts a balanced journal entry (DR Accounts Payable · CR Cash/Bank) with `source="vendor_payment"`, links `bill_ids[]` + `bill_splits{}`, FIFO settles open bills when none specified, tracks `unallocated` for on-account advance. Reversal endpoint deletes the JE and refreshes bill statuses.
- **Vendor ledger**: `GET /api/vendors/{id}/ledger` — chronological bills+payments with running balance. Reconciles to `total_billed − total_paid`.
- **Performance score (0-100)**: weighted composite = completion 30 · on-time 25 · rating 35 · payment reliability 10. Per-project ratings averaged into `vendor.rating` and `rating_count`.
- **Endpoints**: `/api/vendors` (GET filtered list w/ outstanding rollup, POST, PATCH, DELETE), `/api/vendors/{id}` (detail), `/api/vendors/meta`, `/api/vendors/{id}/documents` (POST/DELETE), `/api/vendors/{id}/rate` + `/ratings`, `/api/vendor-bills` (POST/GET/PATCH/DELETE + `/{id}`), `/api/vendor-payments` (POST/GET/DELETE), `/api/vendors/{id}/ledger`, `/api/vendors/{id}/performance`.
- **RBAC (new `vendors.*`)**: Admin/Director/Accountant → full; ProjectManager → create/update but not bills/payments (needs `finance.create`); Designer/Employee → read-only (for task assignment); HR → none; Client → none.
- **Frontend**: new sidebar entry `06 · Vendors` (HardHat icon). List page `/vendors` (KPI strip: count / contractors / suppliers / outstanding · search + agency_type filter · 3-section create form for identity/compliance/banking · clickable rows). Detail page `/vendors/:id` with 7 tabs (Overview · Ledger · Bills · Payments · Projects · Documents · Performance). Overview embeds a 4-dimension rating slider. Bills tab has an inline builder with dynamic line items and live client-side total that matches the server. Payments tab lists open bills as checkboxes for multi-bill settlement.
- **Testing**: `backend/tests/test_vendors_module.py` — 22/22 pytest pass. Curl smoke test: create → 58500 bill (18% GST, 1% TDS) → 30000 partial pay → ledger outstanding 28500 → performance 59.9. Testing agent verified all frontend flows + RBAC 403s for Designer/Employee/HR. Zero regressions on existing modules.

**Super-admin (v2.0 · Jul 21, 2026):** `designsaga10@gmail.com` protected via `SUPER_ADMIN_EMAILS` env var — auto-elevated on every Google sign-in, cannot be demoted through the RBAC endpoint.

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
