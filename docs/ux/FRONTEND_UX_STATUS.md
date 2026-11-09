# Frontend UX status & Claude → Codex handoff

Owner of this file: Claude (frontend, UI/UX, product experience, PDF presentation).
Branch: `claude/ux-product-refinement` (worktree `design_saga-ux-refinement`), based on the integrated baseline `e3ce32b`.
Codex owns backend logic, accounting engine, database, security, CI/infra and integration/deployment.

Resume here next session: read **§4 Open frontend work** and **§5 Codex handoff**; re-run the sweep in §6.

## 1. Sitemap (current, after this batch)

| Sidebar group | Screen | Inside the screen |
|---|---|---|
| — | Dashboard | My day (own tasks, check-in, free leave) · KPI row (money cards by permission) · Alerts · Pipeline + Lead sources (sales roles only) · Team load (managers only) |
| Sales | Leads | Kanban New → Lost; card: type · location · source, budget, Notes, Convert / Project link, ⋮ |
| Sales | Clients → Client | Contact line (call / WhatsApp / email) · Projects · Invoices · Ledger · Activity |
| Sales | Quotations → Quotation | Proposal / Fees / Terms / Versions / Preview; Convert → new or existing project |
| Projects | Projects → Project | **Overview** (Overview, Activity log) · **Work** (Phases, Tasks) · **Design** (Drawings, Files) · **Site** (Site visits, Snags) · **Commercial** (Fee milestones, Invoices, Vendors & purchases); header: Edit, Client portal link, ⋮ (Archive, Reset portal link) |
| Projects | Tasks | Board / List / Calendar; group by status or category; filters project / member |
| Projects | Calendar | All / Studio / Projects; Month / Week / Agenda; legend filters |
| Procurement | Vendors → Vendor | Overview (Details, Performance) · Money (Ledger, Bills, Payments, Vendor incentives, Incentive terms) · Projects · Documents |
| Procurement | Purchase orders | List; row ⋮ Open, Record vendor bill (received POs), Mark sent, Cancel |
| Finance | Invoices | Invoices · Payment Reminders · Collections Due · Received Payments (one Money In strip) |
| Finance | Accounting | One compact section bar: Overview (Dashboard, Health check) · Money in · Money out · Books · Reports · Setup (Chart of accounts, Close & export) |
| Finance | Expense claims, Loans & EMI | Row opens the panel with all role/state actions |
| People | Employees → Employee, Attendance, Live map, Payroll, Holidays | Attendance: Today · Monthly sheet · Leaves · Requests · Settings |
| Administration | Company, Team & Roles, Audit log | — |

Decision: no new modules. Grouping was done *inside* Project, Vendor and Accounting.

## 2. Verified earlier frontend requirements (09/11/2026)

