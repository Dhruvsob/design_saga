# Edit, Delete and Correction Capability Matrix

Last reviewed: 2026-11-02 (Asia/Kolkata)

This matrix records the actual repair-branch behavior. `Delete` means physical
deletion only for safe unposted data. Posted financial records are corrected by
reversal/reposting and remain auditable.

| Area | Authoritative record/workflow | Current safe correction behavior | Remaining verified gap |
|---|---|---|---|
| Vendor master/projects | `vendors_acc` | Edit profile, commercial terms and project assignments; archive preserves history | None confirmed locally; live role validation pending |
| Vendor bills | `vendor_bills` + linked journal | Edit safe metadata; delete draft; cancel posted records with accounting protection | Live bill/project/report reconciliation pending deployment |
| Vendor payments | `vendor_payments` + journal | Posted payment is reversed; bill allocations and balances are restored | No in-place financial edit by design; reverse/repost is authoritative |
| Vendor commissions | `vendor_commissions` + `commission_settlements` | Planned commission edit/cancel; receipt reversal rebuilds allocations and journals | Tax-policy acceptance remains external |
| Vendor documents | Embedded vendor documents/object storage | Add/delete and edit label/type/expiry metadata with ownership checks | File replacement intentionally requires delete/re-upload |
| Purchase orders/GRNs | `purchase_orders`, `goods_receipts` | Draft edit, send, cancel; GRN reversal recomputes quantities and match status | Live 3-way-match correction validation pending deployment |
| Invoices/receipts | `invoices` + source-linked journals | Draft edit/delete; issued accrual reversal to Draft; Record Payment; latest receipt reversal restores outstanding/status | PDF date/page-layout polish remains |
| Quotations | `quotations_adv` | Edit/delete before protected lifecycle stages; versions/change orders preserve accepted history | Final UI consistency review remains |
| Journals/Daybook | `journal_entries` | Descriptive metadata edit; posted amount/date correction uses reversal; direct eligible reversals can be undone | Source-driven entries must be corrected in their source module |
| Expenses | `expenses` + linked journal | Draft edit/delete; approved/reimbursed records use cancellation/reversal safeguards | Live legacy invalid-URL reproduction remains record-specific |
| Payroll/salary | `payroll_runs` + linked journal | Explicit Cash/Bank/date/method/reference; reverse run and repost; generic salary expense path blocked | Salary-revision superseding/correction workflow remains |
| Employees | `employees` | Profile edit/offboard; documents add/edit/remove; warning/reward add/edit/delete with audit | Salary-revision superseding remains separate payroll work |
| Attendance/leave | Attendance, leave and correction collections | Rejected punch retry; correction requests; atomic approval/review; manual authorized adjustment | Approved records intentionally require correction workflow, not hard delete |
| Projects/clients | Project/client masters | Edit; dependency-aware archive/delete; restore | None confirmed locally |
| Leads/tasks/calendar | Respective source records | Edit/delete with module permissions and source visibility rules | None confirmed locally |
| Files | File record + owned storage object | Visibility edit and owned deletion remove stored object safely | Malware scanning remains defense-in-depth follow-up |

## Shared rules

- Tenant scoping is applied by the scoped business database; platform identity
  collections use explicit tenant filters.
- UI permissions never replace backend permission checks.
- Cash/Bank method-account compatibility is enforced for payroll, generic money
  in/out, invoice/milestone receipts and vendor commissions.
- Posted journals are never physically removed through user correction APIs.
- Source-linked transactions are corrected from the source workflow so every
  contextual view continues to reference one authoritative record.
