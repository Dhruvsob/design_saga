## user_problem_statement
Master continuation of the Design Saga Architecture & Interior Design ERP.
This iteration (Phase 2 · Item #1) implements **Vendor / Agency Management + Vendor Ledger**
as an end-to-end module that plugs into the existing accounting, tasks and projects
without rewriting any of them.

## backend:
  - task: "Vendor CRUD (extended)"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            New router at /api/vendors with full CRUD.
            GET /api/vendors        (filters: q, agency_type, category, active, project_id; enriched with rollup outstanding)
            POST /api/vendors       (create with extended fields — bank, GST/PAN, TDS, UPI, agency_type)
            GET /api/vendors/meta   (agency_types + bill_statuses enum)
            GET /api/vendors/{id}   (detail: bills, payments, tasks, projects, summary)
            PATCH /api/vendors/{id} (partial update)
            DELETE /api/vendors/{id} (soft delete – audit safe)
            Storage: existing `db.vendors_acc` collection (backward compatible).
            RBAC uses new `vendors.*` permission family — Admin/Director/PM/Accountant can create;
            Designer/Employee read-only; ProjectManager/Accountant can update.

  - task: "Vendor documents (attachments)"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            POST /api/vendors/{id}/documents  (attach — label/url/kind/expires_on)
            DELETE /api/vendors/{id}/documents/{doc_id}

  - task: "Vendor rating + aggregate score"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            POST /api/vendors/{id}/rate  (quality/timeliness/cost/communication 0-5 + comment)
            GET /api/vendors/{id}/ratings (history)
            Auto-updates vendor master `rating` = avg of per-rating overalls.

  - task: "Vendor bills"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            POST /api/vendor-bills   (items + tax + tds → server-computed subtotal/tax/tds/total)
            GET /api/vendor-bills    (filters: vendor_id, project_id, status)
            GET /api/vendor-bills/{id}
            PATCH /api/vendor-bills/{id}
            DELETE /api/vendor-bills/{id} (if paid, becomes soft-cancel instead of hard delete)
            Status auto-refreshes: received → partially_paid → paid, and → overdue when due passes.
            Storage: `db.vendor_bills` (new).

  - task: "Vendor payments (creates balanced journal entry)"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            POST /api/vendor-payments — posts a journal entry
            (DR Accounts Payable · CR Cash/Bank) and settles the specified bills.
            FIFO settle if bill_ids empty. Handles overpayment → `unallocated` on-account.
            GET /api/vendor-payments (filters: vendor_id, project_id)
            DELETE /api/vendor-payments/{id} — reverses the journal entry and refreshes bill statuses.
            Storage: `db.vendor_payments` (new) + reuses `db.journal_entries`.

  - task: "Vendor ledger (running balance)"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/vendors/{id}/ledger?from_date&to_date
            Returns chronological entries (bills CR, payments DR) with running balance
            and totals (billed/paid/outstanding). Verified via curl:
            bill 58500 → pay 30000 → outstanding 28500.

  - task: "Vendor performance score"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/vendors/{id}/performance
            Composite 0-100: completion 30% + on-time 25% + rating 35% + payment reliability 10%.
            Also returns raw components (tasks, ratings, financial).

  - task: "RBAC — new vendors.* permission family"
    implemented: true
    working: "NA"
    file: "backend/core/rbac.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Admin: *.*   |   Director: vendors.*   |   ProjectManager: vendors.read/create/update
            Designer/Employee: vendors.read   |   Accountant: vendors.*   |   HR: (no)   |   Client: (no)
            Designer/Employee correctly blocked from finance.create for bills & payments.

  - task: "Super-admin whitelist (from earlier iteration — still active)"
    implemented: true
    working: true
    file: "backend/server.py"
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: >-
            SUPER_ADMIN_EMAILS env var (default: designsaga10@gmail.com) → auto-elevated
            to Admin on every sign-in; can't be demoted via /api/rbac/users/{id}/role.

## frontend:
  - task: "Vendors list page (/vendors)"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Vendors.jsx"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Editorial-Swiss list with KPI strip (count/contractors/suppliers/outstanding),
            search box + agency_type filter, and a full create form with 3 sections
            (Identity · Compliance · Banking). Row click routes to /vendors/:id.
            data-testids: vendors-page, new-vendor-btn, vendor-search, vendor-filter-type,
            vendor-form, vf-name/vf-phone/vf-agency-type, save-vendor-btn, vendor-row-{id},
            kpi-vendor-count, kpi-vendor-outstanding.

  - task: "Vendor detail page (/vendors/:id) with tabs"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/VendorDetail.jsx"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Header with rating + outstanding KPIs. Tabs: overview | ledger | bills |
            payments | projects | documents | performance.
            Overview panel includes a 4-dimension rating slider + comment.
            Bills tab: create form with server-side tax/tds math; list with paid/outstanding cols.
            Payments tab: settle-multiple-bills UX + bank/cash account selector.
            Performance tab: gauge score + task/rating/payment breakdowns.
            Non-finance users see read-only bills/payments (buttons hidden by hasPerm).
            data-testids include vendor-detail-page, vendor-tab-{name}, new-bill-btn,
            save-bill-btn, new-payment-btn, save-payment-btn, submit-rating-btn, add-doc-btn,
            ledger-row-{i}, bill-row-{id}, payment-row-{id}.

  - task: "Sidebar Vendors nav + route registration"
    implemented: true
    working: "NA"
    file: "frontend/src/components/Layout.jsx, frontend/src/App.js"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            New nav item (HardHat icon, section 06) between Clients and Invoices.
            Routes: /vendors and /vendors/:id, both guarded by requirePerm="vendors.read".
            Sidebar visible sections renumbered (06 → Vendors, 07 → Invoices, …, 12 → Team & Roles).

## metadata:
  created_by: "main_agent"
  version: "2.1"
  test_sequence: 1
  run_ui: true

## test_plan:
  current_focus:
    - "Vendor CRUD (extended)"
    - "Vendor bills"
    - "Vendor payments (creates balanced journal entry)"
    - "Vendor ledger (running balance)"
    - "Vendor performance score"
    - "RBAC — new vendors.* permission family"
    - "Vendors list page (/vendors)"
    - "Vendor detail page (/vendors/:id) with tabs"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: >-
        Phase-2 item #1 (Vendor / Agency Management + Vendor Ledger) is implemented.
        Curl smoke test passes end-to-end (create vendor → attach doc → rate → post 58500 bill
        with 18% GST & 1% TDS → partial pay 30000 via bank_transfer → ledger shows correct
        running balance → performance score computed).
        A stable test admin session is seeded in Mongo:
            token: `stable_testtok_do_not_delete`
            user: `test-admin@ds.co` (role Admin)
        The token works with both Authorization: Bearer header AND as a session_token cookie.
        Please validate all listed backend + frontend tasks. Focus areas:
          1) All new endpoints return correct RBAC 403 for Designer / Employee where applicable.
          2) Bill status auto-transitions (received → partially_paid → paid → overdue).
          3) Payments create a balanced journal entry (verify via GET /api/journal-entries?vendor_id=…).
          4) Ledger totals reconcile with bills − payments.
          5) UI: nav shows "Vendors" for admin, hides for HR role.
          6) UI: /vendors renders list; /vendors/:id renders 7 tabs; forms submit successfully.
