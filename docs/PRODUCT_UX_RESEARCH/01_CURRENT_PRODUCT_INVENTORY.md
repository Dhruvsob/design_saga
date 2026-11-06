# 01 — Current product inventory (from source, commit 34210dd)

Generated from `frontend/src/App.js`, `components/Layout.jsx` and each page file.
Counts are literal occurrences in the page file (components it imports are not
counted), so they indicate size/complexity, not exact UI element totals.

## Sidebar (Layout.jsx)

| Group | Items (route · permission) |
|---|---|
| — | Dashboard `/dashboard` · dashboard.read |
| Sales | Leads `/crm` · leads.read; Clients `/clients` · clients.read; Quotations `/quotations` · quotations.read |
| Projects | Projects `/projects` · projects.read; Tasks `/tasks` · tasks.read; Calendar `/calendar` · calendar.read |
| Procurement | Vendors `/vendors` · vendors.read; Purchase Orders `/purchase-orders` · purchase_orders.read |
| Finance | Invoices `/invoices`; Accounting `/accounting` · finance.read; Expenses `/expenses`; Loans & EMI `/loans` |
| People | Employees `/employees`; Attendance `/attendance`; Holidays `/holidays` |
| Administration | Company `/settings/company` · admin; Team & Roles `/admin/rbac` · users.read; Audit Log `/settings/audit` · admin |
| Platform | Super Admin `/super-admin` · platform owner only |

Header: breadcrumb, global search (Ctrl+K command palette), date/time, full
screen, notifications, App lock. Public routes: `/`, `/privacy`, `/portal/:token`
(client portal).

## Screens

| Route | Page | Lines | Buttons | Tables | API calls | Internal sections / tabs |
|---|---|---:|---:|---:|---:|---|
| /dashboard | Dashboard | 379 | 3 | 0 | 1 | (cards; Getting started checklist) |
| /crm | Leads | 417 | 14 | 0 | 11 | pipeline |
| /clients | Clients | 213 | 6 | 1 | 5 | — |
| /clients/:id | ClientDetail | 278 | 6 | 1 | 5 | Projects, Invoices, Ledger, Activity |
| /quotations | QuotationsAdv | 184 | 4 | 1 | 6 | — |
| /quotations/:id | QuotationBuilder | 885 | 28 | 3 | 7 | Turnkey: Overview, BOQ Builder, Rooms, Materials, Costing, Payment Plan, Timeline, Terms, Versions, Preview · Consultancy proposal: Proposal, Fees & schedule, Terms, Versions, Preview |
| /projects | Projects | 317 | 8 | 1 | 4 | grid/list, stage filter |
| /projects/:id | ProjectDetail | 647 | 19 | 0 | 13 | Overview, Phases, Tasks, Milestones, Vendors, Files, Invoices, Activity |
| /tasks | TasksBoard | 735 | 16 | 1 | 10 | board/list |
| /tasks/:id | TaskDetail | 450 | 10 | 0 | 7 | Overview, Follow-ups, Comments, Timeline |
| /calendar | Calendar | 687 | 23 | 0 | 9 | month/week/day, Google sync |
| /vendors | Vendors | 334 | 4 | 1 | 4 | — |
| /vendors/:id | VendorDetail | **1471** | **39** | 5 | 31 | overview, commercial, ledger, bills, payments, commissions, projects, documents, performance (9) |
| /purchase-orders | PurchaseOrders | 425 | 17 | 4 | 11 | POs, GRN |
| /invoices | Invoices | 336 | 13 | 1 | 10 | — |
| /accounting | Accounting | **1883** | **40** | **15** | 33 | dashboard, income, expense, Collections Due, daybook, chart of accounts, ledgers, bank, commissions, recurring, reports, balance sheet, cash flow, validation (**14**) |
| /expenses | Expenses | 367 | 12 | 2 | 9 | — |
| /loans | Loans | 421 | 10 | 2 | 9 | — |
| /employees | Employees | 224 | 3 | 1 | 4 | — |
| /employees/:id | EmployeeDetail | **1313** | 25 | 2 | 27 | Overview, Employment, Salary & Bank (pay salary, advances, revisions, history), Documents, Performance, ERP Access |
| /attendance | Attendance | **1879** | **39** | 6 | **42** | dashboard, me, live, monthly, leaves, requests, geo, payroll, setup (**9**) |
| /holidays | Holidays | 201 | 3 | 1 | 3 | — |
| /admin/rbac | RBACAdmin | 575 | 11 | 3 | 10 | users, roles/permissions |
| /settings/company | CompanySettings | 318 | 5 | 0 | 2 | branding, profile, masters |
| /settings/audit | AuditLog | 131 | 3 | 1 | 3 | — |
| /super-admin | SuperAdminPanel | 960 | 26 | 2 | 15 | organisations, analytics, pending sign-ups, health |

## What the numbers already say (verified from source)

1. **Four overloaded screens** carry most of the product: Accounting (14
   sections, 1,883 lines), Attendance (9 sections, 42 API calls), VendorDetail
   (9 tabs, 39 buttons) and EmployeeDetail (6 tabs, 27 API calls). These are
   the first candidates for information-architecture work.
2. **Same subject, several places** (to be confirmed in the browser before any change):
   - Commissions: Accounting > Commissions and Vendor > Commissions.
   - Expenses: sidebar Expenses page and Accounting > Expense section.
   - Payroll: Attendance > Payroll and Employee > Salary & Bank > Pay salary.
   - Money in: Invoices (record payment), Accounting > Income, Accounting > Collections Due.
   - Holidays has its own sidebar item although it belongs to attendance/leave.
3. **Dashboard** route has no permission guard in `App.js` while the sidebar item
   requires `dashboard.read` (behaviour to verify for restricted roles).
