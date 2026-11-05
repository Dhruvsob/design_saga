# Edit, Delete and Correction Capability Matrix

Last reviewed: 2026-11-03 (Asia/Kolkata)

This matrix records the actual repair-branch behavior. `Delete` means physical
deletion only for safe unposted data. Posted financial records are corrected by
reversal/reposting and remain auditable.

| Area | Authoritative record/workflow | Current safe correction behavior | Remaining verified gap |
|---|---|---|---|
| Vendor master/projects | `vendors_acc` | Edit profile, commercial terms and project assignments; archive preserves history | None confirmed locally; live role validation pending |
| Vendor bills | `vendor_bills` + linked journal | Edit safe metadata; delete draft; cancel posted records with accounting protection | Live bill/project/report reconciliation pending deployment |
| Vendor payments | `vendor_payments` + journal | Reference/notes edit through the source record and synchronize the linked journal; financial corrections reverse the payment and restore bill allocations/balances | No in-place financial edit by design; reverse/repost is authoritative |
| Vendor commissions | `vendor_commissions` + `commission_settlements` | Planned commission edit/cancel; receipt reference/notes synchronize with its journal; receipt Delete from Vendor or Accounting routes through a balanced reversal and rebuilds allocations/journals | Tax-policy acceptance remains external |
| Vendor documents | Embedded vendor documents/object storage | Add/delete and edit label/type/expiry metadata with ownership checks | File replacement intentionally requires delete/re-upload |
| Purchase orders/GRNs | `purchase_orders`, `goods_receipts` | Draft edit, send, cancel; GRN reversal recomputes quantities and match status | Live 3-way-match correction validation pending deployment |
| Invoices/receipts | `invoices` + source-linked journals | Draft edit/delete; issued accrual reversal to Draft; Record Payment; latest receipt reversal restores outstanding/status; branded PDF uses client snapshot, DD/MM/YYYY and wrapped multipage items | Live PDF print review remains pending deployment |
| Quotations | `quotations_adv` | Edit/delete before protected lifecycle stages; versions/change orders preserve accepted history | Final UI consistency review remains |
| Journals/Daybook | `journal_entries` | Direct descriptive metadata edit; posted amount/date correction uses reversal; direct eligible reversals can be undone; vendor payment/commission reference edits route to their source records | Other source-driven entries must be corrected in their source module |
| Expenses | `expenses` + linked journal | Draft edit/delete; approved/reimbursed records use cancellation/reversal safeguards | Live legacy invalid-URL reproduction remains record-specific |
| Payroll/salary | `payroll_runs` + linked journal | Explicit Cash/Bank/date/method/reference; reverse from Employee or Accounting and repost; full employee names shown; generic salary expense path blocked; latest salary revision can be superseded without deleting history | Historical paid runs remain immutable and are corrected only by reversal |
| Employees | `employees` | Profile edit/offboard; documents add/edit/remove; warning/reward add/edit/delete with audit | None confirmed for nonfinancial employee master records |
| Attendance/leave | Attendance, leave and correction collections | Rejected punch retry; correction requests; atomic approval/review; manual authorized adjustment | Approved records intentionally require correction workflow, not hard delete |
| Projects/clients | Project/client masters | Edit; dependency-aware archive/delete; restore | None confirmed locally |
| Leads/tasks/calendar | Respective source records | Edit/delete with module permissions and source visibility rules | None confirmed locally |
| Files | File record + owned storage object | Visibility edit and owned deletion remove stored object safely | Malware scanning remains defense-in-depth follow-up |

## Shared rules

- Tenant scoping is applied by the scoped business database; platform identity
  collections use explicit tenant filters.
- UI permissions never replace backend permission checks.
- Cash/Bank method-account compatibility is enforced by one shared rule
  (`core.finance.validate_method_account`) for payroll, generic money in/out,
  invoice/milestone receipts, vendor commissions and vendor payments; Cash and
  Petty Cash never count as bank accounts even though the default chart flags
  them `is_bank` (DS-076).
- Posted journals are never physically removed through user correction APIs.
- Source-linked transactions are corrected from the source workflow so every
  contextual view continues to reference one authoritative record.
