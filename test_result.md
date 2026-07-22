## user_problem_statement
Iteration v2.3 of the Design Saga ERP: land P2 (Notification Center — global bell + all module emitters) AND P6 subset (Balance Sheet, Cash Flow, Enhanced Financial Dashboard, CSV exports on every report). Preserve everything from v2.2.

## backend:
  - task: "Notification Center — collection, emitters, endpoints"
    implemented: true
    working: "NA"
    file: "backend/core/notifications.py, backend/routes/notifications.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            New `db.notifications` collection with schema {id, user_id, kind, title,
            body, link, priority, read, meta, dedup_key, created_at}.
            `core/notifications.py` provides `emit(user_ids, kind, title, body, link,
            priority, meta, dedup_key)` + `emit_admins()`, `emit_finance()`, `emit_hr()`
            broadcasters. Dedup via `(user_id, dedup_key)` uniqueness — safe to re-emit.
            Endpoints:
              GET  /api/notifications?unread_only=&kind=&limit=
              GET  /api/notifications/unread-count
              POST /api/notifications/{id}/read
              POST /api/notifications/mark-all-read
              DELETE /api/notifications/{id}
              POST /api/notifications/scan  — idempotent daily scanner. Emits
                vendor_bill_due/overdue, invoice_due/overdue, milestone_due/overdue,
                task_overdue notifications to the right audiences (finance for financial
                items, individual assignees for tasks).

  - task: "Emit notifications from existing flows"
    implemented: true
    working: "NA"
    file: "backend/routes/tasks.py, backend/routes/attendance.py, backend/routes/auth.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            - Task create → 'task_assigned' notif to the assignee (skips self-assignment).
            - Leave create → 'leave_request' to HR + Admins.
            - Leave action (approve/reject) → 'leave_decided' to requester.
            - RBAC approval → 'account_approved' notif to the newly-approved user.
            - All emits wrapped in try/except so notification failures never break the parent flow.

  - task: "Accounting · Balance Sheet report"
    implemented: true
    working: "NA"
    file: "backend/routes/accounting.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/accounting/reports/balance-sheet?as_of=YYYY-MM-DD
            Returns: {assets:{rows,total}, liabilities:{rows,total},
                      equity:{rows,total,net_income,total_with_net_income},
                      total_assets, total_liabilities_and_equity, balanced}
            The `balanced` flag is Assets ≈ Liab + Eq + Net Income (0.01 tolerance).

  - task: "Accounting · Cash Flow statement"
    implemented: true
    working: "NA"
    file: "backend/routes/accounting.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/accounting/reports/cash-flow?from_date=&to_date=
            Bucketed by journal_entry.source into inflows (income, client_payment, other)
            and outflows (expense, vendor_payment, payroll, other). Includes opening &
            closing bank/cash balance. Verified against journal in smoke test.

  - task: "Accounting · Extended Financial Dashboard"
    implemented: true
    working: "NA"
    file: "backend/routes/accounting.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/accounting/dashboard/extended
            Returns: {receivables:{total,overdue}, payables:{total,overdue},
                      monthly_trend:[{key,income,expense,profit} x 12 months],
                      expense_breakdown:[{category,amount} top 10 for current month]}
            All values pulled from real journal_entries + vendor_bills + invoices.

  - task: "Accounting · CSV export endpoints (5 files)"
    implemented: true
    working: "NA"
    file: "backend/routes/accounting.py"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/accounting/reports/pl.csv, /trial-balance.csv, /balance-sheet.csv,
            /cash-flow.csv, and /api/journal-entries.csv — each returns text/csv with
            Content-Disposition attachment. Journal export supports filters
            ?project_id=, ?client_id=, ?vendor_id=, ?source=, ?from_date=, ?to_date=.

