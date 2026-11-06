# 02 — Coverage matrix

Legend: **S** = source read · **B** = opened in a browser (QA stack) with
screenshot · **E** = covered by an automated end-to-end journey · — = not yet.
"Not inspected" means no visual finding has been made for that screen yet.

| Screen | S | B | E | Notes |
|---|:-:|:-:|:-:|---|
| Dashboard | S | B | E | Getting-started checklist seen 06/11 |
| Leads | S | — | E | not inspected visually |
| Clients / ClientDetail | S | — | E | not inspected visually |
| Quotations list | S | B | E | 06/11 (type cards) |
| Quotation builder — consultancy proposal | S | B | E | 06/11 desktop screenshot |
| Quotation builder — turnkey | S | — | E | PDF rendered 06/11; screen not inspected |
| Projects | S | B | E | 06/11 grid + list |
| ProjectDetail | S | B | E | 06/11; re-check after DS-093 de-duplication pending |
| Tasks / TaskDetail | S | — | E | not inspected visually |
| Calendar | S | — | E | not inspected visually |
| Vendors / VendorDetail | S | — | E | not inspected visually |
| Purchase Orders | S | — | E | not inspected visually |
| Invoices | S | B | E | preview modal fixed 06/11 |
| Accounting (14 sections) | S | partly | E | Collections Due only |
| Expenses | S | — | E | not inspected visually |
| Loans | S | — | — | not inspected |
| Employees / EmployeeDetail | S | partly | E | Salary & Bank (advances) only |
| Attendance (9 sections) | S | — | E | not inspected visually |
| Holidays | S | — | E | not inspected visually |
| Team & Roles | S | — | — | not inspected |
| Company settings | S | partly | E | logo section only |
| Audit log | S | — | — | not inspected |
| Super Admin | S | — | E | subscription control added 06/11; not inspected visually |
| Client portal (public) | S | — | E | not inspected visually |

PDFs rendered and visually reviewed 06/11: consultancy proposal (2 pages),
turnkey quotation (5 pages), invoice (letterhead/logo). Not yet reviewed:
salary slip, receipts, PO, statements.

Breakpoints checked so far: 1440 desktop and 390 mobile on the screens marked
B. Not yet: 1280, 1024, 768.

**Next inspection order:** Accounting (all 14 sections) → VendorDetail →
Attendance → EmployeeDetail → Calendar → Tasks → Leads/Clients → remaining.
