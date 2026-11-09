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
| UX-16 | All forms | 13 "open form" buttons showed a **+** next to "Cancel" | Cancel shows ✕; the + only on the create action |
| UX-17 | Whole app | Owner shared five reference boards (soft/tactile "neo" UI kits) and asked for that detailing in our brown/cream tone across the ERP | **Soft tactile detailing**, CSS only, brand colours unchanged (see §3a) |
| PDF-04 | Vendor incentive statement PDF | Two-line title, period printed twice, direct incentives as "-, -, Rs. 0.00" | "Incentive statement"; period once; Date / From ("Direct incentive" or "Bill …") / Bill value columns |
| UX-19 | Whole app | Owner asked to push the reference-board look further: pill buttons, creamier wash, floating KPI tiles, raised sidebar pill, rounder inputs, PIN screen restyle | **Enhanced tactile Pass 2**, CSS only (see §3b) |
| UX-20 | Login | Original login (plain Google + password form on cream; Unsplash architecture photo background) looked amateur and the background image was rejected as "very bad" | **Login complete redesign**: two-panel CSS-only layout (cream form + brand-brown gradient marketing panel); "Architecture ERP · by Gamaa" identity; Google SSO primary + Studio ID secondary; six module feature list; Jakob Nielsen quote; no external images (see §3c) |

PDF changes are presentation-only (labels, colours, layout); no amount, query or calculation changed.
They touch shared backend files — `server.py` (invoice + quotation PDF builders), `routes/money_in.py` (`generate_reminder_pdf`), `routes/finance_extras.py` (statement) — please merge with care (CDX-05).

### 3a. Soft tactile detailing (UX-17, owner reference boards 09/11/2026)

Taken from the references: layered soft shadows instead of hard borders, a light top edge on raised surfaces, sunken inputs that glow on focus, buttons that lift on hover and press in, rounded floating menus/dialogs/toasts, a quiet background wash, and soft table-row states.
Not taken: the sage/copper palettes, neumorphic low-contrast text, and heavy embossing that hurts legibility on dense finance tables.

All of it lives in the `SOFT TACTILE DETAILING` block at the end of `src/index.css` (no component changed):

