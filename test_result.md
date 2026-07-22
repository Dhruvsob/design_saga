## user_problem_statement
Iteration v2.4: extend the existing Vendor module with commission/incentive/rebate management. Do NOT rebuild. Reuse vendors_acc + vendor_bills + journal_entries. Auto-compute commissions on bill create, auto-post journal entry (DR Bank · CR Vendor Commission Income) when commission is received. Add a Commercial tab + Commissions tab in the vendor detail page and a cross-vendor Commissions dashboard tab in Accounting.

## backend:
  - task: "Commission master config on vendor (percentage / fixed / slab)"
    implemented: true
    working: "NA"
    file: "backend/models/vendor.py, backend/routes/vendors.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            New embedded `commission` object on vendors_acc with fields
            {applicable, type in ('fixed','percentage','slab','category','project','none'),
             percentage, fixed_amount, slabs:[{min_purchase,max_purchase,percentage}],
             min_purchase, effective_from, effective_to, notes, income_label}.
            Endpoints:
              PATCH /api/vendors/{id}/commercial  (idempotent, triggers full recompute
                    for all existing bills of that vendor)
              GET   /api/vendors/{id}/commercial
              GET   /api/vendors/commissions/meta  (COMMISSION_TYPES / STATUSES)

  - task: "Auto-compute commission on vendor bill create / update"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py (_compute_commission_for_bill)"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Called from `create_vendor_bill` and `update_vendor_bill`. Purchase base
            = bill.subtotal (pre-tax, pre-tds). Handles fixed / percentage / slab
            math + min_purchase threshold + effective-date window. On cancelled bill:
            cancel the linked commission row (kept for audit). If a commission is
            already 'received', we do NOT overwrite it — just log a
            `recompute_variance` for auditing. Idempotent.

  - task: "Commission list + ledger per vendor"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/vendors/{id}/commissions?status=
            GET /api/vendors/{id}/commission-ledger — returns {vendor, config,
                totals:{total_purchase,total_earned,total_received,pending}, entries[]}

  - task: "Receive commission → posts a balanced Income journal entry"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            POST /api/vendors/{id}/commissions/receive
            body {amount, received_date, bank_account_id, payment_method, reference?, notes?, commission_ids?}
            Requires `finance.create`. Posts a JE with source='commission_income' — 2 lines,
            DR chosen Bank/Cash · CR income account matching cfg.income_label
            (default: 'Vendor Commission Income'). Settles specified commission rows
            or FIFO across pending/invoiced. Persists a `commission_settlements` doc
            with per-row splits + unallocated (on-account) balance. Also updates each
            settled commission row's status → 'received' or 'invoiced' as appropriate.

  - task: "Cross-vendor commission dashboard + report + CSV"
    implemented: true
    working: "NA"
    file: "backend/routes/vendors.py"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            GET /api/commissions/dashboard → {totals:{total_earned,total_received,pending,
                this_month,this_month_received}, top_vendors[<=10], by_project[<=20]}
            GET /api/commissions/report?vendor_id=&project_id=&status=&from_date=&to_date=
              → {filters, totals:{earned,received,pending,count}, rows[]}
            GET /api/commissions/report.csv → text/csv attachment.

  - task: "Idempotent COA seed — auto-installs new default income accounts"
    implemented: true
    working: "NA"
    file: "backend/routes/accounting.py (_seed_coa_if_empty)"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Previously bailed if any accounts existed → new default accounts
            (Vendor Commission Income, Referral Income, Incentive Income) never got
            installed on existing DBs. Now it inserts only the missing names on
            every call. Fires from /api/accounts and POST /api/accounting/seed-coa.

## frontend:
  - task: "Vendor detail — Commercial tab (commission config UI)"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/VendorDetail.jsx (Commercial)"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            New tab 'Commercial' between Overview and Ledger. Applicable toggle,
            type selector (percentage/fixed/slab/category/project/none), rate/amount
            fields, min purchase threshold, effective date window, income label,
            slabs sub-editor for slab type. Right-hand summary card shows live
            totals (total purchase / earned / received / pending) once the config
            has been saved.
            testids: commercial-tab, cm-applicable, cm-type, cm-pct, cm-fixed, cm-save.

  - task: "Vendor detail — Commissions tab (list + record received)"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/VendorDetail.jsx (Commissions)"
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            New tab 'Commissions' between Payments and Projects. 4-KPI strip,
            'Record commission received' form (amount + date + bank picker +
            payment method + reference + settle checkboxes), and the row-per-bill
            table with earned/received/status.
            testids: commissions-tab, receive-cm-btn, rcm-amount, rcm-bank, rcm-submit,
                     cm-row-{id}.

  - task: "Accounting — new 'Commissions' dashboard tab"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Accounting.jsx (CommissionsDashboard)"
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: >-
            Cross-vendor snapshot appended to the Accounting tab bar. KPIs
            (Total earned / Received / Pending / This month), Top vendors list,
            By-project list, CSV download button.
            testids: commissions-dashboard-tab, dl-cm-csv.

## metadata:
  created_by: "main_agent"
  version: "2.4"
  test_sequence: 4
  run_ui: true

## test_plan:
  current_focus:
    - "Commission master config on vendor (percentage / fixed / slab)"
    - "Auto-compute commission on vendor bill create / update"
    - "Commission list + ledger per vendor"
    - "Receive commission → posts a balanced Income journal entry"
    - "Cross-vendor commission dashboard + report + CSV"
    - "Idempotent COA seed — auto-installs new default income accounts"
    - "Vendor detail — Commercial tab (commission config UI)"
    - "Vendor detail — Commissions tab (list + record received)"
    - "Accounting — new 'Commissions' dashboard tab"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: >-
        v2.4 lands Vendor Commission Management as an extension to the existing
        Vendor module. Zero rewrites. Reuses vendors_acc + vendor_bills +
        journal_entries + accounts.

        Curl-verified end-to-end:
          - Vendor ACME set to 10% percentage commission.
          - Existing bill (subtotal ₹50,000) → auto-computed commission ₹5,000
            with status 'pending'.
          - Receive ₹5,000 → posts JE 'commission_income' (DR Bank 5000 · CR
            Vendor Commission Income 5000). Commission row status → 'received'.
          - P&L now includes 'Vendor Commission Income: ₹5,000'.
          - Dashboard totals: earned 5,000, received 5,000, pending 0.
          - CSV report downloads OK.

        Please validate on top of an already-seeded environment. To create the
        test vendor + bill (if the stub in DB is gone):
          POST /api/vendors     name=ACME agency_type=supplier
          POST /api/vendor-bills vendor_id=<vid> bill_date=today items=[{qty:2,rate:25000}] tax_rate=18 tds_rate=1
          PATCH /api/vendors/<vid>/commercial {"applicable":true,"type":"percentage","percentage":10}
          Verify GET /api/vendors/<vid>/commissions shows one row w/ amount = 5000.

        Fixed as I coded:
          - The COA seed used to short-circuit when accounts existed → new default
            income accounts never propagated. Now upsert-style. Auth agent should
            regression-test that GET /api/accounts still lists the pre-existing
            36 accounts + the 3 new ones (Vendor Commission Income, Referral
            Income, Incentive Income).

        Test creds: /app/memory/test_credentials.md — stable_testtok_do_not_delete
        (Admin), pmanager@ds.co / DS0001 / Test@1234 (ProjectManager).
