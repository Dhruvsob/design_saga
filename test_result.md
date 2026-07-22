## user_problem_statement
System-audit fix pack (Tier A + B + C + D) for the Design Saga Architecture ERP.
Audit revealed: dashboard revenue pulled from wrong source, task↔vendor master
not linked, seed endpoints exposing fake data, no Admin approval gate on new
Google sign-ins, no password login at all. This iteration fixes all four tiers.

## backend:
  - task: "A1 · Dashboard revenue now sourced from accounting journal_entries"
    implemented: true
    working: "NA"
    file: "backend/server.py (dashboard_stats)"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Revenue KPI now = sum(credit − debit) over journal_entries lines
            where account_type == 'income'. Was previously sum(invoices.total)
            where status == 'paid' (two sources of truth). Also reformatted
            the collection-due alert to use ₹ instead of $.

  - task: "A2 · Task → Vendor master link (vendor_id)"
    implemented: true
    working: "NA"
    file: "backend/models/task.py, backend/routes/tasks.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Added `vendor_id: Optional[str]` to TaskIn and TaskUpdate. On task
            creation, if vendor_id is present the vendor_contact block is
            auto-backfilled from vendors_acc so old readers keep working.
            Verified: creating a task with vendor_id=vnd_1f71cd90ee68 populated
            vendor_contact.vendor_name="ACME Carpentry" and phone from master.
            Vendor detail's `tasks` array now includes tasks linked via
            vendor_id primarily (falls back to vendor_contact.vendor_name).

  - task: "A4 · Dashboard team utilization uses real priority-weighted signal"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Was: "count open tasks per assignee" (comment literally said dummy).
            Now: weighted sum (urgent=3, critical=3, high=2, medium=1, low=1)
            and sorted descending. Field name unchanged (load) for backward compat.

  - task: "B1 · Seed endpoints gated behind ENABLE_SEED_DEMO env var"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            /api/seed, /api/quotations-adv/seed and /api/employees/seed each
            return 403 unless env var ENABLE_SEED_DEMO=true. Default: disabled.

  - task: "B2 · Purge of pre-existing fake demo data"
    implemented: true
    working: true
    file: "MongoDB one-shot"
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >-
            Removed 6 leads, 3 clients, 3 projects, 7 tasks, 4 invoices, 3 files
            plus 12 TEST_ users from previous automated runs. Retained real
            accounting (CoA, vendors master, journal entries) and the ACME
            vendor + its bill/payment from vendor-module smoke test.

  - task: "C1 · Admin approval gate for new Google sign-ins"
    implemented: true
    working: "NA"
    file: "backend/server.py (create_session), backend/core/deps.py (require_user)"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            New Google users now land with approval_status='pending' + is_active=false.
            Super-admin & first-ever user bypass approval (auto-Admin, approved).
            require_user (BOTH in server.py and core/deps.py) return 403
            "Your account is awaiting Admin approval." for pending users and 403
            "Your account has been deactivated." for rejected users. Existing
            users grandfathered as approved via one-shot mongosh migration.
            NOTE: `/api/auth/me` still returns the user (with status) so the
            frontend can show a "Pending" screen.

  - task: "C2 · Admin approval / reject / list-pending endpoints"
    implemented: true
    working: "NA"
    file: "backend/routes/auth.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET  /api/rbac/pending                (Admin) — list pending
            POST /api/rbac/users/{id}/approve     (Admin) — body {decision: approve|reject, role?, reason?}
            Approve sets approval_status='approved', is_active=true, assigns role + employee_id (auto DS000N).
            Reject sets approval_status='rejected', is_active=false, invalidates all sessions.

  - task: "D1 · Password login (email OR employee_id)"
    implemented: true
    working: "NA"
    file: "backend/routes/auth.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            POST /api/auth/login-password {identifier, password}
            Identifier can be an email OR a DS0001-style employee_id.
            bcrypt (passlib) for hashing. On success sets the same session_token
            cookie as Google (httpOnly + secure + SameSite=None, 7-day expiry).
            5 failed attempts in 15 minutes → 429 "Too many failed attempts"
            (via login_attempts collection). Pending users → 403 with
            "awaiting Admin approval"; rejected → 403 with "deactivated".

  - task: "D2 · Admin creates user with password + Reset password"
    implemented: true
    working: "NA"
    file: "backend/routes/auth.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            POST /api/auth/register (Admin only). Body: email, password (>=6),
            name, role, phone, approve_immediately (default true). Auto-assigns
            next sequential DS0001, DS0002…
            POST /api/auth/reset-password/{user_id} (Admin only). Body:
            new_password. Kills all active sessions for the target user.
            POST /api/auth/change-password (self). Body: old_password, new_password.
            Returns 400 for Google-only users (no existing hash).

  - task: "Refactor · Deduplicated ROLE_PERMISSIONS between server.py and core/rbac.py"
    implemented: true
    working: "NA"
    file: "backend/server.py, backend/core/rbac.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Was: two ROLE_PERMISSIONS dicts (server.py and core/rbac.py) drifting apart —
            Director in server.py lacked vendors.* and finance.*. Now server.py
            imports ROLES, ROLE_PERMISSIONS, normalize_role, expand_permissions,
            has_permission directly from core.rbac. Single source of truth.
            core.rbac exports LEGACY_ROLE_MAP too (public alias).