| Token / rule | Use |
|---|---|
| `--elev-1/2/3` | Warm shadows (rgba of the brand brown), resting / hover / floating |
| `--edge-light` | 1 px inner highlight on raised surfaces |
| `--sunken`, `--glow` | Inputs: pressed-in at rest, soft taupe ring on focus |
| background | Two faint radial washes over `--app` (#FAF9F6), fixed |
| `.card-flat`, table frames | Rounded, `--elev-1` + edge light |
| `.btn-primary` | #827B68 → #76705E gradient, lifts on hover, presses in on click |
| `.btn-ghost`, chips, pill tabs | Soft depth; selected rows get the accent tint and an inset bar |
| menus, dialogs, toasts | `--elev-3`, 14–16 px radius, dialog backdrop blur 3 px |

Brand tokens are unchanged. `prefers-reduced-motion` turns off the hover lift.

### 3b. Enhanced tactile Pass 2 (UX-19, owner feedback 09/11/2026)

Owner: "keep the brown shade kind of creamy background and brown buttons and all that, which is similar to the pictures which I have shared."

Changes layered on top of UX-17 (all in `src/index.css`; no component changes except `kpi-grid` class in `Dashboard.jsx` and `ClientDetail.jsx`):

| Change | Detail |
|---|---|
| Pill buttons | All `.btn-primary` and `.btn-ghost` gain `border-radius: 100px`; icon buttons become circles (`50%`) |
| Richer cream wash | Three deeper radial gradients over `--app` for a warmer parchment feel |
| Rounder cards | `.card-flat` and table frames at 18 px; inputs at 12 px |
| Sidebar active pill | `aria-current="page"` gets `--elev-1` + `--edge-light` raised shadow |
| KPI floating tiles | `.kpi-grid` hook class: `border-top/left: none; gap: 12px` on container; each child gets `border-radius: 18px; box-shadow; border` — shared-border grid becomes a row of floating cards |
| PIN screen restyle | Warmer overlay (`rgba(243,240,235,.97)`); card `border-radius: 24px` + `--elev-3`; lock icon: brown gradient + circle; keypad buttons: 14 px radius, raised at rest, press-in on active |

### 3c. Login complete redesign (UX-20, owner request 09/11/2026)

Owner: "change the whole id pass google login and add gamaa… It should be completely 100% changed… look like a professional login page of ERP system… The main software company is Gamma for the architecture." Then: "background image of loginpage is very bad."

Previous design: single-panel cream page with an Unsplash architecture exterior photo, gradient overlay, plain form. Problems: photo was low-quality, text readability poor, no brand identity.

Replacement (`Login.jsx`): pure CSS two-panel split, no external images.

| Panel | Detail |
|---|---|
| Left — cream form | Solid `--app` background; `DS` logotype tile (brown gradient + live-dot); "Design Saga / Architecture ERP · by Gamaa" header; "Studio Login" overline; "Your studio, in one place." headline; tagline; Google SSO primary button; `or Studio ID` divider; email/Employee-ID + password form with Phosphor icons; © Gamaa / Privacy / v0.2 footer |
| Right — brand brown | CSS gradient `#76705E → #5F5A4B → #2C2820`; architectural grid SVG 7% opacity; six module feature list; Jakob Nielsen design quote; `aria-hidden="true"` |

Mobile (< lg breakpoint): only the cream form panel. All `data-testid` attributes preserved. Auth logic (`handleGoogle`, `loginWithPassword`) unchanged.

**UX-18 regression found during integration and fixed (09/11).** The first version of the table-frame rule used `overflow: hidden`. 28 wrappers are both the bordered frame and the scroller (`overflow-x-auto`, `table-scroll`), e.g. Collections Due, Daybook, Invoices and the attendance sheets. On phones those tables could no longer be scrolled sideways (the ⋮ column was out of reach), and `table-scroll` lost its vertical scroll and sticky header. The 390 px overflow sweep could not see this, because hidden overflow is exactly what hides it. Fix: existing scrollers keep their own overflow, and other frames use `overflow-x: auto`, which still clips to the rounded corners. Verified at 390 px: Collections Due, Daybook and Invoices report `overflow auto`, scrollWidth ≈ 950 inside a 356 px frame, radius 14 px. Found by the mobile ⋮ tests in `collections.spec` and `ux.spec` failing with "td intercepts pointer events".

## 4. Open frontend work (next batches, in order)

| ID | Pri | Item |
|---|---|---|
| UX-10 | — | Decided: keep the Money In strip inside Accounting › Collections Due. Collections Due lives in Accounting and the strip is the only path between the four Money In screens, so it is a cross-link, not a duplicate engine |
| UX-11 | done | "New quotation" on the Client page and in the Project ⋮ menu; `/quotations?client=` / `?project=` open the form pre-filled |
| UX-12 | done | Vendors summary: Contractors/Suppliers cards (usually 0) replaced by "With bills to pay"; three cards. "Incentive pending" needs a list field (future CDX) |
| UX-13 | P2 | Tables: unify row height, numeric font (money currently JetBrains Mono with slashed zero — decide with owner before changing the established look), sticky first column on wide finance tables |
| UX-14 | done | One entrance for every custom dialog (backdrop fade 140 ms, panel lift 180 ms), button press feedback, row-hover transition; reduced-motion respected. Tab-content transitions intentionally not added (data screens should switch instantly) |
| UX-15 | done (project) | Project lifecycle is a progress line: numbered dots, ticks for finished stages, sentence-case labels, "Stage 4 of 9"; connectors on wide screens only. Leads keep their kanban (stages are columns there) |
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

Integration 09/11 (Codex `397c530` + this branch). The intermittent failures were investigated rather than accepted as rerun passes:

| Failure | Root cause | Fix |
|---|---|---|
| Lock screen mid-test (`ux.spec` employee dialogs, `smoke` primary pages) | The server keeps a session unlocked for 5 min after the last `/auth/pin/touch`; all tests share one session, and navigation-only tests send no activity | `global-setup` keeps both QA sessions active for the run (touch every 60 s, unlock on 423); `api()` also renews. Lock behaviour stays covered by backend tests |
| Saturday holidays (mobile) | Order-dependent: desktop and mobile share one tenant per run, so the second project always gets "already added" | Accept either first message; assert the count stays 24 after the repeat |
| Collections aging (mobile) | Same shared-tenant cause: bucket held both projects' ₹45,000 | Measure the bucket's change, not its absolute total |
| ⋮ in Collections Due (mobile) | Real regression, UX-18 above | CSS fixed |
| Lock screen mid-test (run #3: `site-visits.spec` live map, `ux.spec` clients paging) | Real root cause found: 26 `browser.newContext()` windows across 10 specs were never closed. After 5 min idle their `checkIdle` interval posts `POST /api/auth/pin/lock`, locking the shared admin session for all running tests. | `closeExtraContexts` added to `helpers.mjs` and called via `test.afterEach` in all 10 specs; global keep-alive (touch every 60 s) also added to `global-setup.mjs`. |
| File upload "socket hang up" (pdf, once) | The request never reached the API (no log line); Windows asyncio `ConnectionResetError` at that moment, from a keep-alive socket reused by the local vite proxy just as uvicorn closed it | Not applicable in production: nginx has no upstream keep-alive pool, so every request opens a fresh connection to the backend |

All 27 skips are deliberate viewport de-duplication (`test.skip(project !== "desktop", "... viewport independent")` and phone-only checks), each with its reason in the spec.

Batch 2 (UX-11, UX-14, UX-15, UX-16, UX-17):
- Lint, JSX scan, frontend logic tests, production build: clean.
- Playwright desktop + mobile (ux, smoke, a11y, navigation, forms, phases, proposal, crm-chain, drawings, snags, money, procurement-chain, pdf, collections): 92 passed, 23 intentional skips. 2 failures were environmental: the 5-minute idle PIN lock appeared mid-run (the failure screenshot is the lock screen) and the known Saturday-holidays mongod stall. Both, plus the 5 serial tests that did not run after the first one, passed on a rerun on their own (17/17 desktop ux, 1/1 mobile Saturdays).

Batch 3 (DS-119: Codex integration + UX-18 fix + UX-19 Enhanced Tactile Pass 2 + UX-20 Login redesign + e2e harness fix):
- Lint, JSX scan, frontend logic tests, production build: clean.
- Playwright desktop + mobile **full suite** (all spec files): **125 passed, 27 intentional skips, 0 failed**. Exit code 0. The 2 run-#3 lock-screen failures no longer appear; `closeExtraContexts` afterEach in all 10 specs eliminated the orphan-context PIN lock. The mobile `ux.spec:231` clients-paging test that previously timed out also passed this run.
