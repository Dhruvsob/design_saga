# 06 — Master improvement list (bugs, risks, UX, new features)

Prepared 07/11/2026 from the code, test runs and live checks. Status: **Doing** /
**Next** / **Later** / **Owner decision**. Brand colours stay as they are
(taupe #8B7F6A / button #76705E, cream, off-white, charcoal).

## A. Risks and bugs that can hurt in future (fix first)

| # | Area | Finding (evidence) | Risk | Fix | Status |
|---|---|---|---|---|---|
| R1 | All lists | Backend reads stop at 500–2,000 rows in 65 places (`to_list(500)` etc.); no list has pagination | As data grows, records silently disappear from lists, totals and exports | Server-side pagination + "Load more"/pages on Daybook, Invoices, Tasks, Attendance, Audit, Clients, Leads | Done (DS-100) |
| R2 | Security | The MongoDB Atlas password once exposed in history is not yet rotated (SEC-01) | Anyone with that string could reach old data | Rotate in Atlas, update VPS `.env` | Owner decision |
| R3 | Backups | Backups stay on the same VPS (OPS-02/03) | Disk/VPS loss = data + backups lost together | Nightly copy to off-server storage (e.g. Backblaze/Drive) + failure alert | Owner decision |
| R4 | Calendar | Events accept any `client_id` / `vendor_id` without checking they exist in the tenant | Wrong/foreign links on events | Validate like project links (done for projects in DS-097) | Done (DS-100) |
| R5 | Forms | 17 native `prompt()` popups (Employee, Vendor, Quotation screens) | Ugly, blocked on some mobiles, no validation | Replace with in-app dialogs | Done (DS-099) |
| R6 | Performance | Accounting (1,883 lines), Attendance (1,879), VendorDetail (1,471) load everything at once | Slow on phones as data grows | Split into lazy-loaded sections | Later |
| R7 | Ops | Machine-level: local test DB crashed under memory; no production uptime/error alert | Outages noticed only by users | Uptime ping + error alert to email/WhatsApp | Owner decision (destination) |
| R8 | Permissions | Employee/Designer roles can read all clients and leads (SEC-02) | Staff see all client contacts | Decide policy; restrict if wanted | Owner decision |
| R9 | GST | CGST/SGST vs IGST split and rounding not configurable (ACC-02) | Wrong tax lines for inter-state clients | Add place-of-supply + split | Owner decision |
| R10 | Logo | DESIGN SAGA tenant still has the old JPG with grid | Grid lines on PDFs/sidebar | Owner uploads the cleaned PNG | Owner action |

## B. Whole-app UI/UX

| # | Change | Why | Status |
|---|---|---|---|
| U1 | ⋮ menu on every list (Projects, Leads, Employees, Purchase orders, Expenses, Loans, Holidays, Tasks, Accounting entries, Vendor bills/payments) | Clean rows, consistent actions; done for Invoices, Quotations, Clients, Vendors | Doing |
| U2 | Pagination + "showing 1–50 of 230" on every table | Done for Invoices, Clients, Vendors, Employees (DS-100) |
| U3 | Sticky table headers and sticky first column on wide tables | Easier reading of Daybook/Monthly sheet | Next |
| U4 | Empty states with one clear action ("No vendors yet — Add vendor") | Guides new firms | Done on main lists (DS-103) |
| U5 | Loading skeletons on every page (some show nothing while loading) | Feels faster | Done on main lists (DS-103) |
| U6 | Saved filters per page (remember last filter) | Fewer clicks daily | Later |
| U7 | Keyboard shortcuts: N = new, / = search, Esc = close | Speed for power users | Later |
| U8 | Breadcrumb links clickable back to list | Navigation | Next |
| U9 | Toast "Undo" for archive/delete of drafts | Mistakes are easy to reverse | Later |
| U10 | Dark mode (same browns, dark surfaces) | Comfort at night | Later |

## C. Module by module

**Dashboard** — role-based cards (owner: money; PM: projects/tasks; HR: attendance); "Today" strip (meetings, site visits, due collections); click every number to open the filtered list.

**Leads / CRM** — ⋮ menu; follow-up reminders on calendar; duplicate detection by phone/email; lead → client → quotation → project conversion in one flow; source report.

**Clients** — client 360 page: projects, quotations, invoices, outstanding, files, timeline; WhatsApp/email quick contact buttons.

**Quotations** — duplicate quotation; send by email/WhatsApp link; client e-acceptance link (signature/OTP); versions compare view.

**Projects** — ⋮ menu (Edit, Archive, Duplicate); phase/stage progress bar on card; project budget vs actual chart; site photo gallery per phase; drawing revision register (A, B, C… with approval).

**Tasks / Work board** — subtasks/checklist; recurring tasks; time logging per task; @mentions in comments; "My day" view.

**Calendar** — done: Studio/Project. Next: drag to reschedule events; colour by project; site-visit check-in linking to attendance.

**Vendors / Procurement** — ⋮ on bills/payments/commissions; vendor rating after each job; PO → GRN → bill matching status chips; vendor-wise project ledger.

**Invoices** — ⋮ done; recurring invoices (retainers); payment reminder emails; UPI QR on invoice PDF; aging report (0-30/31-60/60+).

**Accounting** — done: sections grouped Overview / Money in / Money out / Books / Reports / Setup (DS-101). Next: bank statement import with auto-match; GST summary report; cash-flow forecast from collections + bills due; month-end close lock.

**Expenses** — receipt photo upload with amount auto-read (OCR); approval flow; mileage claims.

**Employees / Payroll** — done: advances, salary breakdown. Next: payslip email to employee; bulk "Run payroll for all" with preview; PF/ESI/TDS fields if needed.

**Attendance** — colourful street map (Doing); live map of today's check-ins with pins; selfie on check-in (optional); monthly heat-map calendar per employee; late/absent trend chart.

**Holidays / Leave** — leave calendar for the team; leave balance card on dashboard; carry-forward rules (owner decision).

**Company / Admin** — seats used vs plan (from WorkHand reference); login history; 2-step login for admins.

## D. Order of work

1. Doing now: colourful map (Attendance), replace `prompt()` popups, ⋮ menus on remaining lists.
2. Next: pagination (R1/U2), calendar client/vendor validation (R4), Accounting regrouping, empty states/skeletons.
3. Then module features in the order above, one module per batch, each tested and deployed with your approval.