## frontend:
  - task: "Login page — password form + Emergent Google button both present"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Login.jsx"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Preserved editorial layout + Google flow. Added below the Google
            button (with an OR divider) a compact 2-field form (identifier + password).
            data-testids: login-google-btn, password-login-form, login-identifier,
            login-password, login-password-btn, login-error.
            The Emergent Google URL and redirect logic are untouched
            (kept the DO-NOT-HARDCODE-URL guardrails).

  - task: "Pending-approval / rejected screen in ProtectedShell"
    implemented: true
    working: "NA"
    file: "frontend/src/App.js, frontend/src/context/AuthContext.js"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            AuthContext exposes isPending / isRejected booleans and loginWithPassword().
            ProtectedShell shows a dedicated "Awaiting Admin approval" or
            "Account deactivated" screen with a Sign-out button. PublicRoot also
            forwards pending users to /dashboard so they land in that screen
            consistently (never on the login page while an active session exists).
            data-testids: pending-approval-screen, pending-signout-btn.

  - task: "RBAC Admin — Pending approvals + Create user + Reset password"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/RBACAdmin.jsx"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Full rewrite of RBACAdmin (backward-compatible URL /admin/rbac):
             • Pending-approvals section at top (row-per-user with role picker + Approve/Reject).
             • Team members table gains Employee ID + Status pill (approved / pending / deactivated).
             • Create-user form (email, password, role, name, phone, approve toggle).
             • Reset-password modal per user (all sessions get killed on save).
            data-testids: rbac-page, create-user-btn, cu-name/email/password/role, cu-submit,
             pending-section, pending-row-{uid}, approve-{uid}, reject-{uid},
             reset-pwd-{uid}, reset-pwd-modal, reset-pwd-input, reset-pwd-submit.

  - task: "A3 · Vendor picker in Accounting Expense form"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Accounting.jsx"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            "Vendor id (optional)" text input replaced with a <select> populated
            from /api/vendors. data-testid: expense-vendor-select.

  - task: "A2b · Vendor picker in Task form (task_type=vendor)"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/TasksBoard.jsx"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            When creating a Vendor-type task, a "Pick from Vendor master" dropdown
            auto-fills vendor_contact (name, company, contact_person, phone, email)
            AND stores vendor_id. The manual name field is retained as an ad-hoc fallback.
            data-testid: task-vendor-picker.

## metadata:
  created_by: "main_agent"
  version: "2.2"
  test_sequence: 2
  run_ui: true

## test_plan:
  current_focus:
    - "A1 · Dashboard revenue now sourced from accounting journal_entries"
    - "A2 · Task → Vendor master link (vendor_id)"
    - "B1 · Seed endpoints gated behind ENABLE_SEED_DEMO env var"
    - "C1 · Admin approval gate for new Google sign-ins"
    - "C2 · Admin approval / reject / list-pending endpoints"
    - "D1 · Password login (email OR employee_id)"
    - "D2 · Admin creates user with password + Reset password"
    - "Login page — password form + Emergent Google button both present"
    - "Pending-approval / rejected screen in ProtectedShell"
    - "RBAC Admin — Pending approvals + Create user + Reset password"
    - "A3 · Vendor picker in Accounting Expense form"
    - "A2b · Vendor picker in Task form (task_type=vendor)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: >-
        Big system-audit fix pack landed (Tiers A + B + C + D). No modules were
        rewritten — only extended. Key verification points:

        BACKEND (already curl-verified end-to-end):
         1. `/api/auth/login-password` with either email or employee_id
            returns {user, session_token}. Sets cookie. 401 on wrong password;
            429 after 5 wrong attempts in 15 min.
         2. `/api/auth/register` creates user with employee_id auto-assigned
            (DS0001, DS0002…). Admin-only (403 for non-Admin).
         3. `/api/auth/reset-password/{uid}` — Admin-only; kills victim's sessions.
         4. `/api/auth/change-password` — self; 400 for Google-only user;
            401 on wrong old_password.
         5. `/api/rbac/pending` — returns pending users; Admin-only.
         6. `/api/rbac/users/{uid}/approve` — decision: approve|reject.
         7. New Google user on next Emergent /auth/session lands as pending
            (except super-admin & first user).
         8. `/api/dashboard/stats` — `kpis.revenue` sums income-account credits
            from journal_entries (verified 0.0 after purge, non-zero after
            posting income via /api/accounting/income).
         9. `/api/seed`, `/api/quotations-adv/seed`, `/api/employees/seed` all
            return 403 with detail mentioning ENABLE_SEED_DEMO env var.
        10. Creating a task with vendor_id auto-fills vendor_contact from master;
            vendor detail page shows the task in its "Assigned tasks" tab.

        FRONTEND:
        11. `/` (Login) — Google button + password form both visible;
            error box shows detail from backend for wrong password.
        12. Pending user hitting any /dashboard etc lands on the
            "Awaiting Admin approval" screen (data-testid pending-approval-screen)
            with a Sign out CTA.
        13. RBAC Admin (`/admin/rbac`) shows Pending Approvals section if any;
            approve/reject buttons update state. "Create user" form issues
            /api/auth/register. Reset-password modal per row.
        14. Accounting > Expense: vendor field is now a <select>
            (expense-vendor-select) populated from /api/vendors.
        15. Tasks > New > Agency/Vendor: picker (task-vendor-picker) auto-fills
            the contact block.

        Test creds are in /app/memory/test_credentials.md.
        Special active session in DB:
            stable_testtok_do_not_delete → Admin (test-admin@ds.co)
            pmanager@ds.co / DS0001 / Test@1234 → ProjectManager
            newbie_tok → pending Google user (for approval-flow test)
        Please run through both backend + frontend flows. Zero regressions
        expected on the previously green Vendor Module.