## frontend:
  - task: "Notification bell (top-right of Layout) — real-time badge + dropdown"
    implemented: true
    working: "NA"
    file: "frontend/src/components/NotificationBell.jsx, frontend/src/components/Layout.jsx"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            NotificationBell polls GET /api/notifications every 30 s, shows red badge
            with unread count (99+ if over). Dropdown lists items sorted unread-first,
            with kind pill, title (clickable → deep link), body, relative time, and
            per-row "mark read" + "dismiss" buttons. Header has a manual "scan" refresh
            (calls /notifications/scan) plus "Mark all read".
            testids: top-notifications-btn, notif-badge, notif-panel, notif-row-{id},
                     notif-read-{id}, notif-dismiss-{id}, notif-scan-btn,
                     notif-mark-all-btn.

  - task: "Accounting page — Balance Sheet + Cash Flow tabs"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Accounting.jsx"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Two new tabs appended after "Reports": Balance Sheet (Scales icon) and
            Cash Flow (Waves icon). Both fetch on activation and render KPI strips +
            structured sections. Balance Sheet shows the reconciliation banner
            (green if balanced, red otherwise). Cash Flow shows opening → inflows →
            outflows → closing with color-coded totals.
            testids: tab-balance, tab-cashflow, balance-sheet-tab, cashflow-tab,
                     dl-bs-csv, dl-cf-csv.

  - task: "Accounting Reports tab — CSV download buttons"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Accounting.jsx"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Added inline buttons at the top of Reports: P&L CSV, Trial Balance CSV,
            Journal CSV. Each fetches with credentials and triggers a file download.
            testids: dl-pl-csv, dl-tb-csv, dl-journal-csv.

## metadata:
  created_by: "main_agent"
  version: "2.3"
  test_sequence: 3
  run_ui: true

## test_plan:
  current_focus:
    - "Notification Center — collection, emitters, endpoints"
    - "Emit notifications from existing flows"
    - "Accounting · Balance Sheet report"
    - "Accounting · Cash Flow statement"
    - "Accounting · Extended Financial Dashboard"
    - "Accounting · CSV export endpoints (5 files)"
    - "Notification bell (top-right of Layout) — real-time badge + dropdown"
    - "Accounting page — Balance Sheet + Cash Flow tabs"
    - "Accounting Reports tab — CSV download buttons"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: >-
        v2.3 lands the Notification Center (P2) + a focused Accounting Upgrade (P6).
        Zero rewrites — new endpoints & UI surfaces only.

        Focused test surface:

        BACKEND (already curl-verified):
         1. GET /api/notifications returns {unread_count, notifications: []}.
         2. Assigning a task to another user (POST /api/tasks with assignee_id) emits
            a 'task_assigned' notification visible to that user. Assigning to yourself
            does NOT emit.
         3. Submitting a leave request (POST /api/leaves) emits 'leave_request' to
            HR + Admins. Approving it emits 'leave_decided' to the requester.
         4. Admin approving a pending user via /api/rbac/users/{id}/approve emits
            'account_approved' to that user.
         5. POST /api/notifications/scan is idempotent — running it twice on the same
            day inserts each notification only once (verify via unread count).
         6. GET /api/accounting/reports/balance-sheet returns balanced=true after
            posting a symmetrical journal (income + expense).
         7. GET /api/accounting/reports/cash-flow — opening+net_change == closing.
         8. GET /api/accounting/dashboard/extended — receivables + payables reflect
            actual invoice/bill data.
         9. GET /api/accounting/reports/pl.csv (and the four other CSV endpoints)
            returns text/csv with a filename in Content-Disposition. RBAC: finance.read
            is required (403 for Employee).

        FRONTEND (please test):
        10. As Admin, top-right bell shows red badge with unread count. Clicking
            it opens the dropdown. Task/leave/RBAC notifications appear correctly.
            'Mark all read' clears the badge. 'Scan' refreshes.
        11. Accounting page → tab 'Balance Sheet' renders KPIs + Assets & Liab+Equity
            sections and the green 'balanced' banner. 'Cash Flow' tab shows
            opening → inflows → outflows → closing with KPI strip.
        12. Reports tab has three CSV buttons (P&L / Trial balance / Journal); each
            triggers a browser download.
        13. Bell hidden and Accounting reports gated behind finance.read for
            Designer/Employee roles.

        Test credentials: /app/memory/test_credentials.md
        Special: stable_testtok_do_not_delete (Admin), pmanager@ds.co / DS0001 /
        Test@1234 (ProjectManager).
