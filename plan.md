# ERP Connection + Usability Improvements (No Rebuild) — Plan

## 1) Objectives
- Implement **high-value connectivity + usability fixes** across the existing ERP without rebuilding modules.
- Enforce **Project Team vs Task Assignment** as separate concepts:
  - Project Team controls *task visibility* for regular employees.
  - Task Assignment controls *responsibility + notifications + “Assigned to me” UX*.
- Strengthen **multi-tenant isolation** and SuperAdmin tenant management (manual billing metadata).
- Standardize **India-style UX**: DD/MM/YYYY, IST, ₹, FY (Apr–Mar) for the most visible areas first.
- Add a safe **Full Screen toggle** in the main header.

---

## 2) Implementation Steps

### Phase 1 — Core Flow POC (Isolation): Task visibility + assignment + tenant safety
**Goal:** prove the most failure-prone workflow works before broad UI tweaks.

**POC work**
1. Backend task visibility gate:
   - Add helper: `can_see_all = has_permission(user, "tasks.delete")`.
   - If not `can_see_all`, `/api/tasks` returns only:
     - tasks assigned to the user (via user→employee mapping), OR
     - tasks belonging to projects where the user’s employee_id is in `projects.team_ids` or `project_manager_id`.
2. Assignment model (no rebuild):
   - Normalize assignments in tasks:
     - keep `assignee_id/assignee_name` for backward compatibility,
     - use `assignees: [employee_id]` for multi-assign.
   - On create/update: notify **all assignees** (not only legacy assignee_name).
3. Tenant safety quick checks:
   - Add/extend a pytest-style isolation test using existing `/api/platform/isolation-check`.
   - Verify task listing cannot leak tasks across orgs.

**User stories (POC)**
1. As an Employee, I only see tasks for projects I’m on or tasks assigned to me.
2. As a PM/Admin, I can still see all tasks in the tenant.
3. As an Admin, assigning a task to multiple employees sends notifications to each.
4. As an Employee, I can open “Assigned to me” tasks and update status to done.
5. As a SuperAdmin, I can run isolation-check and see PASS/FAIL with details.

**Exit criteria:** automated tests confirm the restricted visibility rules + no cross-tenant leakage.

---

### Phase 2 — V1 App Development: Project team selection + task assignment UX + vendor link
**Backend**
1. Projects create:
   - Extend `ProjectIn` to accept `project_manager_id` + `team_ids` (persist on create).
2. Tasks:
   - Ensure `vendor_id` is supported on create/update (already in model/router) and consistently backfills `vendor_contact`.
   - Expand notification emission to all `assignees`.

**Frontend**
1. **Projects create** (`Projects.jsx`):
   - Load employees.
   - Add PM dropdown + Team multi-select (reuse selection UI patterns from ProjectDetail team modal).
   - Remove default 0 budget (initial `""`, placeholder “Enter Budget (₹)”).
2. **Tasks** (`TasksBoard.jsx`, `TaskDetail.jsx`):
   - Replace free-text “Assignee name” with employee picker:
     - multi-select assignees,
     - store primary `assignee_id/name` for display compatibility.
   - Add “Assigned to me” badge + quick filter.
   - Show “Task assigned to me by Admin” using `created_by_name/assigned_by` meta.
3. Keep vendor follow-up flow:
   - Retain existing Vendor Master picker (`task-vendor-picker`) and display vendor card in Task detail.

**User stories (Phase 2)**
1. As an Admin, while creating a project I can pick PM + team members.
2. As an Employee, I can see all tasks for projects I’m part of.
3. As an Admin, I can assign multiple employees to a task via picker.
4. As an Employee, I can quickly filter “Assigned to me” and mark tasks complete.
5. As a PM, I can create vendor tasks and pick a Vendor from master for follow-ups.

**Exit criteria:** 1 full end-to-end run (create project + team → create task → employee sees it → completes it).

---

### Phase 3 — Usability + India-style formatting + zero-default cleanup
1. Shared formatting util (frontend): `src/lib/format.js`
   - `formatDateIN(ymd)` → DD/MM/YYYY
   - `formatDateTimeIST(iso)`
   - `formatINR(amount)`
   - `dateForInput(iso|ymd)`
2. Apply to most visible areas first:
   - Header clock (IST), Projects, Tasks, Invoices/Expenses key date chips.
3. Remove default `0` from numeric inputs across modules (targeted edits):
   - Projects/ProjectDetail, QuotationBuilder, EmployeeDetail (salary fields), PurchaseOrders, Invoices, Vendors, Leads, Attendance configs.
   - Rule: if value is null/undefined, render `""` with placeholder; preserve real values.

**User stories (Phase 3)**
1. As a user, all dates display in DD/MM/YYYY consistently.
2. As a user, times feel local (IST) and match my expectations.
3. As a user, I see ₹ formatting consistently across summaries.
4. As a user, empty numeric fields show helpful placeholders instead of “0”.
5. As a user, existing numeric values remain unchanged and readable.

---

### Phase 4 — Tenant → Team & Roles + SuperAdmin tenant billing + Full Screen
1. Tenant Team & Roles verification (RBACAdmin):
   - Ensure list endpoints are tenant-scoped and show correct tenant users.
   - Confirm role permissions remain tenant-specific (existing override system).
2. SuperAdmin tenant management enhancements:
   - Add manual billing sub-doc to org (no payment gateway):
     - `owner_override`, `amount_charged`, `maintenance_charge`, `start_date`, `renewal_date`.
   - `GET /platform/orgs` attaches:
     - owner (primary Admin),
     - billing fields passthrough,
     - health summary already exists.
   - Update `SuperAdminPanel.jsx` table + modals to view/edit billing.
3. Full-screen toggle:
   - Add button near `NotificationBell` in `Layout.jsx`.
   - Uses `document.documentElement.requestFullscreen()` / `document.exitFullscreen()`.

**User stories (Phase 4)**
1. As a Tenant Admin, I see only my tenant’s users in Team & Roles.
2. As a SuperAdmin, I can see each tenant’s owner, plan, billing fields, and status.
3. As a SuperAdmin, I can edit billing fields without affecting tenant data.
4. As a user, I can enter and exit full-screen mode instantly.
5. As a SuperAdmin, I can verify isolation and trust tenants never see each other.

---

## 3) Next Actions
- Implement Phase 1 core visibility gate + assignment notifications.
- Implement Phase 2 project-create team selection + task assignee picker + “Assigned to me” UX.
- Implement Phase 3 formatting util + targeted date/numeric cleanup.
- Implement Phase 4 SuperAdmin billing fields + full-screen toggle + Team/Roles verification.
- Run `testing_agent_v3` after each phase (required) using:
  - Admin: `admin@designsaga.com` / `Admin@123`
  - SuperAdmin: `designsaga10@gmail.com` / `Admin@123`
  - Create a restricted Employee user for visibility tests.

---

## 4) Success Criteria
- Regular employees only see tasks for their project team + tasks assigned to them; privileged roles see all.
- Project create supports PM + team selection; task assignment supports multi-employee tagging.
- Vendor tasks can link a vendor from master (`vendor_id`) and show vendor context.
- Numeric inputs show placeholders instead of default “0” when empty.
- Dates are consistently DD/MM/YYYY and key times are IST in the most visible UI.
- SuperAdmin can view/manage tenants with owner + manual billing fields; isolation-check shows PASS.
- Full-screen toggle works without breaking navigation/responsiveness.
