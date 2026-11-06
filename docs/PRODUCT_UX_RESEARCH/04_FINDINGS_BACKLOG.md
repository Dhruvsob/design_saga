# 04 — Findings backlog (UX & structure)

Each row is evidence-backed. Implementation is tracked in
`DESIGN-SAGA-REPAIR-TRACKER.md` (DS-xxx) once approved.

| ID | Screen | Priority | Evidence | Finding | Proposed direction | Status |
|---|---|---|---|---|---|---|
| UXR-01 | Accounting | P1 | 14 sections, 1,883 lines, 40 buttons (inventory) | Overloaded single screen; daily tasks (record income/expense, collections, daybook) sit beside rarely used reports and setup | Group by job: Money In · Money Out · Books (daybook, ledgers, chart of accounts) · Reports · Setup; keep one engine | To inspect in browser |
| UXR-02 | Commissions | P1 | Accounting > Commissions and Vendor > Commissions | Same records reachable from two places with separate screens | One authoritative list; Vendor and Project show filtered views with "Open in Accounting" | Verify both write paths |
| UXR-03 | Expenses | P1 | Sidebar Expenses page + Accounting > Expense | Two entry points for money out | Confirm whether they post through the same engine; then keep one entry and link the other | Verify |
| UXR-04 | Payroll | P1 | Attendance > Payroll and Employee > Salary & Bank | Two places to run salary | Attendance shows the monthly sheet; paying happens in one place | Verify |
| UXR-05 | Holidays | P2 | Separate sidebar item under People | Holidays are an attendance/leave setting | Move under Attendance (keep URL) | Proposal |
| UXR-06 | Attendance | P1 | 9 sections, 42 API calls | Employee self-service (me) and HR admin (live, monthly, setup, payroll) share one crowded screen | Split "My attendance" from HR views by role | To inspect |
| UXR-07 | VendorDetail | P1 | 9 tabs, 39 buttons | Vendor 360 is long; commercial/ledger/bills/payments overlap | Overview with balances; Money (bills, payments, commissions, ledger); Projects; Documents | To inspect |
| UXR-08 | ProjectDetail | P1 | Owner feedback 06/11 | Hub tiles duplicated tabs and facts duplicated cards | Fixed in DS-093 (facts + Needs attention) | Done, deploy pending |
| UXR-09 | Team & Roles | P2 | REF-002 | No seat usage / pending invitations shown | Show seats used of plan limit, pending invites | Proposal |
| UXR-10 | Dashboard | P2 | `App.js` route has no permission; sidebar requires dashboard.read | Possible mismatch for restricted roles | Verify with Employee role | Verify |
| UXR-11 | Tasks & Calendar | P2 | REF-003 | Separate pages for related work | Evaluate a Calendar view inside Tasks before adding screens | Proposal |
