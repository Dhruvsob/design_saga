# 07 — Phased plan (senior review, 07/11/2026)

Method: walked every screen as an admin on the local QA copy (19 pages, screenshots), logged
every failing API call, traced settings to where they really apply, and read the code behind
each finding. Brand colours stay as they are. Each phase ships in small tested batches.

## Phase 1 — Clean up and fix what exists (now)

| # | Where | Finding | Fix |
|---|---|---|---|
| 1.1 | PDFs (invoices, quotations, payslips) | Live DESIGN SAGA company still has the old default brand colour **Klein blue #002FA7**, so every PDF prints in blue, not the brown brand | Treat the old default as "not set" and use the brand taupe; new companies default to brown; Company Settings shows the real PDF colour with a "Use Design Saga colours" reset |
| 1.2 | Vendors, Invoices, Holidays, Audit Log, Quotations | Own one-off headings; two still show slogans ("Every hand that builds…", "Send. Track. Collect.") | Same page header everywhere: page name, count, one-line purpose, main button |
| 1.3 | Dashboard | Footer strip of module names runs off the screen; empty lead funnel draws coloured bars and fills a big card; "₹0" printed twice | Remove strip; compact empty funnel; single value |
| 1.4 | Leads | Drag hint shown twice; empty columns show stray marks | One hint; clean empty columns |
| 1.5 | Attendance | Admin without linked employee triggers 4 failing requests on every visit; lands on an empty "My Attendance" tab; 9 tabs overflow the screen | Skip personal calls when not linked; admins open on Team Dashboard; tabs wrap instead of overflowing |
| 1.6 | Accounting dashboard | "Source" shows raw codes (OTHER_RECEIVABLE_INCOME, PAYROLL_REVERSAL); amounts don't say in or out; "Upcoming payments" are actually money to collect, with no project name; negatives shown as "₹-5,000" | Plain labels; green in / red out; "Due to collect" with project; "−₹5,000" |
| 1.7 | Clients | Type filter stretched across the full width; mixed dash styles | Filter inline with search; one dash style |
| 1.8 | Employees, Vendors | Empty second line under every employee name; unrated vendors show "★ 0.0"; extra "Open" button beside the row's own click and ⋮ | Remove empty line; "Not rated"; drop duplicate button |
| 1.9 | Projects | "#001" number is just the position and changes with sorting; "Unassigned" actually means no client | Remove; say "No client" |
| 1.10 | Sidebar | "Expenses" opens staff claims while company expenses live in Accounting → Expense | Rename to "Expense claims" |

## Status (08/11/2026)

- **Phase 1: done** (1.1–1.10 all shipped; 1.7 was already in place).
- **Phase 2 done:** Invoices search + status filter + received / still-due columns; Collections Due / Payment
  Reminders / Received Payments tabs. **Open:** Payroll as its own page, Attendance tabs 9 → 5, Task filter
  simplification, Calendar legend filters, Company Settings preview alignment, splitting the largest screens.
- **Phase 3 done:** payment reminders (PDF + WhatsApp), cash-basis collections, % fee milestones, signature on PDFs,
  bulk Saturday holidays. **Open:** site visits with photos, live check-in map, drawing register, Gantt,
  lead duplicate warning, Google Calendar (needs keys), client approvals, UPI QR, retainers, BOQ → PO.

## Phase 2 — Reorganise for daily work

- **Payroll** gets its own page under People (now hidden inside Attendance tabs and employee profiles).
- **Attendance** tabs 9 → 5 (Today, Monthly sheet, Leaves, Requests, Settings).
- **Tasks**: 7 filters → search + project + member, rest under "More filters"; lighter cards (status chip repeats the column).
- **Invoices**: search, status filter, outstanding/overdue summary.
- **Calendar**: day numbers aligned in every cell; legend chips work as filters.
- **Company Settings**: aligned preview card; group settings by Brand, Company, Lists.
- Split the three largest screens (Attendance, Accounting, Vendor detail: 1,500–1,900 lines each) so they load faster on phones.

## Phase 3 — New features for an architecture studio

- **Site visits**: check-in on the project site (geofence + map pin), photos with location and time, notes, linked to attendance and the project timeline.
- **Live map** of today's team check-ins (colour pins, office fences).
- **Drawing register**: revisions A/B/C per drawing, issued-to, client approval status.
- **Project timeline** (Gantt by phase) with milestones and fee instalments.
- **Leads**: follow-up reminders on the calendar, duplicate warning by phone/email, source report.
- **Google Calendar two-way sync** (built; needs the studio's Google OAuth keys on the server — owner action).
- **Client portal approvals**: client approves drawings/quotations online.
- **Invoices**: UPI QR on PDF, payment reminders, recurring retainers.
- **BOQ → Purchase order** in one click for turnkey projects.

## Owner actions (cannot be done from code)

Upload the cleaned logo; rotate the Atlas password (SEC-01); decide staff access to all clients/leads (SEC-02);
GST split rules (ACC-02); off-server backups and alerts destination (OPS-02/03); Google OAuth keys for calendar sync.