Checked in the running app (desktop 1440 and phone 390, 80 screenshots, console/page errors captured by `e2e/tools/ux-sweep.mjs`):
brand tokens unchanged (`src/index.css`: #8B7F6A, #76705E, #F5F4F0, #FAF9F6, #8B7A55, #EDECE8, #2C2C2C; Playfair Display + Inter); reduced-motion rule present; ⋮ menus on lists; lock button beside notifications; Calendar Studio/Project; Workboard Board/List/Calendar + grouping; Vendor 360; drawing register; snags; period close; collections receipts; My day. No page errors; one phone overflow (Holidays) — fixed in this batch.

## 3. Changes in this batch (UX-xx ids)

| ID | Area | Problem found in the live app | Change |
|---|---|---|---|
| UX-01 | Project | Overview showed `financials.collected` = ₹0 while the project had received money through Collections Due (Fee-milestones tab showed the right figure) — two different "collected" numbers on one page | Overview + "needs attention" use `money` (project value · invoiced · received · still to receive). Backend follow-up CDX-01 |
| UX-02 | Project | 11 tabs in one row; 4 header buttons incl. rare "Reset portal link" | 5 groups with sub-sections; `?tab=` deep link; Archive + Reset portal link in ⋮ |
| UX-03 | Accounting | Section menu was a 6-column block (~180 px) on every Accounting page | One wrapping bar of grouped pills (all sections still one click away) |
| UX-04 | Collections Due | Search + "Add expected collection" floated above the title | Title left, actions right on one row |
| UX-05 | Leads | Source truncated to "W…", full-width Notes button, "₹0" for no budget, duplicate drag hint, Won lead had no link to its project | Compact card; source in meta line; "Budget not set"; Notes inline; **Project →** link for converted leads |
| UX-06 | Client | No way to call/WhatsApp/email from the client page | Contact line with tel:, WhatsApp, mailto; "Add phone or email" when empty |
| UX-07 | Holidays | Phone: header actions ran off-screen; redundant Refresh | Wraps; Refresh removed (year change reloads) |
| PDF-01 | Invoice/quotation PDF | Printed the internal status ("Issued") on the client document | Status shown only when cancelled |
| PDF-02 | Turnkey/consultancy quotation PDF | Black table headers (off-brand), payment-plan amounts as bare "0", "LOCATION -", "AREA 0 sq.ft", signature forced onto an almost empty extra page | Brand-colour headers; amounts as Rs. with Indian grouping or "-"; empty cover rows hidden; signature follows terms when it fits |
| PDF-03 | Payment reminder PDF | "FOR -" when no project | Shows the collection title instead |
| UX-12 | Vendors | "Contractors / Suppliers" cards were almost always 0 | "With bills to pay" count; three cards |
| PDF-04 | Vendor incentive statement PDF | Two-line title, period printed twice, direct incentives as "-, -, Rs. 0.00" | "Incentive statement"; period once; Date / From ("Direct incentive" or "Bill …") / Bill value columns |

PDF changes are presentation-only (labels, colours, layout); no amount, query or calculation changed.
They touch shared backend files — `server.py` (invoice + quotation PDF builders), `routes/money_in.py` (`generate_reminder_pdf`), `routes/finance_extras.py` (statement) — please merge with care (CDX-05).

## 4. Open frontend work (next batches, in order)

| ID | Pri | Item |
|---|---|---|
| UX-10 | — | Decided: keep the Money In strip inside Accounting › Collections Due. Collections Due lives in Accounting and the strip is the only path between the four Money In screens, so it is a cross-link, not a duplicate engine |
| UX-11 | P1 | Quotation builder: client picker + "New quotation for this client" from Client page (`/quotations?client=`) |
| UX-12 | done | Vendors summary: Contractors/Suppliers cards (usually 0) replaced by "With bills to pay"; three cards. "Incentive pending" needs a list field (future CDX) |
| UX-13 | P2 | Tables: unify row height, numeric font, sticky first column on wide finance tables; drawer pattern for record details |
| UX-14 | P2 | Motion: consistent 150–200 ms ease on drawers/menus/tab change (respect reduced-motion, already global) |
| UX-15 | P2 | Lead stage stepper and project lifecycle stepper share one component; mono uppercase labels → sentence case |
| PDF-10 | P1 | Payment receipt, purchase-order and client/account statement PDFs need backend endpoints (CDX-02); templates will reuse `core/pdf_brand.py` letterhead/table/signature helpers |

## 5. Codex handoff (backend contracts needed)

| ID | Pri | Endpoint / area | Reproduction | Expected / contract |
|---|---|---|---|---|
| CDX-01 | P1 | `GET /projects/{id}` → `financials` and `money.billed_unpaid` | Project with an invoice added to Collections Due and ₹X received there: `financials.collected` = 0, `money.billed_unpaid` = full invoice; `money.received` = X (correct) | Compute `financials.collected/outstanding` and `money.billed_unpaid` from the same receipts as `money.received` (invoice `paid_amount` + Collections Due receipts linked by `invoice_id`/project), or retire `financials`. Frontend already reads `money.*` |
| CDX-02 | P1 | New PDF endpoints | Not available today | `GET /accounting/collections/receipts/{receipt_id}/pdf` (payment receipt: payer, project, amount, date, Cash/Bank, reference, collection it settles); `GET /purchase-orders/{id}/pdf`; `GET /clients/{id}/statement.pdf?from&to` (invoices, receipts, balance). Same auth/tenant rules as invoice PDF. Claude will style them with `core/pdf_brand.py` |
| CDX-03 | P2 | `tests/test_quotation_types.py::test_consultancy_defaults_use_consultancy_terms_and_schedule` | Fails on `e3ce32b` (not in the CI gate): expected terms text differs from current defaults | Update the test or the defaults; it is not caused by this branch |
| CDX-04 | P3 | `GET /leads` | Card shows "Project →" via `converted_project_id` (present on converted leads) | No change needed unless the field is ever projected out |
| CDX-05 | — | Merge note | This branch edits presentation code in `server.py`, `routes/money_in.py`, `routes/finance_extras.py` | Rebase/merge order: integrate this branch after any Codex change to those PDF functions, or ping Claude to rebase |

## 6. How to re-run the inspection

```
# local QA stack: mongod 27017, API 8001 (CORS incl. 5174), vite preview on 5174 from this worktree
E2E_BASE_URL=http://127.0.0.1:5174 node e2e/tools/ux-sweep.mjs <outDir> all     # 80 screenshots + errors + overflow
E2E_BASE_URL=http://127.0.0.1:5174 node e2e/tools/pdf-samples.mjs <outDir>       # one of every PDF
```

## 7. Test evidence for this batch

- Frontend lint, JSX undefined-name scan, production build: clean.
- Backend PDF-related tests: 41 passed; 1 pre-existing failure (CDX-03) also fails on `e3ce32b`.
- Playwright desktop + mobile (phases, drawings, snags, site-visits, ux, smoke, a11y, navigation, pdf, collections, crm-chain): 82 passed, 15 intentional skips, 2 timeouts that passed on rerun (clients paging, Saturday holidays).
- `ux-sweep.mjs` after the batch: no page/console errors, no horizontal overflow at 390 px.
