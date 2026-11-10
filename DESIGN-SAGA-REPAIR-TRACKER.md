# Design Saga Repair Tracker

Last updated: 2026-11-09 (Asia/Kolkata)

## Current Checkpoint

- Local checkout: `codex/backend-completion`; DS-120 implementation commit `c544d9e` and release checkpoint `648b01a` are published to `origin/codex/repair-release`.
- Production checkout: `/opt/design-saga-git`; runtime/source commit `648b01aac33d23279dc6447e8ee673d63b3dd7b2` is live on `srv2020574.hstgr.cloud`.
- Production working tree: protected external changes in `deploy/Caddyfile` plus `deploy/Caddyfile.pre-tanvika-20261003T154040Z`. Do not overwrite, reset, or include these changes in Design Saga deployments.
- SSH key access works. Caddy, web, backend, FerretDB and PostgreSQL are running; PostgreSQL, FerretDB, backend and web report healthy. Public `/` and `/api/` return 200; unauthenticated auth, site-visit, attendance-project, payroll-run and receivables routes return 401.
- Verified backups were created immediately before and during deployment at `/opt/design-saga-backups/20261108T082420Z` and `/opt/design-saga-backups/20261108T082550Z`. The scheduled backup and monitor timers are active; the latest monitor result is successful.
- Deployment used a SHA-256-verified Git bundle and the guarded updater. It fast-forwarded `c2f09bd` to `e3a855a`, rebuilt/recreated only backend and web, preserved the VPS-only Caddy files byte-for-byte, and produced no observed post-deploy backend 5xx/traceback signature.
- Host log retention is now verified: journald is capped at 1 GB / 7 days; new Docker containers inherit 10 MB x 3-file rotation; an exact-path logrotate rule covers the three older containers without restarting them. Existing PostgreSQL/FerretDB logs were compressed from about 1.5 GB to 115 MB archived, disk use fell from 73% to 70%, and every container stayed healthy.
- Current action: no unblocked P0/P1 engineering defect remains in the canonical backlog. Await the listed owner/accountant/provider decisions; continue P2/P3 product enhancements only after scope is chosen.

### DS-120: Accounting consistency, finance documents and interrupted-reversal recovery (09/11)

- **CDX-01 — one project collection figure**: project `money.billed_unpaid` and legacy `financials.collected/outstanding` now include receipts recorded against invoice-linked Collections Due rows. Direct invoice receipts and linked collections are combined once and capped at the invoice total; a historical paid invoice without `paid_amount` is treated as fully paid. Tenant and financial-read guards are unchanged.
- **CDX-02 — three missing branded documents**: added tenant-branded payment receipt, purchase-order and client-statement PDFs. The routes reuse the existing scoped database, permissions, organisation branding, safe filenames and PDF preview component. Received Payments, Purchase Orders and Client Detail now expose the actions in their existing menus/header instead of adding duplicate modules.
- **CDX-03 — consultancy contract test corrected**: the stale test now reflects the live letter-proposal model (`proposal.fee`); it no longer expects turnkey BOQ payment-plan/timeline fields on a consultancy proposal. Production behaviour was not changed.
- **Historical QA root cause covered**: a regression test proves that when a payroll journal was already reversed but the payroll-run update was interrupted, retrying completes the run cancellation without posting a second reversal. Read-only production investigation isolated that exact state to one Demo payroll row; it is not present in the real Design Saga tenant.
- **Demo payment metadata**: one Demo vendor settlement says bank transfer while its balanced journal explicitly uses Cash. Current validators already prevent recurrence. The safe historical repair is metadata-only (`payment_method=cash`) with an audit row; the journal amount/account must not be reposted or changed.
- **Verified before deployment**: canonical backend gate **485 passed**; focused PDF/accounting/payroll tests passed; frontend ESLint, JSX undefined-name check, 5 logic tests and production build passed; `git diff --check` and tracked/Git-history secret scan passed. No dependency was added.
- **Deployed and live verified**: guarded fast-forward to `648b01a`; backend and web are healthy at that immutable revision. Pre-/during-/post-repair backups: `/opt/design-saga-backups/20261109T173244Z`, `20261109T173351Z`, and `20261109T173838Z`. The two protected Caddy hashes are unchanged; Postgres, FerretDB and Tanvika were not rebuilt or restarted.
- **Historical Demo repair completed**: payroll run `pr_2ccbff137a52` now references its existing single balanced reversal and is `reversed`; settlement `vcpay_45ca202c39a1` now says `cash`, matching its unchanged ₹1,000 Cash journal. Both actions are audited; no financial amount or journal line was rewritten.
- **Production acceptance**: all five integrity counters are zero and audit-chain verification passes for all eight tenants. All three PDFs rendered from actual production records; their OpenAPI paths are present. Public app/API and Tanvika return 200, unauthenticated auth/new-PDF routes return 401, security headers remain present, and backend/web logs contain no observed 5xx/traceback after deployment.

### DS-119: UX integration — enhanced tactile, login redesign, e2e harness root-cause fix (09/11)

- **Integration**: merged Codex security hardening `397c530` with Claude UX `d16579b` into `b2d6a99`; all conflicts resolved.
- **UX-18 (table overflow regression) fixed**: The soft-tactile table-frame CSS rule used `overflow: hidden`, which prevented horizontal scroll on 28 wrapper elements that are both the border frame and the scroll container (Collections Due, Daybook, Invoices, attendance sheets). Fixed with selective `overflow-x: auto` on non-scroll frames; existing `overflow-x-auto` / `table-scroll` classes keep their own overflow untouched. Verified at 390 px: Collections Due `scrollWidth ≈ 950` inside a `356 px` frame, `border-radius 14 px`, scroll works.
- **Enhanced tactile Pass 2** (`src/index.css`): full pill on all action buttons (`border-radius: 100px`); richer cream background (deeper layered radial gradients); cards at 18 px radius with `--elev-1` + edge-light; table frame radii matched to cards; inputs at 12 px radius; sidebar active item gets `--elev-1` raised-pill shadow; KPI grids converted from shared-border to floating tiles via `.kpi-grid` hook class (gap 12 px, each child gets its own border + radius + shadow); PIN lock screen restyle (warmer overlay, rounded card, brown icon gradient, raised keypad buttons with press-in feedback). `Dashboard.jsx` and `ClientDetail.jsx` both updated with `kpi-grid` class.
- **Login page complete redesign** (`Login.jsx`): scrapped the original form. Two-panel CSS-only layout: left = cream form panel (`--app` solid background; brand `DS` logotype in gradient tile; `Design Saga / Architecture ERP · by Gamaa` identity; Google SSO primary + Studio ID secondary form; © Gamaa footer); right = brand-brown gradient panel (`#76705E → #5F5A4B → #2C2820`; architectural grid SVG at 7% opacity; feature list of all 6 modules; Jakob Nielsen design quote). Mobile shows form-only panel. No external images. `data-testid` attributes preserved.
- **E2e harness root-cause fix**: 26 `browser.newContext()` windows across 10 specs were never closed. After 5 min their `checkIdle` posted `POST /api/auth/pin/lock`, intermittently locking the shared session for all running tests. Fix: `closeExtraContexts` exported from `helpers.mjs`, called via `test.afterEach` in all 10 spec files; global-setup keep-alive touches the session every 60 s and unlocks on 423.
- **Verified**: lint/JSX/logic tests/production build: clean. E2E desktop + mobile full suite (all spec files): **125 passed, 27 intentional skips, 0 failed** (baseline was 123; 2 additional cases now pass with the orphan-context fix). Exit code 0.

### DS-118: Acceptance pass 09/11 - one "still to collect" figure, large-tenant fixes, UX polish

- BR-010 root cause: main and Accounting dashboards computed money due from invoices/milestones only (stale after invoices moved to Collections Due); now both use `collections_summary()` (same rows as Collections Due) and flag sent invoices not yet in Collections Due; dashboard month capped at month end. E2E `consistency.spec` proves dashboards = Collections Due, month P&L = dashboard = Daybook, All-time P&L = Daybook, every entry balances, trial balance balances, bank ledger = dashboard balance.
- BR-012: invoice, quotation and uploaded-file previews verified under production CSP (pdf.spec, new case); staff cannot open other projects' files.
- Chains: new `procurement-chain.spec` (PO → GRN → bill → payment once, chosen bank, vendor/project/ledger views; Record vendor bill from PO). Other chains covered by crm-chain, collections, money, snags, site-visits, period-close specs.
- DB-01/DS-008: `scripts/perf_large_tenant.py` on a disposable DB (30k journals, 3k invoices, 2.5k collections, 40k audit rows): all heavy reads 0.03-1.9 s locally (MongoDB; FerretDB in production is slower - re-measure there before onboarding very large studios). Found and fixed: account ledger refused >10,000 lines (413) - now exact totals with the newest 5,000 lines shown and a note.
- UX: plain-language Accounting header/KPIs with hints and click-through; GRN journal narration uses GRN/PO numbers; source labels for GRN/reversals; invoice filters by money actually received (incl. Collections Due) and "in full" marker; project cards without duplicate type label and "Fee not set"; calendar day numbers top-aligned; search-icon overlap fixed (tasks, payroll, ledgers, daybook, audit); payroll month picker no longer truncated; phone header search no longer wraps; dashboard alerts in Indian grouping, clickable, plain labels; empty pipeline stages without stub; bill form fields labelled; VEN-02 Record vendor bill from PO (row menu + panel, received POs only); UX-06 "My day" (own tasks, check-in, free leave via `/dashboard/my-day`) and sales/team widgets only for roles that use them.
- Assessed, not adopted: ClamAV (VPS 3.9 GB RAM shared with Tanvika; signatures need ~1-1.5 GB) - uploads keep type/size/magic checks, nosniff, private serving; export streaming not needed (1 FY of 30k entries in <2 s).
- Verified: 479 backend tests; lint/JSX/logic tests/build; E2E desktop+mobile ux/smoke/a11y/navigation 43 passed (9 intentional skips), procurement 2/2, consistency 1/1, pdf 3/3.

### DS-117: Full request audit 09/11 (every owner message since 05/11) + last gaps

- Re-read all 100+ owner messages across the six session transcripts and the long prompts (handoff, investigation, final audit, calendar/workboard, invoice/reminder/collections, collection-due reminders, reorganisation) and checked each against code, tests and read-only production queries.
- Confirmed on production: HDFC opening balance ₹10,336 posted (07/10/2026); Hiren Panchal terminated (hidden from sheets); DESIGN SAGA logo set; signature/period-close/drawings/snags routes live; containers healthy; Let's Encrypt certificate valid to 29/12/2026; SSH key-only (`passwordauthentication no`, root `prohibit-password`); ufw (22/80/443) and fail2ban active; nightly + pre-deploy backups with SHA256SUMS; health monitor timer running; Tanvika services untouched.
- Fixed now: (1) owner's "no commission anywhere" rule also applied to the chart of accounts - idempotent startup migration `core/terminology_migration.py` renames "Vendor Commission Income" → "Vendor Incentive Income" and "Commission Advances" → "Vendor Incentive Advances" in every company (labels only; journal line display names relabelled; amounts untouched; a name clash becomes "… (old)"; audit row per rename). (2) Team leave list dropped the leftover leave-type column and the policy text no longer mentions casual/sick/earned (owner removed leave types).
- Still owner-side (cannot be done from code): VPS restart for kernel 7.0.0-42 (`/var/run/reboot-required`; also restarts Tanvika), mark 1st/4th Saturdays (one-click button), draw the signature, rotate the Atlas credential, choose off-server backup + alert destinations, GST split / TDS / retention policy, employee client/lead visibility, demo company INV-1001/1002/1004 restatement (demo only).
- Verified: 478 backend tests (new `test_terminology_migration.py`), lint/JSX/build, E2E phase2/money/collections 24/24.

### DS-116: Site snags with photo evidence and verified closure (PRJ-02)

- Project › **Snags**: raise (title, area, priority, fix-by date, team member and/or vendor responsible, photo taken on the phone camera and shrunk on the device) → assignee or manager **Mark fixed** with a required photo of the fix → manager **Verify & close**, or **Reopen** / **Won't fix** with a reason. Numbering SN-001 per project; filters Open & to verify / Assigned to me / To verify / Closed / All; photos and full history in one dialog.
- Rules (server): raising needs `tasks.create|tasks.update|projects.update` and project visibility; only the assignee or a manager can mark fixed; only `projects.update` can close/reopen/won't-fix; closing requires a fixed snag; assignee/vendor must belong to the tenant; delete only for an open snag with no fix photo or reopen history (removes its photos), otherwise Won't fix; compare-and-set on status; audit rows for every step. Photos use the shared upload service (same type/size checks, storage and backups as site-visit photos) and are served only to users who can see the project.
- Verified: 477 backend tests (new `test_snags.py`); E2E `snags.spec.mjs` (raise with photo → staff cannot verify or read photos → close refused before fix → fixed with photo → verify & close → reopen with reason → history and both photos) passed; drawings/site-visits rerun green.

### DS-115: One project per job across lead → quotation → project (CRM-01)

- Audit found the chain created duplicates: converting a lead creates the client and a project; converting the accepted quotation for that client always created a **second** project.
- `POST /quotations-adv/{id}/convert-to-project` now accepts `{project_id}` to link the accepted quotation to an existing project of the same client (needs `projects.update` on that project instead of `projects.create`): sets `from_quotation_id`, keeps an already-agreed project value (fills it from the quotation only when empty), adds the quotation's phase/BOQ tasks. Refuses a project already linked to a quotation (409), an archived project (409) or another client's project (400). Rollback removes only the tasks this conversion created and unlinks the project; audit row `quotation.convert`.
- Quotation screen: Convert offers the client's existing unlinked projects first ("Link to <project>"), with "Create a new project" still available.
- Verified: 476 backend tests; new E2E `crm-chain.spec.mjs` (lead → convert → second convert 409 → quotation approved → UI link → still one project, quotation converted to it → relink 409 → second quotation: same project 409, other client's project 400, new project OK); proposal/pdf specs 4/4.

### DS-114: Drawing register on every project (DOC-01)

- Project › **Drawings**: numbered drawings (unique per project, e.g. A-101) with discipline and scale; **Issue rev A/B/C…** uploads the PDF through the existing project Files upload (one file engine, same storage/backup/permissions) or picks an existing project file; purpose For review / approval / construction (GFC) / as built / information; issued to; what changed.
- New revision supersedes the previous one (a rejected revision keeps "Changes asked"); only the current revision can be Approved / sent back (reason required) / commented, by users with `projects.update`; issuing needs `files.create`; reading needs `files.read` + project visibility. Number is fixed once issued; issued drawings are archived, never deleted; never-issued drawings can be deleted. Compare-and-set on `rev_count` stops two people issuing the same letter; unique index `(org_id, project_id, number)`. Audit rows for create/update/archive/issue/decision.
- Register counts (approved / awaiting decision / issued for construction), discipline filter, revision history, Excel export (register + full revision history).
- Also in this batch: vendor incentive journal fallback now uses the rename-tolerant account lookup (it looked up the old "Vendor Commission Income" name, which fails for tenants that renamed the account, e.g. DESIGN SAGA); remaining visible "commission" wording in two errors and the Collections Due subtitle changed to incentive.
- Verified locally: 476 backend tests (new `test_drawings.py`: letters A…Z→AA, number validation, duplicate 409, foreign-project file refused, rejection needs reason, supersession, only-current decisions, number lock, archive-not-delete, Excel). E2E `drawings.spec.mjs` (add → issue A for approval → ask for changes → issue B for construction → staff 403 → approve → counts → history → Excel) passed; collections/money/smoke/site-visits rerun 12/12 + 20/20. Production timing check: 231 requests in 24 h, none over 1 s (the two local E2E timeouts were 10-second stalls of the workstation's test database, not the code).

### DS-113: No silent caps on money lists; overdue-age strip; PO quick actions; Vendor 360 groups

- INV-06: `received_payments` read every row (money total; was `to_list(5000)`); Payment Reminders and a project's site-visit history use the shared `MAX_LIST_ROWS` instead of 2,000 / 200.
- INV-07: Collections Due shows **money due by age** (Not yet due · 1-30 · 31-60 · 61-90 · Over 90 · No due date) for the selected category; clicking a bucket filters the queue, clicking again clears it.
- INV-08: Purchase-order rows get ⋮ Open · Mark as sent · Cancel PO (same server actions as the panel; the server still refuses a cancel after goods are received). Decided not to add ⋮ to Expense claims and Loans: the whole row opens the panel that already holds the role- and state-dependent actions (approve/reject/reimburse/EMI), and a menu with only "Open" would repeat it.
- Vendor 360: up to nine flat tabs grouped as **Overview** (Details, Performance) · **Money** (Ledger, Bills, Payments, Vendor incentives, Incentive terms) · **Projects** · **Documents**; tab ids, permissions and consultancy/turnkey filtering unchanged.
- INV-09 measured instead of refactored: every page is already a lazy route chunk (Accounting 45 KB gzip); the shared start-up bundle is 174 KB gzip. Splitting the 2,168-line Accounting file would not speed up first load; revisit only with a bundle analyser.

### DS-112: Collection receipts correctable from where they are seen; reminders come back on reversal

- INV-01..04 above. Collections Due rows have an always-on ⋮ with **Receipts & entries** (new read-only `GET /accounting/collections/{type}/{id}/entries`, finance.read; lists receipts for manual/invoice-linked collections, vendor incentives — the applied share of each settlement — milestones and legacy invoices, each with its journal). Each opens the standard entry panel, whose **Delete** now covers `other_receivable_income` and reverses through the existing source-aware path. Received Payments rows get **Open entry** / **Open source**.
- Reversing a collection receipt or a vendor incentive receipt now refreshes that collection's reminder: Payment Reminder back to open, calendar/Google event and alerts recreated.
- Verified locally: 473 backend tests (vendor receipt delete asserts the reminder refresh). E2E: collections suite 12/12 incl. two new cases (UI: receipt → Receipts & entries → Open entry → Delete → row due again, reminder open, calendar event back, removed pair out of books, staff 403, Received Payments ⋮ opens the entry; API: vendor incentive receipt delete → due again, reminder open, receipt shown Reversed).

### DS-111: Close & export a financial period (Excel books + lock), owner request 08/11

- Owner asked for quarterly/yearly Excel exports and closing of older years. Built as one workflow in Accounting › Setup › **Close & export**: choose FY + full year or Q1-Q4 → **Check** → **Download Excel** → **Close** (Admin) → **Reopen** (Admin, written reason).
- Lock: one date per tenant (`organizations.books_locked_through`), enforced in `_post_journal` (the single journal writer for every module) and wherever an entry is taken out of the books (Delete/Correct `hide_from_books`, `_hide_reversed_pair`, cash-basis restatement, paid-salary edit). Salary edit and restatement check up front so nothing is half-written. A reversal dated today stays allowed, so closed books are corrected without being rewritten. Closed years stay fully visible in every report/ledger/search.
- Check (read-only): unbalanced entries in the period, the DS-072 source-integrity report scoped to records dated up to the closing day (new `as_of`), half-saved salary payments; warnings for unpaid approved claims and open collections. Close refuses without an export of that exact period made in the last 7 days, refuses gaps after the previous closing, and uses a compare-and-set update so two admins cannot race.
- Export: dependency-free `.xlsx` writer (`core/xlsx.py`; text is never written as a formula). Sheets: Manifest (company, period, generated by/at, counts, debit/credit totals, net profit, SHA-256 per sheet), Daybook (incl. reversed/removed with status), Journal lines, Trial balance (opening/period/closing), P&L, Chart of accounts, Invoices, Receipts, Collections due, Vendor bills, Vendor payments, Payroll, Expenses, Attachments index, Audit log. File SHA-256 stored in `period_exports`; history in `period_closes`; audit rows `accounting.period.export/close/reopen`.
- Nothing is deleted. Purging old data stays out of scope until the owner/CA confirms retention (CGST s.36, Companies Act s.128) — see ACC-10.
- Deployed `6ccdd8f` on 08/11 14:53 IST (pre-deploy backup `/opt/design-saga-backups/20261108T092217Z`); containers healthy, no backend errors, new routes 401 anonymously, Caddy files untouched. Live authenticated walkthrough pending an owner session.
- Verified locally: 473 backend tests (new `test_period_close.py`: xlsx validity/no formulas/escaping, lock boundaries, lock at the writer, removal refused, today-dated reversal allowed, trial balance and P&L figures; new payroll case: closed-books salary edit refused before any write). Lint/JSX/build clean. E2E `period-close.spec.mjs` (staff 403, no-export 409, UI check → real .xlsx download → close → back-dated post and in-place correction 409 → reversal OK → reopen with reason, history) passed; full desktop suite 59 passed, 2 timeouts that passed on rerun (6/6).

### DS-110: Attendance/site operations, connected expenses/payroll and release-gate repair

- Added attendance-linked site visits, project/site selection, check-in map, live admin map, visit photos/reports and tenant/role/location privacy controls. The attendance-only project policy still lets Site Execution/Site Supervisor staff inspect every active tenant project without broadening ordinary project visibility.
- Consolidated salary payment UI into the authoritative payroll workflow; employee history and accounting share the same run/journal. Expense claims gained receipt correction/storage and linked financial controls.
- Unified Collection Due reminders across calendar, notifications and Google queue without posting a journal at reminder creation. Receipt posting remains idempotent and is the only money event.
- Fixed shared row actions so a divider before `Cancel/Delete` no longer hides the action, fixed direct site-photo selection, removed a duplicate empty-state invoice CTA, and repaired Calendar filter contrast.
- Verification on a disposable local database: 469 canonical backend security/integrity tests passed; frontend lint, production build, JSX import check and 5 logic tests passed. The four new E2E suites passed on desktop (23), mobile (21 with 2 intentional skips) and laptop (10 with 13 intentional skips). A wider 117-case regression produced 61 passes, 51 expected cross-project skips and five failures; all five root causes were corrected and reran successfully (4 desktop + 1 mobile).
- Dependency audits remain enforced in GitHub CI. Secure production-only audits were rerun in ephemeral containers after deployment: `npm audit --omit=dev --audit-level=high` found 0 vulnerabilities and `pip-audit -r requirements.production.txt` found no known vulnerabilities. The complete development/build npm tree still reports three advisories (1 moderate, 2 high), tracked with the legacy CRA/toolchain modernization work; they are not shipped in the production runtime image.
- Database effect before deployment: none. Tests used only disposable local QA data.
- Production evidence: release `e3a855a` is live; all five containers are running and the four application/data containers report healthy; public security headers remain present; protected repaired routes reject anonymous requests; Caddy configuration hash and protected working-tree files are unchanged.
- Live accounting evidence: the read-only source-integrity report was executed independently for `org_default` and `org_759bcccd654c` (both Design Saga organisation records). Both returned zero unbalanced journals, orphaned source journals, broken reversal links, paid sources without an active journal, and payment-method/account mismatches.

### DS-109: Security review + pentest, signature on PDFs, cash-basis restatement, Phase 1 leftovers

- Security review / penetration test (local active, production read-only): see `docs/SECURITY_REVIEW_2026-11-08.md`.
  Fixed: login CSRF (cookie-less foreign-origin writes), cross-company reads answering empty 200 (now 404),
  fpdf2 CVEs (2.8.8), dotfile/backup paths 404 in nginx. 32 cross-company attacks, 382-route staff matrix and
  injection probes found no data exposure.
- Signature on PDFs: draw with Apple Pencil (pointer pressure) or upload PNG/JPEG/WebP; white paper removed,
  stored privately (`org-signatures`, admin-only preview), printed above "Authorised Signatory" on invoices,
  payment reminders and salary slips (slip gained a signatory block).
- `POST /accounting/invoices/{id}/restate-cash-basis` (admin, audited, once): accrual-era invoice -> cash basis
  (issue entry reversed+hidden; receipts re-booked as income on their dates).
- Holidays: "Add Saturdays" (e.g. 1st and 4th of every month), skips existing dates.
- Phase 1: Leads empty columns, Vendors "Not rated" + no duplicate Open, Employees no empty line,
  Projects no "#001" / "No client", sidebar "Expense claims".

### DS-108: Invoices, payment reminders, collections and accounting kept apart (₹6 lakh fix)

- Root cause: issuing an invoice booked its full value as income (Dr Receivable / Cr Income). sample(Demo) INV-1004 for ₹6,00,000 with ₹51,000 received showed ₹6,00,000 Consultancy Income. Also: PATCH milestone status "paid" auto-posted a full receipt (no date/account; duplicate on part-paid milestones).
- Company setting `accounting_basis` (default **cash**): sending/issuing an invoice posts nothing; Record Payment books only the amount received (Dr Cash/Bank, Cr Income, with output GST split in the invoice's proportion). `accrual` keeps the previous behaviour; invoices already recognised under accrual keep settling their receivable.
- A "paid" label is never a payment: invoice (already) and milestone status changes to paid are refused (409) — Record Payment only, idempotent.
- Invoices can bill a project milestone (`milestone_id`): one live invoice per milestone, Collections Due lists it once (as the invoice), paying the invoice updates the milestone; paying the milestone directly is refused.
- Percentage milestones follow the project value until billed or received. Project detail shows Project value / Scheduled / Invoiced / Received / Still to receive.
- New `routes/money_in.py`: numbered Payment Reminders (PR-0001) with branded PDF and WhatsApp link (wa.me, India code added), no journal; Received Payments register (cash/bank receipts only).
- UI: Invoices | Payment Reminders | Collections Due | Received Payments tabs; invoice Received / Still due columns, filters, "Send payment reminder"; Remind button in Collections Due; accounting-basis choice in Company Settings; fixed or % milestones.
- Historical data untouched: sample(Demo) INV-1004 still carries its accrual entry; correct only with owner approval.
- Tests: `tests/test_money_in.py`, e2e `collections.spec.mjs` (₹6L + ₹10k, GST split, duplicate key, reminder PDF/WhatsApp/no journal, staff 403, % milestone, invoice-milestone single count, screens).

### DS-107: Edit a paid salary; cancelled salaries leave the books; opening balance for accounts with activity

- Owner report: reversing a salary left "minus" reversal lines in the Daybook and employee sheet; a wrong salary amount could not simply be edited. Janvi's October run still said "paid" although its journal had been reversed from the Daybook (books and payroll out of step).
- `POST /payroll/runs/{id}/correct`: replace a paid (or previously cancelled) salary with the right amount/bonus/date/account. Old journal is reversed on its own date with both entries hidden from books (kept for audit); slip breakdown is rebuilt so earnings − deductions = paid amount (bonus shown as Bonus).
- Cancelling a salary now hides the pair too (reversal dated with the payment, so no balance moves on any date). Reversing a payroll journal from the Daybook is refused with a pointer to the Payroll tab.
- Employee sheet: payment history shows live payments only (toggle for cancelled), ⋮ menu with Slip / Edit payment / Cancel payment / Pay again.
- `POST /accounting/accounts/{id}/opening-adjustment` + "Add opening balance" in the Chart of Accounts ⋮ menu: posts account vs "Opening Balance Adjustment" dated the day before the account's first entry (the opening field itself stays frozen once there is activity). Reversible from the ledger.
- UI: expense claim form (headings, proper category names, empty amount, phone layout); salary Pay row no longer asks "Cash" twice; monthly attendance sheet drops "— ·", holiday letter H, half-day ½, legend letters, upcoming days blank.
- Tests: `tests/test_payroll_correction.py`, `tests/test_opening_adjustment.py`, e2e "a paid salary is edited in place".

### DS-106: Senior review + Phase 1 batch 1 — logos 404 on gamaa.in, blue PDFs, dialogs under the header, white sidebar

- Review method: walked all 19 screens as admin on the local QA copy (screenshots), logged failing API calls per page, traced settings to where they apply. Plan written to `docs/PRODUCT_UX_RESEARCH/07_PHASED_PLAN.md` (Phase 1 clean-up, Phase 2 reorganise, Phase 3 architect features, owner actions).
- **Logos never loaded on gamaa.in** (owner screenshot: broken image in Company Settings, blank sidebar tile). Root cause: in `deploy/nginx.conf` the static-asset regex `location ~* \.(png|jpg|...)$` beat the `/api/` prefix, so every API path ending in .png/.jpg (logos, any image download) got nginx's 404 page; the backend itself served the file (200). Fix: `location ^~ /api/`. Safety net: sidebar and settings fall back to initials if an image fails.
- **PDFs printed in blue**: all live companies still carried the old default `#002FA7` (Klein blue) that nobody chose, so invoices/quotations/proposals/payslips used it. `core.pdf_brand.brand_primary_hex` treats that default (or empty) as "not set" and prints the brand taupe #76705E; a colour a studio really picks is kept. New companies default to taupe. Company Settings now shows "PDF colour" (what it really controls) with a reset; the unused Accent colour and the misleading "Button" preview were removed. Tests: `test_pdf_brand_colour.py`.
- **Dialogs trapped under the header**: entry animations used fill-mode `both`, leaving a permanent transform/opacity layer on the page wrapper, so fixed dialogs (28 of them) were stacked below the sticky top bar; on short pages the PDF preview's Close button was hidden. Animations now use `backwards`; the PDF preview renders on <body>.
- Sidebar (owner request): plain white, warm-tint active row with taupe bar; group headings (Sales, Projects, ...) in Playfair Display 15px instead of tiny capitals.
- Same page header (`PageHero`) on Vendors, Invoices, Holidays, Audit log and Quotations; removed the slogans "Every hand that builds…", "Send. Track. Collect.".
- Quotation builder: removed the three "AI: missing items / optimise cost / premium upgrades" buttons and their side panel (owner request).
- Dashboard: removed the scrolling module-name strip (it also made phones scroll sideways); empty lead funnel shows one line instead of six empty bars; KPI cards no longer print the same amount twice.
- Attendance: an admin login with no employee profile no longer fires 4 failing requests on every visit, is sent to the Team Dashboard, and does not see empty "My" tabs; personal data reloads per month, not on every tab click; tabs wrap instead of running off screen.
- Accounting dashboard: "Upcoming payments" renamed "Due to collect · next 30 days" and shows project + amount still due; transaction source shown in words ("Salary", "Collection received") instead of codes; negatives shown as "−₹5,000".
- Verified: backend gate 390 passed; ESLint + JSX check clean; build OK; e2e full run 64/65 (the one failure, phone sideways scroll, was the removed strip; passes now) plus desktop smoke/money/proposal/PDF 11 passed after the last changes.

### DS-105: ⋮ menus on every remaining table row; hidden crash in Collections fixed

- Owner screenshot: rows still had inline "Edit | Delete" buttons. Searched every page and component for inline row actions and moved them all into the shared ⋮ RowActions menu: vendor bills, vendor payments (Reverse), expected commissions, commission receipts; Accounting collections (expected) and Chart of Accounts (Edit / Deactivate-Restore); employee documents, warnings, rewards; recurring rules (Post now / Pause / Edit / Delete); bank-import batches (Download CSV / Delete); project files; work board cards and list rows; master-data values (Rename / Hide / Delete). Up/down ordering arrows and visible "Open" links stay as they are. All test ids kept on the menu items.
- Bug found while doing this: Accounting > Collections Due rendered `<Trash>` without importing it, so any manual expected collection with nothing received yet would crash that screen. Fixed (import) and covered by an e2e test that also listens for page errors.
- Guard: ESLint here has no React plugin, so undefined JSX tags slip through. New `frontend/scripts/check-jsx-undef.mjs` fails CI when a JSX component is used but never imported/declared (clean now; it flags the old Accounting file). Added to the quality workflow.
- Verified: ESLint clean, JSX check clean, build OK; e2e ux/money/smoke/a11y/phases 39 passed incl. new test (collection row has no inline buttons, ⋮ shows "Cancel this collection", no page errors; employee warning edit through ⋮).

### DS-104: Clickable breadcrumbs; pinned headers on long tables

- U8: top-bar breadcrumb was plain text. Company name now links to the Dashboard; on a detail page (e.g. one project) the list name links back to the list and the last crumb reads "Details". On the list itself it stays a plain label.
- U3: Daybook and the Attendance monthly sheet (grid and summary) scroll inside their own box on tablet/desktop (max 72% of screen height) with the column headings pinned; the frozen Employee column corner stays above both. Phones keep normal page scrolling.
- Verified: ESLint clean, build OK; e2e ux/smoke/a11y 28 passed incl. new test (breadcrumb back-links, Daybook header computed position sticky).

### DS-103: Loading shimmer and helpful empty states on list pages

- Invoices, Vendors and Quotations had no loading state, so they briefly said "No ... yet" while data was still arriving; Clients showed a plain "Loading..." line; empty messages were bare text with no next step.
- New `components/TableState.jsx`: `SkeletonRows` (shimmer rows using the existing `.skeleton` style, screen-reader "Loading...") and `EmptyRow` (icon, title, one-line hint, primary action button).
- Applied to Invoices, Quotations, Vendors, Clients, Employees and Expense claims: shimmer while loading; "No X yet" with a create button (only for users allowed to create) when truly empty; "No X match - try a different search" when a search/filter hides everything. A failed load ends the shimmer instead of spinning forever.
- Verified: ESLint clean, build OK; e2e ux/smoke/a11y/forms pass (two forms tests timed out under load and passed when rerun alone); new test covers the no-match state and the empty state's create button.

### DS-102: Geofence map showed "API KEY REQUIRED" and a broken pin on gamaa.in

- Owner screenshot: CARTO Voyager tiles (DS-099) work on localhost but CARTO now refuses unregistered domains, so production showed "API KEY REQUIRED" watermarks. The default Leaflet marker PNG is not bundled by Vite, so the pin showed as a broken image.
- Fix: street layer switched to OpenStreetMap standard tiles (keyless, colour, attribution linked, origin-only referrer); Esri satellite kept (keyless). Pin is now a drawn green SVG (divIcon), no image files.
- Verified: both tile servers return real tiles with a gamaa.in Referer; new e2e test checks OSM tiles load, the drawn pin shows, no broken marker image and no CARTO requests.

### DS-101: Accounting sections grouped by task

- The 14 Accounting sections were one flat grid of equal buttons. Now grouped under plain headings: Overview (Dashboard, Health check), Money in (Income, Collections Due, Commissions), Money out (Expense, Recurring), Books (Daybook, Ledgers, Bank Reconciliation), Reports (P&L · Trial Balance, Balance Sheet, Cash Flow), Setup (Chart of Accounts). Mobile select uses the same groups (optgroups).
- Labels: "Reports" renamed to "P&L · Trial Balance" (what the tab shows); "Validation" renamed to "Health check". Section ids and test ids unchanged, so links and tests keep working.
- Verified: ESLint clean, build OK; e2e ux/money/smoke/a11y 29 passed incl. new grouping test.

### DS-100: No more silent row limits; paging on long lists; calendar link checks

- R1: backend reads stopped at fixed row counts (500 to 20,000) in ~90 places. In money code this meant wrong totals once a company grew: P&L, ledgers, receivables, finance dashboard, vendor ledgers/commissions, payroll and advance recovery. In `core/access_control.visible_project_ids` it meant users would lose access to projects past the cap.
- Fix: accounting, vendors, finance extras, payroll, advances, loans (EMI), attendance salary summaries and access control now read every row (`to_list(None)`). Plain display lists use one shared limit `core/limits.MAX_LIST_ROWS = 20000`. Naturally small sets (phases, office locations, master data) and explicit `.limit(n)` reads are unchanged.
- Guard: `tests/test_row_limits.py` fails if a capped read returns to the money/access modules or server lists; added to the CI gate.
- U2: shared `components/Pager.jsx` (`usePaged`): 50 rows per page with "Showing 1-50 of N" and Prev/Next on Invoices, Clients, Vendors, Employees; resets to page 1 when search/filter changes; hidden for short lists. Daybook already pages from the server.
- R4: calendar events now refuse a `client_id` / `vendor_id` that does not exist in the company (404), on create and edit.
- Verified: backend gate 386 + 2 new passed; ESLint clean; build OK; e2e ux/forms/a11y/money 28 passed (one mobile client-picker test timed out under load and passed when rerun alone).

### DS-099: Master improvement list; colourful map; in-app forms; more ⋮ menus

- Owner asked for a list of bugs, risks, UI changes and module features, then fixes module by module. Written to `docs/PRODUCT_UX_RESEARCH/06_MASTER_IMPROVEMENT_LIST.md` (risks R1-R10, whole-app U1-U10, per-module ideas, order of work).
- Attendance geofence map: was greyscale. Now colourful street map (CARTO Voyager) with a Satellite layer switch (Esri), attribution shown; office fence green, saved locations dashed blue; help text updated.
- R5: all 17 browser `prompt()` popups replaced by an in-app form dialog (`askForm` in `lib/confirm.jsx`) with labelled fields, required-field check and defaults: employee warnings/rewards/documents, quotation new version and list editing, vendor document edit.
- U1: ⋮ action menus on Leads (Convert stays visible), Employees, Holidays and Projects. Project menu: Open, Pin to top (remembered on this device), Edit details (opens the edit form), Archive (confirm). Works in grid and list views.
- Verified: ESLint clean, build OK; e2e ux/forms/a11y 22 passed incl. new test (pin moves the card first, archive removes it, warning dialog refuses an empty reason then saves).

### DS-098: One paid leave per month for every employee; taupe sidebar; logo tile

- Owner: "1 leave in one month to all the employees". Verified the payroll engine already applies a company-wide monthly paid-leave allowance (default 1; first approved casual/sick/earned leave in a month is paid, further ordinary leave is unpaid at the per-day rate; "unpaid" always deducted; maternity/paternity/comp-off not counted). Live DESIGN SAGA policy has no stored value, so the default 1 already applies (read-only check 06/11).
- Gaps fixed: the setting was buried under Attendance > "Geo & Policy" between GPS fields. Tab renamed "Office & Leave Policy"; a "Leave policy" section now sits at the top ("Every employee gets [1] paid leave per month", rules, worked example for a Rs. 24,000 salary) with its own Save. Hardened: a stored null/empty allowance now means the default 1 (engine and policy merge) instead of 0; the save sends a clamped 0-31 integer.
- Sidebar (owner: "sidebar colour same as button", "remove collapse of dropdown"): background = primary button taupe #76705E with tokens re-scoped (white text 5.1:1; active/hover use a deeper taupe overlay so white text stays above 4.5:1); group headings are plain labels (no collapsible dropdowns); icon-rail Collapse kept. Logo and initials sit on an off-white tile so the black mark reads on taupe.
- Verified: `tests/test_monthly_leave_allowance.py` (6) incl. 1st leave free, 2nd leave Rs. 1,000 deducted at 26,000/26, stored null = 1; backend gate 386 passed; axe colour-contrast clean.

### DS-097: Calendar Studio/Project scopes, Work board views, Google context, three-dot menus

- Calendar: one feed, two scopes. Every feed item now carries `project_id`, `scope` (project if linked to a project, else studio) and `project_name`; the page has All / Studio / Projects tabs with counts and a project filter. The event form gained the missing Project field (empty = studio event). Server now refuses linking an event to a project the user cannot see (404) — before, any project id was accepted.
- Google Calendar (existing engine, no second system): project items sync as "[Project] title" with project link in the description; studio events as "Studio: title"; `designSagaScope` extended property; deterministic event ids unchanged (no duplicates), updates/deletes unchanged.
- Work board: Board / List / Calendar segmented views over the same task records; board Group by status or category (drag between category lanes sets the category); "+" quick add in every lane (respects the project filter); member filter; Calendar view = month grid by due date, drag a task onto a day to set its due date, Unscheduled panel. Toolbar wraps on phones (was overflowing).
- Three-dot menu: reusable `components/RowActions.jsx` (Radix dropdown, keyboard accessible, hides unauthorised/unsupported actions, financial actions keep reversal semantics). Applied to Invoices (Preview and Record payment stay visible; PDF, Edit, Undo latest payment, Delete in menu), Quotations, Clients, Vendors.
- Verified: backend gate 377 + `tests/test_calendar_scope.py` (3); e2e ux suite incl. calendar scope + project guard, board quick add/group/list/calendar, quotation delete via menu.

### DS-096: Sidebar redesign (same brand colours)

- Owner: "sidebar is not looking good". Colours unchanged (cream #F5F4F0, taupe #8B7F6A, warm grey #EDECE8).
- Structure: full-height sidebar where only the menu scrolls; brand and profile stay pinned. Active page = soft taupe tint, taupe icon and an inside marker bar (was a white pill with the bar outside on the edge). Group headings are clear uppercase labels that collapse/expand (remembered; the group holding the current page always opens). Footer is one compact row: avatar, name, role, App PIN settings and Sign out icons. New desktop "Collapse" control shrinks the sidebar to a 76px icon rail with tooltips (remembered), like the owner's Tanvika ERP.
- Verified: navigation/a11y/ux/smoke 30 passed; new `ux.spec.mjs` sidebar test (group collapse + rail, both persist across reload).

### DS-095: Original Design Saga palette restored (owner correction)

- Owner rejected the DS-094 colour change (espresso/walnut/caramel): "never told you to do this". The original palette from the pre-redesign CSS is restored exactly and documented as fixed: taupe #8B7F6A (buttons #76705E, hover #5F5A4B), sidebar cream #F5F4F0, background #FAF9F6, logo brown-gold #8B7A55, warm grey #EDECE8, charcoal #2C2C2C, Playfair Display headings (now with lining tabular figures for money), Inter text. Light cream sidebar restored; dark sidebar removed; 189 inline colours reverted to their original values; Tailwind stone/gold restored.
- Kept from DS-094 (no colour impact): shared tokens (now holding the original values), page names instead of slogans, dashboard greeting, stray `overline` line fix, visible search, consistent buttons/inputs/tables/chips, purposeful motion with reduced-motion support.
- Contrast fixes without changing the palette: logo initials enlarged on #8B7A55, taupe chip text uses #5F5A4B, TEAM badge and `.accent-blue` use #76705E (as in the original CSS). Axe colour-contrast clean on all 19 primary pages.

### DS-094: Design system — brown identity, tokens, shell, motion

- Owner: "still not looking good; keep the brown pattern; sidebar colours; animations/touch".
- Root cause found: 2,075 hard-coded hex colours across 52 screen files (plus 188 in inline styles), a leftover "jewellers ERP" stone/gold palette, Tailwind's `overline` utility drawing a stray line over every label, serif display font with old-style figures for money, slogan headings ("The control room.", "Every rupee, in its place.") and cards that bounced on hover.
- Built: `index.css` token system (paper, surfaces, lines, ink 1-4, walnut brand `--accent #7A5A3C`, caramel, success/warning/danger/info + soft variants, radii, shadows, easing); legacy stone/gold names alias the new tokens; codemod moved every class colour to tokens (opacity-modifier colours and alpha-concatenated status colours mapped to the new palette hex). Components: walnut primary / quiet secondary buttons with press feedback, 38px inputs with brown focus ring, calm cards (lift only when clickable), unified table headers/row hover, consistent status chips. Type: Manrope headings with tabular lining figures, Inter text, calm labels. Shell: espresso sidebar with caramel active marker (tokens re-scoped so every child adapts), logo on a light tile, visible search field, quiet clock, no decorative strips. Page headers show the page name (13 slogans replaced); Dashboard greets the user with today's date. Motion: page ease-in, menus pop-in, press scale, active-bar grow; all disabled under prefers-reduced-motion.
- Fixed contrast in Calendar (out-of-month dates, holiday/milestone colours).

### DS-093: Project page de-duplicated; subscription read-only mode

- Owner feedback: DS-092 copied the reference too literally and duplicated content (facts strip vs Team/Site cards, Stage in facts and lifecycle bar, hub tiles repeating the tab bar and the header's client-portal button). Now: facts strip shows only client, type, area, location, start, target end; the Site/Schedule card is removed; the tiles are replaced by a short "Needs attention" list (overdue tasks, milestones due, invoiced-not-received, no project manager) with a link to fix each, or "Nothing overdue". Tabs remain the only navigation.
- Read-only mode (reference: Work Hand trial-ended state): `core/subscription.py`. A tenant is read-only only when the platform owner explicitly sets subscription status "expired", or "trial" with a past `trial_ends_on`; tenants with no subscription record are never restricted (no live tenant changes on deploy). Enforced server-side in both `require_user` implementations for every non-GET request; exempt: `/api/auth/*` (sign-in, sign-out, PIN) and `/api/notifications`; Super Admin never blocked. `/api/org/current` returns `subscription_state` (status, trial end, days left, read_only, message). UI: red banner when read-only, amber notice in the last 7 trial days. Super Admin > Organisations: per-tenant Plan control (not set / Trial + end date / Active / Ended), confirmation before making a tenant read-only, audited (`org.subscription`).
- Verified: `tests/test_subscription_readonly.py` (11); `e2e/ux.spec.mjs` creates a throwaway tenant, sets an ended trial -> POST refused 403 "Read-only", GET 200, banner shown -> Active -> writes work again; regression forms/money/navigation/smoke 28 passed; backend gate 377 passed.
- Reference review (read-only, owner's Work Hand session): Team page (seats used/free, Present/Pending/Past, owner account outside seats), Work Board (Board/List/Calendar views, group by status/category), trial banner + sidebar subscription card. Seats and work-board view ideas recorded for the research blueprint, not implemented.

### DS-092: Live PDF preview fix, header lock, project hub, projects toolbar

- Bug (production): invoice "Preview" and quotation Preview tab showed the browser's blocked-frame icon. Cause: every response carries `X-Frame-Options: DENY` (VPS Caddy) and `frame-ancestors 'none'`, so `<iframe src=/api/..pdf>` is refused. Fix: shared `components/PdfPreview.jsx` fetches the PDF with the session and shows it from a `blob:` URL (loading, error, Open in new tab, Download, Esc to close); `deploy/nginx.conf` CSP adds `frame-src 'self' blob:` and `object-src 'self' blob:`. Anti-clickjacking headers unchanged; Caddyfile untouched. Also moved the inline PerformanceServerTiming shim from index.html into the bundle (it was blocked by `script-src 'self'` on every page load).
- App lock moved from the sidebar footer to a lock icon beside the notification bell (one click locks; opens PIN setup when no PIN; Ctrl/Cmd+Shift+L). PIN settings remain as a small shield icon in the user row.
- Project home (reference: Work Hand): key facts strip (client, type, area, location, started, stage, team avatars) and "In this project" tiles with live counts (phases, tasks open/done/overdue, payment milestones to collect, vendors POs/bills, files, invoices outstanding, activity, client portal link). Financial tiles follow project financial visibility.
- Projects list: search, sort (newest/name/stage), stage chips with counts, grid/list toggle (remembered), "no match" state; title "Projects".
- Verified: `e2e/pdf.spec.mjs` preview test injects the production CSP + X-Frame-Options and asserts a blob: frame with no CSP violations; `e2e/ux.spec.mjs` lock/hub test; regression smoke/navigation/phases/a11y/pdf/proposal 30 passed, ux 8 passed.

### DS-091: Employee advances - give, recover through payroll, reverse (mandate 08, T06)

- Gap: "Advance recovered" only lowered net pay; nothing recorded the advance, salary expense was booked at net (understated by the recovery) and there was no outstanding balance.
- Built: `routes/employee_advances.py` - Give advance (amount, date, reason, Cash/Bank with method check, reference, optional monthly recovery) posts Dr Employee Advances / Cr Cash-Bank (source `employee_advance`). Payroll recovery is refused above the outstanding balance; the salary journal is now Dr Salary (net + recovered) / Cr Cash-Bank (net) / Cr Employee Advances (recovered); recoveries are allocated oldest-first and recorded per payroll run. Reversing a salary payment restores the recovered amount. Cancel = balancing journal, blocked once partly recovered. Audited, tenant-scoped, indexed.
- UI: Employee > Salary & Bank > Advances panel (outstanding, suggested monthly recovery, history with per-month recoveries, give/cancel); Pay Salary shows outstanding with a one-click suggested recovery.
- Also: unsaved-change browser warning on the quotation builder and employee form (`lib/useUnsavedWarning.js`).
- Verified: `e2e/money.spec.mjs` advance test (5,000 cash -> recover 2,000 [expense 24,000, bank 22,000, advances 2,000] -> over-recovery 400 -> cancel blocked 409 -> recover 3,000 closed -> reversal restores 3,000 -> UI shows 3,000); backend gate 366 passed.

### DS-088: Collections Due - active queue vs Received history (mandate 11, T08)

- Bug: the default "All" view kept fully received items in the queue at Rs. 0.
- Fix: default Active view = items with money still to collect; Received history view shows amounts received (and any balance still due); status chips show counts; category chips: Client payments, Vendor commission, Other receivables. Partial receipts show "of total".
- Verified: `e2e/ux.spec.mjs` (Rs. 5,000 expected -> receive 2,000 -> active 3,000 partial -> receive 3,000 -> gone from Active, 5,000 in history) desktop + mobile.

### DS-089: Leave privacy for staff (mandate 05, T03)

- Staff no longer receive the company leave entitlement table or the maternity/paternity categories (meta, balance, apply). Maternity/paternity leave is recorded by HR on the employee's behalf (403 with a clear message if staff try directly), so the statutory right is preserved. Staff see their own real balance (remaining/used) instead of the policy table. HR/managers unchanged.
- Verified: `tests/test_leave_privacy.py` (4) and `e2e/ux.spec.mjs`.

### DS-090: Transparent salary working + styled confirmations (mandate 07, 14)

- Pay Salary shows "How this is calculated": per-day rate formula (monthly / basis days), paid and LOP days, attendance counts, every deduction with its date and reason (absent, unpaid leave, half day, late by N min, short leave), additions and net.
- All 47 native browser confirm() popups replaced by one accessible styled dialog (`lib/confirm.jsx`): clear title/body, red action for destructive verbs, Cancel/Go back, queued safely.
- Verified: backend gate 366 passed; e2e ux/forms/money 14 passed.

### DS-087: Consultancy design proposal (quotation modes, owner's reference format)

- Source: owner's reference "Design Proposal_Krunal Soni_28.05.26.pdf" and the Production Finishing mandate (section 04, T02).
- Built: new consultancy quotations are a letter-style proposal with the reference's sections in order: greeting, project details (project, location, area, scope, designer), scope of work, design process & approvals (revision/render counts substituted into editable clauses), design fees & payment schedule (fixed fee, advance on confirmation, instalment every N months, extra-work note, optional GST), material procurement, communication + office number, optional site-coordination support (monthly fee, duties, role-limit note), terms, closing, signatory and a client acceptance line. Empty optional sections are omitted; the document flows across pages (sample = 2 pages, like the reference).
- Money: `core/consultancy_proposal.py` fee schedule is exact to the paisa; the last instalment takes the remainder; the fee drives the quotation grand total (and GST only when set).
- Modes: Consultancy-only workspaces can only create consultancy quotations, Turnkey-only only turnkey, Hybrid chooses at creation (two cards). Type can change only on a draft and only within the mode; saved/sent quotations keep their type and PDF. Turnkey builder and PDF unchanged; legacy consultancy quotations (no proposal block) keep their old template.
- Input safety: proposal payload whitelisted, trimmed, list/length capped, money validated (advance/instalment cannot exceed fee) -> 400 with a clear message.
- UI: Proposal and Fees & schedule tabs (list editors with reorder/remove, live schedule table and fee summary), Save now reports errors; type switch only for Hybrid drafts.
- Verification: `tests/test_consultancy_proposal.py` (15) incl. 2-page sample, no blank page, mode enforcement; backend gate 361 passed; `e2e/proposal.spec.mjs` desktop+mobile (UI create -> fee -> save -> 2-page PDF, invalid fee 400, sent type locked 409, axe clean).

### DS-086: Logo rebuilt from the owner's original file; logo uploads normalised

- The original "Design saga Logo Final 17-04 (01)-01.jpg.jpeg" (6250 px, construction grid) was rebuilt without the grid: the D outline is redrawn exactly from the construction lines (outer arc, counter circle, corner circle), the S, accent and wordmark are traced from the original. Files: Downloads "Design Saga - logo (final, transparent).png" and "... logo mark only (final).png".
- Uploads: `services/storage.normalize_logo` trims plain/transparent borders, keeps a 4% margin, caps at 1200 px and stores PNG (both upload endpoints); refuses decompression bombs. A 6250 px JPG with wide white margins no longer renders tiny.
- Display: sidebar shows the logo at its natural shape (48 px high, no white box); PDF letterhead logo 22 mm high; Company Settings preview larger, hint corrected (no SVG), Uploading/Replace states.
- Verification: `tests/test_logo_normalize.py` (6).

### DEPLOY-2026-11-06b: Release `bfb70cf` (phase templates) deployed

- Owner approved in chat. Bundle `fbe0311..bfb70cf` (SHA-256 `5bc69ba6...394c`, matched both ends) fast-forwarded in a transient unit; pre-deploy backup `/opt/design-saga-backups/20261106T080953Z`; backend and web healthy; `/healthz` ok; `/api/project-phase-templates` 401 (present, login required); 0 exceptions, 0 5xx.
- Read-only tenant check: tenants "Design Saga", "DESIGN SAGA" and "sample(Demo)" have no logo, address, GSTIN or bank details yet, so PDFs show name only until Company Settings is completed. The owner supplied the logo image in chat only; a file is needed to upload it, and the owner must confirm which Design Saga tenant is the real one.

### DS-085: Architecture phase templates on projects (PRJ-01)

- Gap: projects had one `stage` value on a fixed pipeline, with no per-phase dates, fee share or deliverables.
- Smallest connected slice: built-in templates (Consultancy design services, 8 phases; Turnkey design-and-build, 6 phases; fee shares total 100%). Applying one creates editable, tenant-scoped `project_phases` with sequential planned dates from the project start, deliverable checklists and status (not started / in progress / done, actual dates recorded). Optional fee milestones go into the existing payment-milestone (Collections Due) workflow with exact paise that sum to the project fee, only when the project has no milestones yet; phases with paid milestones cannot be removed. Read uses project visibility; apply/update/delete require `projects.update` plus visibility; audited.
- UI: Project > Phases tab (template picker pre-selected from the project's engagement type, progress, current/overdue phases, inline status/date edits, deliverable toggles; fee amounts only for users who can see project financials). Breadcrumb no longer repeats a group name equal to the page name.
- Verification: `tests/test_project_phases.py` (12) incl. visibility-first and `projects.update` gates; backend gate 340 passed; `e2e/phases.spec.mjs` desktop+mobile (apply with fee milestones summing to the fee, track status/deliverables, double apply refused, Employee refused, axe clean). Screenshot `docs/screenshots/project-phases.png`. Not deployed.
- Next slice: tenant-editable templates; link phase progress to the lifecycle stage.

### DEPLOY-2026-11-06: Release `fbe0311` deployed to production

- Contents: DS-082 (money footing), DS-083 (WCAG 2.1 A/AA pass), DS-084 (double-submit guard, toasts, setup checklist). Owner approved the deploy in chat on 06/11.
- Method: git bundle `8d17a12..fbe0311` (SHA-256 `e077212c...5c0f`, matched on both ends, verified) fetched on the VPS and fast-forwarded inside a transient systemd unit; post-merge hook ran `deploy/update-production.sh`.
- Result: pre-deploy backup `/opt/design-saga-backups/20261106T074528Z`; backend and web rebuilt and healthy; "Design Saga deployment completed: fbe0311".
- Live checks: `/healthz` ok; `/api/auth/me` 401; integrity endpoint 401; new main bundle contains the submit guard and AA palette; CSP header served; 0 backend exceptions and 0 5xx in the first minutes; daily backup timer scheduled 18:25 UTC.
- Not yet verified by a signed-in owner: Getting started checklist content, logo on PDFs, Data checks on real data.

### DEPLOY-2026-11-05: Repair release `8d17a12` deployed to production

- Target verified before deploy: hostname `srv2020574`, eth0 `187.52.124.46`, `/opt/design-saga-git` on GitHub remote `Dhruvsob/design_saga`, previous runtime `3b15e23`, only the protected Caddy files modified locally (untouched), 14 GB disk free, all five containers healthy.
- Access: SSH works via `srv2020574.hstgr.cloud` over IPv6; the IPv4 address still times out on port 22. The VPS cannot reach github.com (GitHub has no IPv6), so the 44 commits were shipped as a git bundle over SSH (SHA-256 `4022e85c...7bb7`, matched on both ends, `git bundle verify` passed) and fast-forwarded with `git merge --ff-only`; the post-merge hook ran `deploy/update-production.sh` inside a transient systemd unit.
- Result: pre-deploy backup `/opt/design-saga-backups/20261105T184001Z`; backend and web rebuilt and healthy; rollback image tags `rollback-3b15e23`; "Design Saga deployment completed: 8d17a12".
- Live verification (06/11): `/healthz` ok; `/api/auth/me` 401; new `/api/accounting/integrity/source-links` 401 (exists, requires login); new CSP/COOP headers served; production bundle contains grouped navigation; zero backend errors and zero 5xx since deploy.
- Backups: the scheduled `design-saga-backup.service` had failed daily since 27/10 (read-only sandbox vs `chmod` in backup.sh). Fixed in `8d17a12`; a manual run of the real sandboxed unit succeeded (`20261106T045038Z`, 64 MB, SHA256SUMS verified).
- Not yet live-verified (needs a signed-in owner): uploading the real logo and printing each PDF, running Accounting > Validation > Data checks on real data, salary/vendor payment Cash/Bank pairing in the real forms.

## Canonical Open Backlog (05/11/2026 delta from `f9e1351`)

This is the single deduplicated list of genuinely open work. It supersedes the
open rows scattered across the BR-/DS- tables, the risk register and the
planning reports; those keep their history and evidence. Closed DS-/BR- items
are not repeated. Status vocabulary: Confirmed, Audit Needed, Decision Needed,
Externally Blocked, Implementing, Tested (local), Deployed, Live Verified.

Investigation method for this delta: full route/guard inventory (DS-071),
scoped-DB wrapper and raw-collection review, default RBAC matrix review,
money/tax computation trace, sidebar/IA review, and existing test inventory.
Browser journeys could not be executed: this workstation has no Docker, no
local MongoDB/FerretDB and no browser E2E harness (see OPS-06).

### 0. 08/11/2026 inventory delta (live code + browser runs on a disposable DB)

Method: route-by-route read of the money screens (Accounting, Collections Due, Received Payments, Payment Reminders, entry panel), table/⋮ coverage scan of every page, the full desktop E2E suite (61 cases) and the existing phone-overflow/runtime-error smoke tests. Rows below are new; older open rows stay in sections 1-12.

| ID | Module | Exact location | Current problem | Change | Pri | Depends | Status |
|---|---|---|---|---|---|---|---|
| INV-01 | Collections | `TransactionDetail.jsx` `canDelete` | Receipts on Collections Due rows (`other_receivable_income`, now the path for every new invoice collection) could not be deleted/reversed anywhere in the UI although the API supports it | Allow Delete (reversal) + "Open Collections Due" drill-through | P1 | — | Deployed (DS-112, `82202e4`) |
| INV-02 | Reminders | `_sync_other_receivable_after_reversal`, `_reverse_commission_settlement_locked` | Reversing a receipt made money due again but left its reminder, calendar/Google event and alerts closed | Refresh reminders on both reversal paths | P1 | — | Deployed (DS-112, `82202e4`) |
| INV-03 | Received Payments | `ReceivedPayments.jsx` | Page says "correct from the Daybook" but gives no link to the entry | Row ⋮: Open entry, Open source | P1 | — | Deployed (DS-112, `82202e4`) |
| INV-04 | Collections Due | `Accounting.jsx` CollectionsDue row | ⋮ only on unreceived manual plans; no view of receipts behind a collection; inline "Open" did a full page reload | Always-on ⋮: Receipts & entries, Open vendor/project, Edit/Cancel when allowed | P1 | — | Deployed (DS-112, `82202e4`) |
| INV-05 | Accounting | — | No period close, lock or Excel export | Close & export workflow | P1 | — | Deployed (DS-111, `6ccdd8f`) |
| INV-06 | Received Payments API | `money_in.py` `received_payments` `to_list(5000)` | Silent 5,000-row cap (R1 regression) | Read all rows (money); display lists use MAX_LIST_ROWS | P2 | — | Deployed (DS-113, `c7aaf2f`) |
| INV-07 | Collections | Collections Due | No receivable aging (0-30/31-60/61-90/90+) by client/project | Aging strip + filter on the existing queue | P2 | — | Deployed (DS-113, `c7aaf2f`) |
| INV-08 | Lists | Expenses, Loans, Purchase orders | Row actions only inside the detail panel (U1) | PO row ⋮ (send/cancel); Expenses/Loans keep row-opens-panel by decision | P2 | — | Deployed (DS-113, `c7aaf2f`) |
| INV-09 | Performance | `Accounting.jsx` (~2,100 lines), `Attendance.jsx`, `VendorDetail.jsx` | One bundle per page (R6) | Measured: routes already lazy; 174 KB gzip shell | P3 | Analyser | Measured (DS-113) |
| INV-10 | Navigation | `Layout.jsx` NAV | Sidebar already groups Sales · Projects · Procurement · Finance · People · Administration, permission-filtered (DS-074/096) — matches the requested Project → Finance → People → Admin hierarchy | No move needed; keep URLs | — | — | Verified |
| INV-11 | Retention | Close & export | Purge of exported years | Only after owner/CA decision + off-server backup (ACC-10, OPS-02) | P2 | Owner | Decision Needed |

### 1. Security, tenancy and authentication

| ID | Sev | Item and evidence | Status | Smallest safe solution / acceptance |
|---|---|---|---|---|
| SEC-01 | P0 | Exposed Atlas password + Mongo viewer token in old commits/chat (risk register) | Externally Blocked | Owner rotates/revokes at provider; record date in secret inventory |
| SEC-02 | P1 | Default `Employee` and `Designer` roles hold `clients.read` + `leads.read` (`core/rbac.py`), so every employee sees all client contacts and the full sales pipeline | Decision Needed | Owner decides default visibility; if restricted, change defaults with a migration note for tenants that customised roles |
| SEC-03 | P2 | `_ScopedColl.__getattr__` passes unwrapped methods (`estimated_document_count`, `bulk_write`, `watch`, ...) straight to the raw collection; no current caller, but a future one would read/write across tenants | Deployed (DS-073; `e3a855a`) | Fail closed for tenant-unsafe passthroughs; regression test |
| SEC-04 | P2 | Admin sidebar entries gate on `role === "Admin"` instead of permission, so a tenant owner on a custom full-access role loses Company/Audit links while backend allows them | Deployed (DS-074; `e3a855a`) | Gate on permission + platform flag only |
| SEC-05 | P2 | Secret inventory document (owner/purpose/rotation/revocation, never values) | Done (09/11) | `docs/runbooks/secret-inventory.md`; SEC-01 rotation row still pending owner |
| SEC-06 | P2 | Object-level assignment visibility for invoices/quotations/clients is tenant-wide by permission design; needs explicit product rule per role | Decision Needed | Tie to SEC-02 decision |
| SEC-07 | P3 | Server-side malware scanning and orphan-object reconciliation for uploads | Confirmed (defense-in-depth) | ClamAV sidecar or documented acceptance |

### 2. Accounting and financial integrity

| ID | Sev | Item and evidence | Status | Smallest safe solution / acceptance |
|---|---|---|---|---|
| ACC-01 | P1 | `compute_invoice_totals` (`server.py`) rounds each line but sums unrounded amounts, adds tax to the unrounded subtotal, and uses binary-float `round()` (₹2.675 → ₹2.67): printed lines can fail to foot to subtotal/total | Deployed (DS-073; `e3a855a`) | Decimal ROUND_HALF_UP per line; subtotal = Σ rounded lines; total = subtotal + tax; only affects new/edited drafts |
| ACC-02 | P1 | GST is one tax amount; no CGST/SGST vs IGST split, place of supply, tenant GSTIN/state (BR-016) | Decision Needed | Needs tenant state + client state fields and accountant sign-off on rounding |
| ACC-03 | P1 | Run DS-072 `/api/accounting/integrity/source-links` on production and reconcile record by record | Live Verified 09/11: all five checks zero for all eight tenants; every audit chain verifies | Report only; no automatic repair |
| ACC-09 | P1 | Historical payroll/vendor-payment rows booked to Cash with a non-cash method (DS-076 root cause) are not yet listed for correction | Live Verified 09/11 (DS-120): real Design Saga was clean; the one Demo metadata mismatch was repaired to match its unchanged Cash journal and audited | Prevention remains enforced by shared method/account validation |
| ACC-04 | P1 | Decimal/minor-unit policy across PO, bill, commission, payroll, loans (floats with `round(x, 2)` throughout) | Deployed (DS-082; `e3a855a`) | Shared money helper adopted module by module after ACC-01 proves the pattern |
| ACC-05 | P2 | TDS, commission tax treatment, credit notes (period close done in DS-111) | Decision Needed | Accountant policy first |
| ACC-10 | P2 | Purge/archival of exported years: only after owner/CA retention decision, verified off-server backup (OPS-02) and restore drill | Decision Needed | Keep closed years read-only in place; no deletion of posted books |
| ACC-06 | P2 | Tally export (BR-017), invoice email sending (BR-014), payment link/UPI (BR-015) | Confirmed gaps | Product scope decision; not correctness defects |
| ACC-07 | P3 | Plain-language Money In / Money Out / Collections Due / Banking / Daybook / Reports framing with advanced tools for finance roles | Audit Needed | After IA batch |

### 3. Attendance, leave, payroll and HR

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| HR-01 | P1 | Live validation of payroll Cash/Bank posting, reversal/repost and monthly paid-leave/LOP | Live Verified 09/11 (DS-120): Demo interrupted reversal recovered through the application workflow; exactly one reversal remains and integrity is clean | Current shared validator, idempotent recovery and regression suite prevent recurrence |
| HR-02 | P2 | Statutory payroll (PF/ESI/PT/TDS), payslip delivery, bank files | Decision Needed | Scope decision |
| HR-03 | P2 | Leave carry-forward/encashment rules | Decision Needed | Policy |

### 4. Projects, tasks, phases and site execution

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| PRJ-01 | P2 | Generic stages; no configurable architecture phase templates with fee/dates/deliverables | Deployed (DS-085; `e3a855a`) | Smallest slice: per-tenant phase template applied at project creation, editable |
| PRJ-02 | P2 | Site diary / issue / snag with photo evidence and closure is missing (supervisors use tasks) | Deployed in current `143c995` (DS-116) | Snag list with issue/fix photos and verified closure; site diary covered by site visits (DS-110) |
| PRJ-03 | P3 | Timesheets, capacity planning, planned-vs-actual hours | Confirmed gap | Later; depends on PRJ-01 |

### 5. CRM, clients, quotations, invoices and collections

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| CRM-01 | P2 | Lead → quotation → project chain not verified end to end on current code | Deployed in current `143c995` (DS-115) | Duplicate-project defect fixed; E2E added |
| CRM-02 | P3 | Duplicate lead merge, source attribution | Confirmed gap | Later |

### 6. Vendors, procurement, bills, payments and commissions

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| VEN-01 | P1 | Live 3-way-match correction and vendor/project/report reconciliation | Live Verified: procurement-chain mutation E2E passes; all production source/journal/link checks are clean after DS-120 | No production seed/mutation retained; continue regression coverage |
| VEN-02 | P3 | Bill creation discoverability from vendor and PO context (BR-027) | Deployed in current `143c995` (DS-118) | Record vendor bill from received/partial PO row or detail panel |

### 7. Files, drawings, revisions, RFIs, submittals and approvals

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| DOC-01 | P2 | No drawing register (number, revision, issue purpose, supersession, transmittal) | Deployed in current `143c995` (DS-114) | Register + revisions + approvals + Excel; transmittal PDF remains a separate P3 enhancement |
| DOC-02 | P3 | RFIs/submittals, client selections, change orders | Confirmed gap | Validate demand first |

### 8. Frontend information architecture and UI/UX

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| UX-01 | P2 | Flat 19-item sidebar with meaningless section codes ("04b", "12b") and no workflow grouping (`Layout.jsx`) | Deployed (DS-074; `e3a855a`) | Permission-aware groups: Sales, Projects, Procurement, Finance, People, Administration; stable URLs |
| UX-02 | P2 | Breadcrumb shows only Brand › Page; no group context | Deployed (DS-074; `e3a855a`) | Brand › Group › Page |
| UX-03 | P2 | Mobile drawer has no close button (only backdrop tap); `X` icon imported but unused | Deployed (DS-074; `e3a855a`) | Accessible close button |
| UX-04 | P2 | Large flat dropdowns for project/client/vendor/employee/account (BR-029) | Deployed (DS-081; `e3a855a`) | Searchable combobox for high-volume selectors |
| UX-05 | P2 | Form safety: double-submit, unsaved-change warning, field-level server errors (risk register "Audit") | Deployed (DS-084; `e3a855a`); unsaved-change and field-level errors remain a P3 follow-up | Shared form hooks, module by module |
| UX-06 | P3 | Role-specific home (principal, PM, supervisor, accountant, HR, employee) | Deployed in current `143c995` (DS-118) | Permission-aware My day, sales/team and finance widgets |

### 9. Accessibility, responsive behaviour and browsers

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| A11Y-01 | P2 | Keyboard/focus/contrast/table semantics audit; supported-width visual QA; Chrome/Edge/Safari/mobile smoke | Deployed (DS-083; automated axe A/AA and responsive E2E); manual screen-reader/Safari/tablet QA remain | Needs running app (OPS-06) |

### 10. Database, performance and scalability

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| DB-01 | P2 | Slow-query/index audit with large-tenant data; API latency budgets (DS-008) | Measured 09/11 | Production last 24 h: 231 requests, 0 over 1 s, max 234 ms; new collections (drawings, snags, period exports) indexed by org+project. Re-run with a large synthetic tenant before onboarding big studios |
| DB-02 | P2 | Rate-limit buckets in process memory; must move to shared storage before >1 worker | Confirmed constraint | Keep single worker until done |
| DB-03 | P3 | Large-export streaming | Confirmed | Later |

### 11. DevOps, backups, monitoring and deployment

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| OPS-01 | P0 | Deploy accumulated branch (`3b15e23` → current) | Live Verified at runtime `648b01a` on 09/11; three verified release/repair backups, healthy backend/web, protected Caddy hashes unchanged | Continue guarded bundle releases; back up first and preserve protected Caddy files |
| OPS-02 | P1 | Encrypted off-server backup replication + alerting | Externally Blocked (destination/credentials) | Owner chooses provider |
| OPS-03 | P1 | External alert delivery (uptime/5xx/TLS/disk/backup) | Externally Blocked | Owner chooses webhook/email target |
| OPS-04 | P2 | Container image scanning, immutable release tags, CI approval gate | Deployed and live-verified at `6ec8745` | Pinned Trivy HIGH/CRITICAL gate, fresh `--pull` builds and revision-labelled immutable release tags |
| OPS-05 | P2 | Log retention/rotation evidence | Live Verified 08/11: journald 1 GB/7 days, Docker 10 MB x 3, exact legacy-container rule active; 1.5 GB compressed without downtime | Verify on host |
| OPS-06 | P2 | No repeatable browser E2E or disposable-DB integration harness locally or in CI | Deployed (DS-075; Playwright desktop/laptop/mobile + disposable DB in quality workflow) | Add a CI job with a Mongo service + Playwright smoke for login and core journeys |

### 12. Commercial product readiness

| ID | Sev | Item | Status | Solution |
|---|---|---|---|---|
| PROD-01 | P3 | Onboarding checklist for a new tenant (company, roles, employees, first project) and useful empty states | Deployed (DS-084; `e3a855a`) | After IA batch |
| PROD-02 | P3 | In-app help/glossary for accounting terms (BR-035) | Confirmed gap | Inline help with ACC-07 |

### Execution order

1. Completed and deployed: ACC-01/04/09, SEC-03/04, UX-01..05, PRJ-01,
   OPS-01/04/05/06 and the DS-110 repair release.
2. Next independent engineering work: DB-01 measured query/index audit. Do not
   tune indexes without production-like traces.
3. Owner/accountant decisions remain required for SEC-02/06, ACC-02/05/06 and HR-02/03.

### OPS-04 verification evidence (09/11/2026)

- The backend runtime base contained two fixable HIGH `zlib1g` findings
  (CVE-2026-76844 and CVE-2026-85091). The Dockerfile now installs the current
  Debian security update during the image build; a disposable rebuilt image scans
  with zero HIGH/CRITICAL findings. The web image also scans clean.
- CI builds fresh backend and web images and scans both with the Trivy action pinned
  to an immutable commit. Any fixed HIGH/CRITICAL finding fails the workflow.
- The production updater builds with `--pull`, records the Git revision as an OCI
  image label, creates non-overwritable `release-<commit>` tags and retains its
  existing change-aware, rollback-safe deployment behaviour.
- Current branch validation: 473 backend tests passed; frontend ESLint, five logic
  tests and production build passed. Focused Playwright journeys passed for period
  close/export/reopen and collection/commission receipt correction (desktop and
  mobile where applicable): 5 passed, 1 intentionally skipped on mobile.
- Live verification at `6ec8745`: all five containers are healthy; the public site
  and API return 200; protected auth, integrity and period-close routes return 401;
  CSP/HSTS/frame/content-type/referrer/permissions headers are present; no
  `gamaa.in` 5xx or backend exception appeared after deployment. The running backend
  release tag and OCI revision match `6ec8745`; Trivy reports zero fixable
  HIGH/CRITICAL findings in both deployed images. Read-only source-integrity checks
  for both Design Saga organization records are clean across every reported count.

### DS-084: Form safety, non-blocking errors and new-firm setup checklist (UX-05, PROD-01)

- Double submit (reproduced): double-clicking Save on the Clients form created two identical clients 11 ms apart; about 15 forms (Clients, Projects, Invoices, Quotations, Tasks, Project detail and others) had no busy guard. Fix: `src/lib/submitGuard.js`, installed once in `index.js`, swallows a repeat submit of the same form while its write requests are in flight (tracked by new counters in `lib/api.js`), disables and marks busy only the buttons it disabled, releases on completion (0.4 s grace when the handler sends no request; 30 s safety release); `data-allow-resubmit` opts out. Covers every current and future form.
- Blocking pop-ups: 31 `alert()` calls (Attendance, Employee, Invoices, Project, Quotation, Super Admin) became non-blocking toasts consistent with the rest of the app; two vague "Failed" messages now say what failed; quotation conversion no longer shows an internal project ID.
- New tenants landed on an empty dashboard. An admin-only "Getting started" checklist (logo, address/contact/GSTIN, bank details, first employee, client, project, vendor) is derived from real data, links to each screen, ticks itself off, hides when complete and can be dismissed.
- Tests: E2E double-click test (failed with 2 records before the fix), checklist tests (admin links and dismiss; employee never sees it). Navigation tests now unlock the 5-minute App PIN before each test so long runs stay reliable. E2E navigation 16 passed; forms/money/pdf/smoke/a11y passed in the full run. Not deployed.
- Deferred (P3): 47 native "Are you sure?" confirmations still work and are accessible; replacing them with one styled dialog is a consistency follow-up.

### DS-083: WCAG 2.1 A/AA accessibility pass across all primary pages (A11Y-01)

- Method: new `e2e/a11y.spec.mjs` runs axe-core (WCAG 2/2.1 A and AA rules) on all 19 primary pages and each page's main create form as an Admin. Baseline: 437 violations across 4 rules.
- Root causes and fixes:
  - Colour contrast (418): the caption/label grey `#9B9B9B`/`#9A9A9A` reached only 2.5-2.8:1. The `--ink-3` token and 193 inline uses now use warm grey `#6E6A63` (4.9:1 on cream, 5.4:1 on white); brand-brown text uses `#76705E` (95 uses); primary buttons use `--stone-600` (white text 5:1, was 3.9:1) with a darker hover; calendar type colours, the Outstanding KPI, audit-log timestamps, out-of-month calendar days and the locked-role badge were darkened to pass.
  - Unnamed dropdowns (11 flagged; 98 found by scan): each unlabelled `<select>` gets an `aria-label` naming the field it controls, except where a visible `<label>` already wraps it; poor derived names were hand-corrected; the shared task-table `InlineSelect` takes a `label` per column.
  - Unlabelled fields (6): Holidays year/date/name and the Company Settings colour picker/hex inputs.
  - Icon-only buttons (2): Calendar previous/next.
- Result: 0 violations; all rules including colour contrast are enforced as a CI gate. Visual review confirmed the same brand palette, only darker greys/chips.
- Also: Playwright discovery was silently skipping spec files that OneDrive had converted to cloud-file placeholders (reparse points) in this checkout; recreated them locally. Recommendation: keep the Git checkout outside OneDrive.
- Verification: E2E 21 passed (incl. the accessibility gate); ESLint, build, `npm audit --omit=dev` 0 vulnerabilities. Not deployed.

### DS-082: Every money document foots to the paisa (ACC-04)

- Root causes: purchase orders, vendor bills, vendor commission and the quotation cost sheet repeated the invoice defect fixed in DS-073: unrounded line amounts were summed while rounded amounts were displayed, tax was computed on unrounded subtotals, and binary-float `round()` turned 2.675 into 2.67. The quotation payment plan rounded each milestone separately, so a 33.33/33.33/33.34 plan did not add up to the grand total. The PO and bill forms previewed totals with unrounded float arithmetic.
- Fix: PO (`_po_totals`), bill (`_bill_total`), commission (`_calc_commission_amount`, fixed/percentage/slab) and quotation (`_q_compute_costs`: lines with margin, category/room totals, discount, contingency, GST, grand total) use `core/money.py` Decimal half-up per displayed figure; when milestone percentages total 100%, the last milestone takes the exact remainder. PO and bill previews use `roundPaise`. Loans and payroll already reconcile (tests added, code unchanged).
- Data effect: none; stored documents are not recomputed. Only new or edited drafts use the rule (differences are at most a paisa per figure).
- Verification: 6 new tests in `tests/test_money_footing.py` (4 failed before the fix); mandatory backend gate 330 passed; ESLint and production build pass. Not deployed.

### DS-081: Searchable selectors and phone-width layout fixes (UX-04)

- Root cause: 52 client/project/vendor/employee/account pickers across 14 screens (Accounting forms and Daybook filters, Invoices, Record Payment, Vendor bills/payments/commissions, Purchase Orders, Quotations, Projects, Tasks, Calendar, Attendance, Loans, Salary, Ledger panel, Recurring expenses) were plain dropdowns that become unusable as a firm accumulates records.
- Fix: `frontend/src/components/SearchSelect.jsx` is a drop-in replacement for `<select>`: it reads the same `<option>`/`<optgroup>` children and calls `onChange({ target: { value } })`, so every handler is unchanged (a guarded scan converted only selects bound to an entity id; no handler uses native-only select APIs). It shows a search box above 7 options, supports keyboard (Enter/Space/ArrowDown open, arrows, Enter select, Escape close, focus returns), exposes `role="combobox"`/`aria-expanded`/accessible name, and keeps native `required` validation through a hidden input. Built on the existing cmdk + Radix popover UI kit; no new dependency.
- Responsive defects found by a new phone-width sweep and fixed: Invoices list table widened the whole page on phones (now scrolls inside its own container); the shared PageHero action row never wrapped (Accounting reached 650px on a 412px phone; now wraps for every page); a Company Settings colour input could not shrink.
- Verification: unit test for option parsing; browser `e2e/forms.spec.mjs` on desktop and mobile (long client list is searchable, keyboard open/close, the saved invoice carries the searched client); new `smoke.spec.mjs` phone test asserts none of the 19 primary pages scrolls sideways. E2E 20 passed; backend gate 324 passed. Screenshot: `docs/screenshots/searchable-client-picker.png`. Not deployed.

### DS-080: List historical payments booked to the wrong Cash/Bank account (ACC-09)

- Need: DS-076 stops new mismatches, but payments recorded before the fix (e.g. a salary marked Bank Transfer that credited Cash) stay in the books until corrected.
- Fix: the read-only `/api/accounting/integrity/source-links` report adds `method_account_mismatches`, applying the same rule as the live check (`core.finance.method_account_problem`). Covered with certainty: salary runs, vendor payments, commission receipts and other-receivable collection receipts (method and account are stored). Generic Money In/Out (including invoice/milestone receipts) is covered when the default description "Payment received via <method>" / "Expense - <method>" is present and is labelled `inferred`; custom descriptions are never guessed. Each finding shows date, type, party (employee names, not codes), amount, recorded method, account used, the problem and the exact screen/action to correct it through reverse-and-record-again. Up to 500 rows are returned with a truncation flag.
- UI: Accounting > Validation now starts with an admin-only "Data checks" panel (run on demand, plain-language counts for all five checks, mismatch table with correction steps). Screenshot: `docs/screenshots/accounting-data-check.png`.
- Data effect: none; strictly read-only. No record is modified or auto-corrected.
- Verification: 5 new unit tests in `tests/test_accounting_source_integrity.py` (all record types, cash-method-to-bank, no false positives for consistent/unknown-account rows, narration inference, custom narration not guessed); live QA run with two simulated pre-fix records (inserted only into the local disposable QA database) listed exactly those two while dozens of correct transactions were not flagged; browser E2E runs the panel without errors. Backend gate 324 passed; E2E 17 passed. Not deployed.
- Owner action after deployment: open Accounting > Validation > Run data check and correct each listed payment from its own screen.

### DS-079: Branded PDFs with tenant logo on every document

- User request (05/11): every PDF must show the company logo and full company details in a proper professional format, invoice and quotation first.
- Root causes: (1) logo upload depended on the external Emergent object store; with `EMERGENT_LLM_KEY` blank (the deployment template default) uploads failed with 503, so no tenant could have a logo on any PDF; (2) the quotation PDF never drew a logo or company address/contact/GSTIN; salary slip, attendance payslip and commission statement had name-only headers; (3) https logo URLs were silently ignored by the PDF code.
- Fix: `backend/core/pdf_brand.py` provides one letterhead (logo + name, tagline, address, phone/email/website, GSTIN/PAN; document title and meta on a fixed right column), a running header with logo on continuation pages, a footer on every page (company, GSTIN/PAN, footer note, "Page X of Y"), a payment-details block and an authorised-signatory block. All five PDFs use it: invoice (Tax Invoice when GSTIN + GST, Bill To/Project, balance due after part payment, amount in words), quotation (letterhead cover, numbered sections without gaps, payment details on the acceptance page), salary slip (employee bank account masked to the last 4 digits; payment line shows date, method, account and reference), attendance payslip (marked "Not a payment receipt") and commission statement (DD/MM/YYYY dates, plain-language statuses, repeating table header). Logos are normalised to PNG with Pillow; external logo URLs are never fetched server-side (SSRF). `services/storage.py` stores logos on the backed-up `/data/files/branding` volume when the external store is not configured, with a strict path allowlist.
- Verification: `tests/test_pdf_branding.py` (11) and browser `e2e/pdf.spec.mjs` (uploads a test logo through the real API, downloads all five PDF types, asserts the embedded image and the masked account). Rendered samples were visually inspected, including a 3-page invoice with a 66-character company name; overlap/overflow defects found there were fixed. Not deployed.
- Owner action after deployment: upload the real logo and fill address, contact, GSTIN/PAN and bank details in Company Settings. Nothing is invented when a field is blank.

### DS-078: Attendance page for accounts without an employee profile

- Root cause: the tenant owner (created by Super Admin) has no employee profile. Attendance loaded eight requests in one `Promise.all`; the personal calls returned 400 "link an employee profile", which rejected the whole batch, left unhandled errors and discarded attendance meta, policy and project data for admin tools.
- Fix: personal calls fail independently; the "My attendance" tab explains how to link a profile; admin/HR data always loads. Verified by the page smoke E2E. Not deployed.

### DS-077: Vendor detail page crash and undefined-identifier guard

- Root cause: the DS-070 receipt-edit form was placed inside the generic `Field` component instead of `Commissions`, so `editingReceipt` was undefined and every vendor detail page rendered blank on the repair branch (production `3b15e23` predates it). ESLint had `no-undef` off.
- Fix: form moved into `Commissions`; `no-undef` enabled (current code passes; it reports the original bug). New `e2e/smoke.spec.mjs` opens all 19 primary pages and vendor/employee/client detail pages and fails on any runtime error or blank page. Not deployed.

### DS-076: Cash/Bank method-account mismatch (salary booked to Cash as "bank transfer")

- Reported symptom: salary paid as Bank Transfer appeared under Cash in the Daybook.
- Root causes (reproduced against the live QA stack): the default chart flags Cash and Petty Cash with `is_bank=True`, and every non-cash check only tested `is_bank`, so receipts, Money Out, salary and commission receipts accepted "bank_transfer" into Cash (HTTP 200). In the salary, Money In/Out, invoice payment and commission forms, choosing a non-cash method auto-selected the first `is_bank` account, which is Cash. Vendor payments validated nothing (free-text method, any asset account) and their form defaulted to Cash + Bank Transfer.
- Fix: shared `core.finance.validate_method_account` (cash method requires Cash/Petty Cash; any other method requires a real bank account, never Cash) used by Money In, Money Out, collections, payroll, commission receipts and vendor payments; shared frontend `lib/cashbank.js` pairs method and account in all six forms. Commission status key `invoiced` is labelled "Partially received" in the UI (stored key unchanged).
- Data effect: none; historical mismatched records are not rewritten. Follow-up ACC-09 lists them for record-by-record correction.
- Verification: `tests/test_cash_bank_consistency.py` (14), updated `test_accounting_safety.py`, and browser `e2e/money.spec.mjs`: invoice issue + partial/full collection with idempotent retry and over-collection refusal; payroll bank payment posts once to the chosen bank with the employee name, duplicate refused, reversal and re-payment; vendor commission planned posts nothing, partial receipt posts once to bank, UI shows "Partially received". Not deployed.

### DS-075: Disposable-database browser E2E harness (OPS-06)

- Root cause: no repeatable way existed to sign in and exercise the real UI against a database; all UI claims rested on code inspection, lint and build.
- Fix: `backend/scripts/qa_bootstrap.py` creates a QA platform owner only when `MONGO_URL` is localhost and `DB_NAME` starts with `design_saga_qa` (refusals verified for a remote host and a production-like name) and resets that owner's PIN/sessions per run. `frontend/e2e/global-setup.mjs` then creates a fresh tenant, Admin and Employee through the real API (including the mandatory App PIN step) and refuses non-local targets. `frontend/playwright.config.mjs` runs desktop (1440), laptop (1280) and Pixel 7 projects. Vite dev/preview gained a same-origin `/api` proxy (no production effect). New CI job `e2e` runs the stack against a `mongo:8.0` service with per-run generated QA secrets.
- Evidence: 10 passed, 2 skipped (mobile-only test on wide viewports): workflow groups and Finance › Invoices breadcrumb, mobile drawer close, no sidebar horizontal overflow, Employee sees no Administration/Accounting/Invoices/Loans/Employees/Quotations. Screenshots in `docs/screenshots/`.
- Also: pre-existing high-severity `follow-redirects` advisory (via axios) resolved by a lockfile-only update to 1.16.2; `npm audit --omit=dev` reports 0 vulnerabilities. `@playwright/test` 1.49.1 added as a pinned dev dependency.
- Limits: local QA runs on MongoDB 8.0, not FerretDB/PostgreSQL as in production, so FerretDB-specific behaviour still needs staging/production verification. `quality.yml` triggers on `main` pushes/PRs and manual dispatch, so pushes to `codex/repair-release` do not run it automatically.

### DS-074: Grouped permission-aware navigation

- Root causes: the sidebar was one flat list of 19 backend modules with meaningless section codes ("04b", "12b"); the breadcrumb showed only Brand › Page; the mobile drawer could only be closed by tapping the backdrop; admin links were gated on `role === "Admin"` instead of the permissions `App.js` and the backend already enforce, hiding Company/Audit from full-access custom roles and Team & Roles from roles holding `users.read`.
- Fix (`frontend/src/components/Layout.jsx`, `frontend/src/lib/navigation.js`): workflow groups Dashboard · Sales (Leads, Clients, Quotations) · Projects (Projects, Tasks, Calendar) · Procurement (Vendors, Purchase Orders) · Finance (Invoices, Accounting, Expenses, Loans & EMI) · People (Employees, Attendance, Holidays) · Administration (Company, Team & Roles, Audit Log). Every URL, `data-testid`, permission and tenant module flag is unchanged; groups with no permitted item are hidden; breadcrumb is Brand › Group › Page with `aria-current`; labelled `nav`/`group` landmarks; accessible mobile close button.
- Verification: `node --test src/lib/frontend-logic.test.mjs` (permission filtering, disabled modules, permission-not-role admin gating, empty-group removal) added to CI; ESLint 0 warnings; production build passes. Browser-verified under DS-075 at 1440px, 1280px and Pixel 7 widths with real Admin and Employee sessions; a mobile brand/close-button overlap found in screenshots was fixed. Not deployed.

### DS-073: Invoice totals that always foot, and scoped-DB fail-closed passthrough

- Root causes: `compute_invoice_totals` rounded each displayed line but summed unrounded products, then added tax to the unrounded subtotal, using binary-float `round()` (₹2.675 → ₹2.67), so a printed invoice could fail to foot by a paisa. The invoice form preview and outstanding figure used unrounded float arithmetic. Separately, `_ScopedColl.__getattr__` passed tenant-unsafe methods (`estimated_document_count`, `bulk_write`, `watch`, `drop`, ...) straight to the raw collection (no current caller).
- Fix: new `backend/core/money.py` (Decimal, ROUND_HALF_UP to paise; inputs via `str()`); invoice line = round(qty × rate), subtotal = Σ rounded lines, tax = round(subtotal × rate), total = subtotal + tax; floats only at the API boundary. Frontend `roundPaise` mirrors the policy in the invoice preview and outstanding/payment cap. Scoped collections now raise for tenant-unsafe passthrough methods.
- Data/migration effect: none. Stored invoices are not recomputed; only new or edited drafts use the new arithmetic (differences are at most one paisa per figure). Journals post the invoice's stored total/tax, so ledger and invoice stay identical.
- Policy note: half-up to the paisa is the engineering default; whole-rupee GST rounding or CGST/SGST split rounding remains an accountant decision under ACC-02.
- Verification: `tests/test_money_footing.py` (11 tests; 9 failed before the fix) added to CI; expanded backend gate 297 passed; frontend logic tests 4 passed. Not deployed.

### DS-072: Read-only accounting source-integrity report

- Root cause: unique `idempotency_key` indexes (fail-closed at startup) prevent duplicate linked postings, but nothing detected ledger/source divergence they cannot prevent: unbalanced journals, active journals whose source record no longer exists, reversal links pointing to missing journals, or paid payroll runs / active vendor payments whose linked journal is missing or reversed. The existing `/accounting/dashboard/validation` only compares legacy revenue figures.
- Fix: admin-only (`*.*`) `GET /api/accounting/integrity/source-links` evaluates the tenant-scoped ledger through a pure `_evaluate_source_integrity` function and returns counts plus bounded samples. It is strictly read-only; findings must be corrected through the source module's reversal workflow, never by editing journals.
- Verification: `tests/test_accounting_source_integrity.py` (6 tests) covers clean ledgers, unbalanced/single-line journals, orphaned active vs reversed source journals, generic Money Out with no source record, broken reversal links, paid sources linked to reversed/missing journals, and proof that a non-admin finance reader is rejected with zero database access. Added to the CI gate.
- Next: once deployed, run against production as an admin and reconcile any findings record by record (no automatic repair). Not yet deployed.

### DS-071: Mutating-route authorization gate and CI coverage gap

- Audit: every FastAPI handler in `server.py` and `routes/*.py` was statically inventoried for permission/ownership guards (beyond the DS-058 authentication gate). No new same-tenant authorization gap was confirmed. Remaining unguarded authenticated routes are self-service (`/attendance/me/*`, `/attendance/my-salary`, notifications, preferences, PIN/password) or delegate to guarded resolvers (`_resolve_employee_id` ignores a client-supplied employee ID unless the caller can edit punches; `commissions_report_csv` delegates to the permission-checked report). Notification mutations use `notification_owner_filter`; master data, portal, AI history, chat and invoice-PDF share paths apply explicit `org_id`/owner filters on raw collections.
- Fix: `test_every_mutating_route_has_permission_or_ownership_guard` fails any new POST/PUT/PATCH/DELETE handler that authenticates without calling a permission, platform, employee-self-resolution or owner-filter guard, with a reviewed allowlist limited to login/session/PIN/password/preferences and the public share-token portal message. A negative check (removing an allowlist entry) proved the gate fails.
- CI gap: DS-070's own regression suite `test_vendor_payment_safety.py`, plus `test_download_safety.py` and `test_local_file_storage.py`, passed locally but were not in `.github/workflows/quality.yml`; all three are now mandatory.
- Verification: expanded mandatory backend list 286 passed; tracked-secret scan and diff check pass; frontend unchanged since the 05/11 baseline (ESLint 0 warnings, Vite build pass). Not yet deployed.

### DS-070: Source-backed vendor payment and commission receipt correction

- A Daybook/Ledger Edit action could patch a generated journal without updating
  its authoritative vendor payment or commission receipt. This created a real
  source-of-truth divergence risk, while the Vendor receipt/payment histories
  exposed reversal but no safe metadata correction.
- Authorized finance users can now edit bounded reference/notes on active vendor
  payments and commission receipts. Reference changes synchronize the linked
  journal under the same document lock and every correction is audited. Reversed
  records and records with missing journals fail closed.
- Daybook/Ledger routes source-backed Edit/Delete to the authoritative endpoint
  and no longer offer a generic direct reversal for source-generated journals.
  Amount/date/account/allocation changes still require balanced reversal and
  re-recording, preserving posted accounting history.
- Verification: 6 focused vendor regressions and the 268-test mandatory backend
  security/integrity suite pass. Full frontend ESLint, production build,
  tracked-secret scan and diff checks pass. Deployment remains blocked by SSH
  timing out before authentication.

### DS-067: Immutable salary-revision correction

- Effective-dated salary revisions were append-only with no way to correct the latest mistaken structure/date. Deleting or mutating the old row would destroy compensation history, while editing current employee salary alone would disconnect it from the revision trail.
- Payroll/finance-authorized users can now correct the latest active revision through a document lock. The original is retained and marked superseded; a replacement revision records the corrected structure and source ID, and current salary updates through the same atomic employee update. Historical payroll runs/payslips remain unchanged because they retain their existing snapshots. Older non-current revisions cannot overwrite current salary.
- Verification: 12 focused salary/payroll/employee regressions pass, including immutable supersession, current-salary synchronization, historical-revision rejection and permission denial before writes. Frontend ESLint and production build pass. Deployment remains pending stable VPS access.

### DS-066: Vendor and employee document metadata correction

- Vendor and employee documents were add/delete-only. Correcting a label, document type, expiry date or employee external URL required removing and recreating the record, risking lost context and unnecessary file churn.
- Vendor documents now support permission-checked in-place label/type/expiry correction without replacing stored file bytes. Employee external document records support label/URL correction through the existing safe external-URL validator. Updates target the exact nested document ID and emit audit events that exclude document URLs and file contents.
- Verification: 8 focused employee/vendor correction regressions pass, including nested-ID scoping, invalid date rejection, unauthorized zero-write behavior and audit metadata. Frontend ESLint and production build pass. Deployment remains pending stable VPS access.

### DS-065: Employee warning/reward correction lifecycle

- The Employee Performance screen supported creating warnings and rewards but exposed no correction path. Mistyped nonfinancial records were permanently visible even to authorized HR/Admin users, contrary to the correction behavior in other master-data modules.
- Authorized `employees.update` users can now edit or delete a specific nested warning/reward. Inputs are bounded and reject blank titles/reasons; every update/removal records a tenant-bound audit event containing only the employee and nested record IDs. UI actions are permission-aware and require confirmation before removal.
- Verification: 18 focused employee/financial-permission regressions pass, including nested-ID query scoping, audit creation and rejection before database access. Frontend ESLint and production build pass. Deployment remains pending stable VPS access.
- The persistent cross-module inventory is `docs/CORRECTION-CAPABILITY-MATRIX.md`; it distinguishes safe physical deletion, source correction and immutable financial reversal instead of promising destructive deletion for every record.

### DS-064: Session-expiry and multi-tab app-lock consistency

- A server-revoked or expired session could leave the current protected screen mounted until another navigation/auth refresh, producing repeated API failures and stale-looking UI. The five-minute PIN timer was also tab-local: an inactive background tab could lock every tab even while the user was actively working in another tab.
- Global 401 handling now invalidates local authenticated state immediately, causing protected routes to return to login after expiry, password reset, tenant suspension or explicit revocation. Login/logout state synchronizes across tabs. PIN activity is shared across same-origin tabs while the server remains authoritative through the existing touch/lock endpoints; manual lock still locks every tab.
- Verification: frontend ESLint passes with zero warnings and the production Vite build succeeds. Live multi-tab expiry/revocation validation remains pending deployment and stable VPS access.

### DS-063: API and notification failure-detail secret minimization

- The cross-tenant notification scheduler returned raw per-tenant exception messages in its operational result, and the multipart company-logo endpoint returned raw object-storage failures to authenticated clients. Provider/database errors can include credentials, internal endpoints, request details or tenant data.
- Scheduler results now expose only the bounded exception class. Logo-storage failures are logged by exception class and return a stable generic 503 message, matching the existing base64 logo upload path.
- Verification: focused regressions inject a private provider-detail marker and assert it cannot escape through scheduler results; source regression prevents reintroducing raw storage exception interpolation. Deployment remains pending stable VPS access.

### DS-061: Google Calendar retry-error secret minimization

- Calendar synchronization previously persisted raw external exception text in queue/connection `last_error` fields. OAuth and HTTP client messages can contain request URLs, provider response bodies, authorization codes or token fragments, bypassing log-only redaction because the value was stored in the database.
- Retry failures now persist only the bounded exception class and HTTP status code when available. Retry timing, attempt counts and operator-visible failure state remain intact without storing provider payloads or URLs.
- Verification: focused regression uses an exception containing a secret OAuth code/token and proves the stored summary contains only `HTTPStatusError (HTTP 401)`. Deployment remains pending stable VPS access.

### DS-062: Scheduled-job failure-state secret minimization

- The shared job runner persisted raw exception messages in `job_status.last_error`. Database/network exceptions can embed connection strings, credentials, request URLs or tenant data, so this bypassed log redaction and retained sensitive text in operational state.
- Job health now persists only the bounded exception class while retaining failure timestamps, attempt counts and consecutive-failure alerts. Logs already record the exception class only.
- Verification: focused regression supplies a private provider-detail marker and proves only `RuntimeError` is retained. Deployment remains pending stable VPS access.

### DS-059: Favorite-account financial permission isolation

- The standalone `finance_extras` router is mounted separately from the protected Accounting router. Its Favorite Accounts endpoints authenticated the caller but did not require `finance.read`, allowing an ordinary employee to probe an account ID and retrieve account master fields through a personal favorite list.
- List, add and remove favorite-account endpoints now reject callers without `finance.read` before any account or favorite-record lookup. Tenant scoping and per-user ownership remain unchanged.
- Verification: focused financial-read regressions prove all three unauthorized paths return 403 without database access. Deployment remains pending stable VPS access.

### DS-060: Vendor commission statement financial privacy

- Vendor Commission Statement PDF exposed earned, received and pending commission amounts to any role with `vendors.read`, while the Vendor Commissions screen and accounting APIs correctly require finance access.
- The PDF now requires both `vendors.read` and `finance.read`; a vendor-directory-only employee is rejected before vendor or commission data is queried.
- Verification: focused financial-read regression proves the non-finance path returns 403 with zero vendor-data access. Deployment remains pending stable VPS access.

### DS-058: Journal-detail defense-in-depth and route-authentication gate

- Accounting already enforces `finance.read` through a router-level dependency, so the direct journal-detail endpoint was not publicly exposed. The handler nevertheless lacked its own explicit check; it now authenticates and rejects non-finance roles before any journal lookup, preserving protection if route wiring is refactored later.
- Added a source-level regression inventory covering every FastAPI route in `server.py` and modular route files. A new endpoint fails the mandatory security suite unless it calls an approved authentication dependency or is deliberately added to the small reviewed public/delegating allowlist.
- Verification: 35 focused access, URL and financial-read tests pass, including proof that the handler itself performs zero database reads for an unauthorized caller. Deployment remains pending VPS SSH access.

### DS-057: Tenant-safe audit evidence export

- Tenant Admins can export up to 10,000 rows of their own tamper-evident audit chain as formula-safe CSV. Platform SuperAdmin export defaults to platform-only evidence and accepts one explicit tenant ID; an omitted selector never produces an accidental all-tenant dump.
- Export includes chain sequence/hash evidence, supports bounded date filters, rejects oversized exports, and appends an `audit.export` event without exposing password/session data. The existing Audit Log screen now offers a direct Export CSV action.
- Verification: focused audit-chain/export regressions and frontend lint/build pass. Automatic audit deletion was intentionally not added because deleting chained evidence would break integrity and requires an approved legal-retention policy. Deployment remains pending VPS SSH access.

### DS-055: Accounting navigation and vendor-action usability

- Accounting's fourteen sections no longer depend on an invisible single-line horizontal scroller. Desktop and laptop widths use a fully visible responsive grid with a clear active state; small screens use an accessible section selector. Existing accounting routes, calculations and forms are unchanged.
- The Vendor directory now exposes permission-aware Edit, Archive and Open actions on each row. Edit opens the existing vendor master form. Archive uses the existing backend lifecycle rule, preserving bills, payments and accounting history instead of hard-deleting financial records.
- Verification: frontend ESLint and production build pass. Production deployment and live responsive-width/role validation remain pending restored VPS access.

### DS-056: Configurable monthly paid-leave allowance

- Attendance Policy now includes a tenant-configurable monthly ordinary paid-leave allowance, defaulting to one day. Casual, sick and earned leave consume that allowance in date order; excess approved ordinary leave becomes salary loss-of-pay. Explicit unpaid leave remains deductible, while maternity, paternity and approved comp-off are not incorrectly consumed by this ordinary-leave cap.
- Payroll preview and paid-run breakdowns expose the allowance, allowance used and excess ordinary-leave days. Existing paid payroll runs and attendance records are not rewritten; the policy affects future previews/runs through the existing attendance-payroll source of truth.
- Verification: 32 focused attendance/payroll regressions pass, including one paid ordinary day, excess ordinary leave, explicit unpaid leave and statutory leave. Frontend ESLint and production build pass. Deployment and live payroll preview validation remain pending restored VPS access.

### DS-044: IST-safe business-date defaults

- Replaced UTC-derived or browser-local `today` defaults in accounting, attendance, payroll, employee onboarding/salary, tasks, loans, holidays, calendar, vendor entries, recurring expenses and account-ledger flows with the shared Asia/Kolkata calendar-date helper. Users working between midnight and 05:30 IST no longer receive the previous UTC date in forms, overdue checks, due-state calculations or the calendar's Today action.
- Financial-year and accounting period presets now derive the current calendar day in IST before calculating month, week, year and 1-April-to-31-March boundaries. Comments also use the shared DD/MM/YYYY formatter instead of a browser-locale-dependent date.
- Verification: full frontend ESLint and production Vite build pass. Native date input values and API/database storage remain ISO `YYYY-MM-DD`; user-facing business dates remain DD/MM/YYYY. Deployment and live midnight-boundary verification remain pending restored VPS access.

### DS-045: Project-detail task visibility parity

- The project-detail aggregator previously returned every task in a visible project whenever the caller had `tasks.read`, bypassing the task module's assigned/created/project visibility query. A limited employee could therefore receive unrelated task records through the nested project response.
- Project detail now combines the project ID with the shared task visibility query and returns no task data at all when `tasks.read` is absent. This preserves the existing administrator-wide view while keeping restricted employees on the same rules across task list, task detail, search, calendar and project detail.
- Verification: the focused access/URL safety suite passes 20 tests, including the new query-composition regression. Deployment and live custom-role validation remain pending restored VPS access.

### DS-046: Permission-aware dashboard aggregates

- `dashboard.read` previously exposed tenant-wide project/task counts, lead funnel/source statistics and employee task-load names even when the role lacked the corresponding project, task, CRM or employee permission. Assignment-restricted users also received counts derived from records they could not open.
- Dashboard project and task aggregates now reuse the shared assignment visibility queries and fail closed when their source permission is absent. Lead analytics require `leads.read`; named team utilization requires both `tasks.read` and `employees.read`. Financial cards retain their existing finance/invoice gates.
- Verification: 42 focused access, visibility, tenant-lookup and authentication tests pass, including fail-closed and assignment-scope dashboard regressions. Deployment and live custom-role validation remain pending restored VPS access.

### DS-047: Client, invoice and quotation audit coverage

- Added tamper-evident audit events for client creation/restoration, invoice creation, and advanced quotation creation, editing, deletion, status changes, internal approval decisions and version creation.
- Existing authorization, optimistic-concurrency checks and accounting posting behavior are unchanged; the new records capture actor, tenant, target and bounded metadata after each successful mutation.
- Verification: server compilation and 34 focused conversion/access tests pass. The complete mandatory suite passed 224 tests immediately before this audit-only batch. Deployment and production audit-chain verification remain pending restored VPS access.

### DS-048: Sensitive employee mutation audit coverage

- Salary revisions, private employee document addition/removal, warnings and rewards now emit tenant-bound tamper-evident audit events containing only record identifiers and safe operational metadata, not document URLs, notes, reasons or salary amounts.
- Employee document removal now fails with 404 when either the employee or document ID is absent instead of reporting a misleading success for a guessed/stale identifier.
- Verification: Python compilation, diff and tracked-secret gates pass. Deployment and production audit-chain verification remain pending restored VPS access.

### DS-049: Five-minute personal App PIN inactivity lock

- The mandatory per-user App PIN now locks after five minutes (300 seconds) without activity instead of one minute. Backend unlock leases and frontend idle detection use the same duration, while manual Lock now, cross-tab locking, five-attempt/15-minute protection and hashed PIN storage remain unchanged.
- All setup, lock-screen and security-dialog text now states five minutes. Existing users and PIN hashes require no migration.
- Verification: 14 focused PIN/session regressions pass; full frontend ESLint and production build pass. Deployment and live timing verification remain pending restored VPS access.

### DS-050: Connected salary payment and accounting correction

- Root causes: payroll payment UI did not send payment date, method or reference; backend journals used a hard-coded 28th date; method/account compatibility was not enforced; mistaken paid runs had no controlled correction; and Accounting Expenses exposed Employee Salary as a disconnected second payment path.
- Correction: payroll now records the selected payment date, Cash/Bank account, constrained payment method and reference in one payroll run and its linked balanced journal. Cash is limited to Cash/Petty Cash and non-cash methods require a configured bank account. Authorized payroll/finance users can reverse a paid run through an immutable balancing journal; retry recovery handles an already-created reversal and releases the period key so a corrected payment can be posted. Generic Employee Salary expenses are blocked and the UI directs users to Employee → Salary & Bank → Run Payroll, preserving one source of truth.
- Integrity: salary preview treats only active paid runs as already paid; reversal retains the original period key and linked journal IDs for audit, emits tenant-bound audit events, and never deletes historical journals or existing production records.
- Verification: 72 focused payroll, accounting, attendance and financial-permission regressions pass, including explicit payment metadata, invalid-method rejection and reversal/re-post eligibility. Frontend lint and the production build passed for the changed salary/payment UI; diff checks pass.
- Database effect: no migration or historical rewrite. New payroll fields are additive and reversal updates only the selected paid run while posting a balanced journal.
- Deployment: pending restored VPS access and the mandatory backup/service-specific release gate.

### DS-051: Vendor commission planning and receipt correction parity

- Root cause: the shared commission backend already supported planned receivables and safe receipt reversals, but the Vendor → Commissions screen exposed only receipt entry. Users could not create or edit the underlying expected commission there, so a direct ₹5,000 receipt appeared as unallocated while the table still said no commissions existed. Receipt method and account type could also disagree.
- Correction: Vendor → Commissions now creates and edits the same `vendor_commissions` records used by Accounting → Collections Due, including amount, due/reminder dates, project, recognition basis, reference and notes. Manual plans show contextual details and permission-aware Edit/Cancel actions. Posted receipts retain the existing Delete action, which creates a balanced reversal and rebuilds allocations rather than deleting accounting history. Cash receipts must use Cash/Petty Cash; UPI/bank/cheque/online/card/other methods require a configured bank account. Receipt dates and methods are schema constrained.
- Accounting policy: adding an expected commission creates no journal. Recording actual receipt posts one settlement/journal; direct excess receipts remain visible as unallocated advances instead of being double-counted as earned commission.
- Verification: 47 focused accounting, vendor-commission visibility and financial-permission regressions pass. Frontend ESLint and production build pass; diff checks pass.
- Database effect: no migration or historical rewrite. New plans and future corrections use the existing authoritative collections; posted receipt corrections remain reversal based.
- Deployment: pending restored VPS access and the mandatory backup/service-specific release gate.

### DS-052: Invoice Record Payment and reversible partial collections

- Root cause: Invoice status UI allowed a direct Paid selection that silently created a full receipt dated today through a default account. It did not capture the actual amount, Cash/Bank account, method or reference, so status could be mistaken for proof of payment and reproduce Cash/Bank mismatches. The invoice screen also offered edit/delete actions that the backend correctly rejected for partially paid records.
- Correction: Paid is now derived only from the authoritative Money In receipt workflow. Issued invoices expose Record Payment with amount, date, method, Cash/Bank account and reference; partial receipts set Partially Paid and full settlement sets Paid. Direct API creation/status transition to Paid is rejected with guidance to Record Payment. The latest linked payment can be deleted from the invoice screen by a balanced hidden-from-books reversal, which restores invoice outstanding/status through the existing source-sync engine. Draft invoice edit/delete controls now match backend lifecycle rules.
- Validation: Money In dates and methods are schema constrained. Cash receipts require Cash/Petty Cash; bank transfer, UPI, cheque, card, online and other non-cash methods require a configured bank account. The same rule applies to generic income, invoice/milestone collections and other receivables.
- Verification: 53 focused invoice, accounting, payroll, vendor-commission visibility and financial-permission regressions pass. Frontend ESLint and production build pass; diff checks pass.
- Database effect: no migration or historical rewrite. New receipts use existing journal/source records and corrections append balanced reversals.
- Deployment: pending restored VPS access and the mandatory backup/service-specific release gate.

### DS-053: Purchase-order GRN correction and 3-way-match recovery

- Root cause: PO cancellation instructed users to reverse Goods Receipts first, but no GRN reversal API or UI existed. A mistaken receipt therefore permanently inflated received quantities and GRN clearing, and blocked PO cancellation.
- Correction: authorized purchase/finance users can now reverse an active GRN from the PO detail screen. Reversal is blocked while an active linked vendor bill exists; users must cancel the bill first so clearing cannot be corrupted. The exact GRN journal receives a balanced hidden-from-books reversal, the GRN is retained with reversal metadata, and PO line receipts/status plus the 3-way match are rebuilt from active GRNs only. PO cancellation ignores already-reversed GRNs.
- Verification: 52 focused purchase-order, invoice, accounting and permission regressions pass, including the new linked-journal/PO-reconciliation reversal test. Frontend ESLint and production build pass; diff checks pass.
- Database effect: no migration or historical rewrite. Future GRN corrections add reversal metadata and one balanced journal.
- Deployment: pending restored VPS access and the mandatory backup/service-specific release gate.

### DS-054: Cash/Bank method consistency across Money In and Money Out

- Root cause: generic Accounting Income, Expense and Collections Due forms could select the first Cash/Bank account while retaining an incompatible default payment method. That allowed the UI to describe Bank Transfer while the journal affected Cash, or vice versa.
- Correction: choosing Cash/Petty Cash now selects Cash; choosing a configured bank selects Bank Transfer. Changing method selects a compatible account across Income, Expense and collection receipt forms. Backend schemas constrain dates and payment methods, and posting rejects Cash with a bank account or non-cash methods with Cash/Petty Cash. The rule now covers generic income/expense, invoice and milestone receipts, other receivables, vendor commissions and payroll.
- Verification: 50 focused accounting, payroll and financial-permission regressions pass; frontend ESLint and production build pass; diff checks pass.
- Database effect: none. Existing journals are unchanged; invalid future combinations fail before persistence.
- Deployment: pending restored VPS access and the mandatory backup/service-specific release gate.

### DS-043: Authentication, rate-limit and lifecycle hardening batch

- Rate-limit identity now prefers Nginx's overwritten `X-Real-IP` and otherwise uses the nearest forwarded hop, preventing a public client from bypassing login/search/upload limits with a forged first `X-Forwarded-For` value.
- Production login and Google OAuth responses are cookie-only by default. The raw bearer token is returned only outside production or when an operator explicitly enables the split-origin fallback; the HttpOnly/Secure/SameSite cookie remains authoritative.
- Direct frontend routes for CRM, projects, tasks, clients and quotations now require the same read permissions as their APIs. Users without access see a consistent 403 screen rather than loading a broken screen through a manually entered URL.
- Unconverted lead removal is now an audited archive; converted leads cannot be deleted because they are project provenance. Client hard-delete now checks projects, invoices, both quotation stores, journal entries and comments before allowing deletion. Comment deletion is soft, hidden from normal reads and audited.
- The unused legacy DayPicker component and its incompatible/unused `react-day-picker` and `date-fns` dependencies were removed. The current production Node dependency audit reports zero vulnerabilities.
- Verification: 221 mandatory backend security/integrity tests pass; full frontend ESLint and production build pass; tracked-secret and diff checks pass. Deployment and live role/login verification remain pending restored VPS access.

### DS-041: Permission-aware core business screens

- Clients, projects, leads, invoices, expenses, holidays and loans now hide creation or mutation controls when the signed-in role lacks the matching backend permission. Lead drag/drop, conversion and notes are protected separately; invoice status editing and loan EMI/prepayment controls no longer appear to read-only users.
- Existing backend authorization remains authoritative. This change removes misleading actions and repeated 403 failures without granting new access or changing production data.
- Verification: full frontend ESLint and the production Vite build pass. The release commit is pushed; deployment and live custom-role verification are pending restored VPS access.

### DS-042: Calendar and holiday permission revocation

- Calendar event update/delete now re-check `calendar.read` before ownership, so a user whose custom-role access is revoked cannot keep mutating previously created events through direct API calls.
- The holiday date probe now requires `holidays.read`, matching the main holiday calendar and preventing custom roles without holiday access from bypassing the route permission.
- Verification: 19 focused Calendar/Google Calendar/holiday permission tests pass. Deployment is pending restored VPS access.

### DS-038: Purchase-order correction and quotation permission controls

- Purchase orders now expose permission-aware create, edit, send, cancel and GRN controls. Draft line items can be corrected; after sending, only safe metadata remains editable, while received quantities and matched bills stay protected.
- Quotation create/delete/update/version/status/AI/conversion controls now follow the backend permissions. Invalid status actions are no longer offered, converted quotations remain read-only, and project conversion is shown only when the user also has project/task creation rights.
- Verification: focused frontend ESLint and production build pass. Deployment and live role verification are pending restored VPS access.

### DS-039: Ambiguous name-based task assignment privacy

- Legacy tasks that contain only an assignee display name now resolve that name only when it identifies exactly one active, approved user in the tenant. Duplicate names fail closed instead of exposing or notifying the wrong employee.
- The same rule protects task list/detail visibility, Assigned to me badges, overdue notifications, Google Calendar invitations and personal Google Calendar copies. New self-assigned employee tasks persist the immutable user ID so they do not depend on names.
- Verification: 47 focused task/calendar/notification/visibility tests pass, including a duplicate-name regression; Python compilation and diff checks pass. Deployment is pending restored VPS access.

### DS-040: Expense RBAC and legacy vendor-link isolation

- Expense policy, approver, list, detail, summary, create, edit and cancellation APIs now fail closed when a custom role lacks the relevant expense/finance permission. Claimant-only and routed-approver record visibility remains unchanged after the permission gate.
- Legacy task links by vendor display name are used only when the name identifies exactly one active vendor in the tenant. Duplicate vendor names can no longer contaminate another vendor's task history or performance metrics; ID-linked records remain authoritative.
- The RBAC role/permission catalogue now requires an explicit RBAC or user-management read permission instead of being visible to every authenticated account.
- Verification: 56 focused expense/vendor/RBAC/finance/security tests pass; Python compilation and diff checks pass. Deployment is pending restored VPS access.

### DS-037: Safe correction controls across vendor, expense and loan workflows

- Vendor bills expose metadata edit and draft-delete/posted-cancel controls; vendor payments and commission receipts expose balanced reversal controls; expected commissions can be cancelled. Vendor master records now expose Edit and audit-preserving Archive actions using the existing permission-checked APIs.
- Expense claims can be corrected before reimbursement and automatically restart approval. Claimants can withdraw their own unposted claims; managers can correct permitted claims; reimbursed claims require `finance.delete` and create a balanced hidden reversal before becoming cancelled.
- Loan records expose permitted non-financial metadata correction and safe archive. Financial terms remain immutable after posting, and EMI-day edits are validated to 1-31.
- Verification: 61 deterministic backend accounting/security tests pass; frontend ESLint and production build pass; tracked-secret scan and diff checks pass. The legacy Emergent preview loan suite remains external-only and unavailable because its preview TLS endpoint is retired.
- Deployment: pending restored Hostinger SSH or a fresh authenticated browser-terminal session.

### DS-034: Unified password policy and recoverable personal app lock

- Every tenant-owner, tenant-user and employee account creation/reset path now enforces the same 8-128 character letter-and-digit password policy on both API models and UI forms.
- Admin password inputs are masked and use new-password autocomplete semantics; the remaining six-character UI rules were removed.
- Privileged password recovery always revokes every user session, clears login lockouts and removes a forgotten app PIN. The reset is tenant-scoped and audited, and the user must sign in and configure a new PIN. Self-service password changes preserve the existing PIN.
- Local verification: 43 focused password/auth/tenant/PIN/release tests pass; Python compilation, frontend ESLint, production build and diff checks pass. A broader legacy run passed 212 tests; its remaining live-integration tests are not runnable locally because they depend on `/app/frontend/.env`, `REACT_APP_BACKEND_URL`, and an unavailable Emergent preview TLS endpoint.
- Deployment: pending stable Hostinger SSH or console access. Production remains unchanged.

### DS-035: Notification ownership after tenant reassignment

- Notification list, unread count, read, mark-all-read and dismiss operations now require both the authenticated `user_id` and effective `org_id`.
- Notification deduplication now includes `org_id`, so an old tenant's notification cannot suppress a valid notification after reassignment.
- This prevents notifications from a user's former company remaining visible or mutable after a Super Admin reassigns the user to another tenant. Legacy rows without tenant ownership fail closed.
- Local verification is covered by focused tenant-filter regression tests; deployment is pending stable VPS access.

### DS-036: Repeated backend 5xx monitoring

- The five-minute production monitor now counts backend HTTP 5xx responses from the previous five minutes and raises a deduplicated alert when the configurable threshold is reached.
- The default threshold is five responses and can be changed with `DESIGN_SAGA_MAX_BACKEND_5XX_COUNT`. Threshold validation and monitor wiring have regression coverage.
- Deployment and external alert delivery verification remain pending stable VPS access.

### DS-020: Posting recovery, attendance availability and milestone collection

- Accounting integrity: commission receipts now use stable request keys, allocate only earned commission to income, hold excess cash in `Commission Advances`, recalculate allocation totals after retries, and exclude reversed bill allocations. Loan creation, EMI and prepayment retries recover existing journals instead of posting duplicates.
- Payroll and receipts: interrupted payroll, invoice and milestone finalization recovers from the already-posted journal. Milestone collections can now be recorded directly from Collections Due with an explicit cash/bank and income account.
- Attendance: when tenant geofencing is disabled, unavailable browser GPS is optional instead of blocking every employee punch. Enabled geofencing remains mandatory and the existing supervisor all-active-project rule remains enforced server-side.
- Lifecycle and files: projects with tasks, events, project messages or comments must be archived rather than hard-deleted. Nginx now accepts the backend's 15 MiB file limit with multipart overhead.
- Local verification: 171 backend security/integrity tests, frontend lint, frontend production build, Python compilation and diff checks pass. Production deployment evidence is pending.
- Database effect: startup adds sparse unique request-key indexes and seeds the new liability account per tenant on normal account access. No historical journal or business row is rewritten.

## System Inventory

| Layer | Current implementation | Evidence/status |
|---|---|---|
| Frontend | React/CRA served by Nginx container | Confirmed from Dockerfile/package/docs; workflow coverage varies |
| Backend | FastAPI, mostly `backend/server.py` plus modular routes | Confirmed; production health passes |
| Database | PostgreSQL 17 + DocumentDB extension behind FerretDB Mongo protocol | Confirmed from Compose and running containers |
| Authentication | Password/Google-compatible session tokens in `user_sessions`; HTTP-only secure cookie or bearer token | Recent tenant-login repair verified live on 2026-10-01 |
| Tenancy | `org_id`, scoped DB wrapper, tenant filters, SuperAdmin exceptions | Strong prior evidence; requires continuing endpoint-by-endpoint audit |
| RBAC | Server-side role/permission expansion with tenant-specific overrides | Implemented; coverage audit ongoing |
| Background jobs | In-process notification due/overdue scheduler | Previously reported; runtime behavior not reverified in this pass |
| File storage | Tenant-scoped external links plus content-validated local binary storage on a dedicated persistent VPS mount | Implemented; deployment/live upload verification pending |
| Reverse proxy/TLS | Caddy with automatic HTTPS; shared VPS routing file | Healthy; production file has protected external edits |
| Deployment | Docker Compose; post-merge invokes tracked `deploy/update-production.sh` | Change-aware, backup-gated, health-checked, service-specific, and refuses automatic Compose/Caddy changes |
| Backups | Dedicated daily PostgreSQL/FerretDB and uploaded-file archive with checksums, catalogue validation, seven-day retention, and tested isolated database restore | Active on VPS; same-host storage remains a disaster-recovery limitation |

## Workflow Inventory

| Workflow | Status | Current evidence |
|---|---|---|
| Tenant owner/user login | Previously verified | Live synthetic owner and employee login by email/ID; bcrypt and isolation checks passed at `dbf6595` |
| Tenant isolation | Previously verified, audit continues | Prior two-tenant tests and live cross-tenant 404/RBAC 403 evidence |
| Attendance | Focused critical-path verification complete | Identity, IST date, punch idempotency, authorized-site behavior, review concurrency, leave preservation, correction consistency, and payroll blocking verified |
| Leads → quotations/BOQ → projects | Partial | Implemented and prior module tests exist; full current conversion chain unverified |
| Projects → tasks/assignments | Previously tested, needs currency check | Historical task visibility and assignment evidence exists |
| Vendors/procurement | Partial | Vendor, PO and accounting tests exist; current end-to-end flow unverified |
| Invoices/receipts/accounting | Focused critical-path verification complete | Payment permissions, exact settlement, idempotency, reversals, source deletion, account types, journal balance, and dashboard netting verified |
| Payroll/expenses | Payroll critical path verified; expenses partial | Concurrent payroll posting, account types, unresolved-review blocking, permissions, and journal cardinality verified with synthetic data |
| Notifications/calendar | Previously tested | Historical iteration evidence; scheduler runtime not reverified |
| Files/documents/exports | Unverified | Access control, persistence, and cross-tenant guessing audit pending |

## Reused Evidence

- `dbf6595`: tenant login supports email, employee ID formats, and internal user ID; live synthetic owner/user tests passed and temporary data was purged.
- `f02246e`: production session cookies default to secure.
- PRD and prior reports document P0 tenant-isolation repairs, accounting posting/reversal, suspension enforcement, plan limits, employee-login linking, and notification tenant stamping.
- `plan.md` documents completed attendance, project-finance visibility, salary-history, calendar privacy/reminders, and employee-account work.
- Reuse is provisional where only narrative evidence exists; run the smallest current verification before relying on it for a new repair.

## Prioritized Issue Queue

| ID | Priority | Issue / verification target | State |
|---|---|---|---|
| DS-001 | High | Server-side invoice/dashboard financial-read authorization bypass | Fixed, deployed, and verified live |
| DS-002 | High | Verify attendance identity, idempotency, timezone boundary, approval audit, and payroll consistency end to end | Fixed, deployed, and verified live |
| DS-003 | High | Establish a validated backup and restore path for Design Saga PostgreSQL/FerretDB data and deployment state | Fixed and active with repeatable restore drill and recovery runbook; offsite copy remains a follow-up |
| DS-004 | High | Reconcile dashboard revenue/outstanding figures with journal/invoice sources and permission boundaries | Fixed, deployed, and verified live |
| DS-005 | High | Audit project/task/file authorization and unsafe attachment URLs | Fixed, deployed, and verified live |
| DS-006 | High | Prevent cross-tenant account reset and tenant-to-SuperAdmin escalation | Fixed, deployed, and verified live |
| DS-007 | High | Replace unsafe blanket Git redeploy hook with change-aware deployment | Fixed, installed, and verified live |
| DS-008 | Medium | Measure endpoint/page performance and inspect indexes/N+1/pagination before optimizing | In progress: route-level code splitting reduces the initial JS bundle from 1.52 MB to 495 KB (372 KB to 149 KB gzip); API latency, index and large-data traces remain |
| DS-009 | High | Employee/payroll endpoints expose compensation, bank, and private HR data through broad employee-read permission | Fixed, deployed, and verified live |
| DS-010 | High | Prevent password-login identifier spraying from one network source | Fixed, deployed, and verified live |
| DS-011 | High | Rejected punch retry, late-review races, manual-time integrity, weekly offs, and overlapping leave | Fixed, deployed, and verified live |
| DS-012 | High | Empty role overrides restored default privileges; legacy session routes missed tenant lifecycle gates | Fixed, deployed, and verified live |
| DS-013 | High | Search, comments, calendar, and event notifications bypassed primary visibility boundaries | Fixed, deployed, and verified live |
| DS-014 | High | Repair-branch scheduler, audit-chain, business-date, idempotency, numbering, and workflow integrity gaps | Fixed, deployed, and verified live |
| DS-015 | Medium | Central project milestone collections/receivables view | Deployed; four pending Design Saga milestones confirmed in the production data audit |
| DS-018 | High | Accounting posting, ledger, GST and bank-reconciliation integrity controls | Deployed; focused regression suite and production health checks pass |
| DS-019 | High | Vendor bill, Accounts Payable, advance-payment and three-way-match integrity | Deployed; sample vendor balance and project-linked draft bill verified live |
| DS-020 | High | All-time accounting ranges and safe reversal undo | Deployed; exact historical correction remains record-specific and evidence-gated |
| DS-021 | High | Capital, investment and person-wise receivable/payable workflows | Deployed and verified live with fully reversed sample-tenant journals |
| DS-022 | Medium | Chart of Accounts current balances, editing, deactivation and future duplicate-code prevention | Deployed and verified; scoped duplicate-code cleanup completed after backup |
| DS-023 | High | Invoice accrual, Accounts Receivable settlement and revenue/GST recognition | Fixed, deployed and verified live with a fully reversed sample-invoice lifecycle |
| DS-024 | Medium | Private notification controls, complete search, tenant audit UI and cash-flow activity split | Fixed, regression-tested and deployed; cash-flow totals retain backward-compatible fields |
| DS-025 | Medium | Durable project/vendor document uploads with tenant authorization, validation and backup | Implemented and regression-tested; production deployment/live verification pending |
| DS-026 | High | Quotation conversion bypasses client/project/task create permissions | Fixed, covered by conversion/concurrency regressions, deployed and verified healthy at `fbbd7da` |
| DS-027 | High | Vendor permissions and broad tenant reads exposed purchase orders/GRNs outside visible projects; project invoice access exposed vendor bills/costs | Fixed, covered by permission and project-finance regressions, deployed and verified healthy at `949c372` |
| DS-028 | Medium | Production updater could repeat the same successful release because `ORIG_HEAD` was not advanced | Fixed and installed at `81b06f3`; replay now exits without backup, rebuild or restart |
| DS-029 | High | Lead conversion allowed a lead editor to create a client and project without their create permissions | Fixed, regression-tested and deployed at `3b95ca1` |
| DS-030 | High | Direct vendor commission receipts posted valid journals but disappeared from commission ledgers/dashboards when no bill earning was allocated | Fixed and deployed at `3b95ca1`; live ₹21,000 across three receipts reconciles between the vendor ledger and dashboard |
| DS-031 | Low | Operational screens displayed inconsistent raw ISO dates | Fixed across accounting, milestones, projects, attendance, clients, vendors, invoices, expenses, POs, loans, tasks, employee/RBAC, portal and platform surfaces with the shared DD/MM/YYYY formatter; timestamp boundaries are rendered in IST and pure calendar dates remain stable; deployed and live-verified at `8e1ec41` |
| DS-032 | High | Production monitor omitted memory/load/database-capacity and TLS-expiry checks | Fixed and active at `8669d1d`; the five-minute monitor now validates all four thresholds in addition to service, site, disk and backup health |
| DS-033 | High | Long-running Caddy container retained a stale DNS upstream and could not reach the ACME renewal service | Corrected in production by a scoped Caddy restart; IPv6 DNS and ACME directory connectivity pass, certificate remains valid through 29/12/2026, and TLS-expiry monitoring is active |
| DS-034 | High | Password rules differed by account-creation path and admin reset could leave a user trapped behind a forgotten app PIN | Fixed and regression-tested locally; pushed repair deployment pending stable VPS access |
| DS-035 | High | Reassigned users could retain notifications from their previous tenant because personal notification queries omitted `org_id` | Fixed and regression-tested locally; deployment pending stable VPS access |
| DS-036 | High | Production monitor did not detect repeated backend HTTP 5xx responses | Fixed and regression-tested locally; deployment pending stable VPS access |

## User-Reported Master Backlog - 2026-10-23

This is the canonical intake list supplied after the repair-release deployment. Statuses below are based on current-code inspection; production-data items remain open until the exact tenant records are reconciled. "Implemented" does not mean historical production data was rewritten.

| ID | Sev | Reported issue | Reconciled state |
|---|---|---|---|
| BR-001 | High | Invoice payment cannot be recorded / draft invoice stuck | Verified live on sample `INV-1001`: paid posting and reversal succeeded, then the invoice was restored to draft with no active receipt journal |
| BR-002 | High | PO/bill cannot link to project | API/UI support is deployed; a temporary project-linked sample bill was created and deleted live without a journal |
| BR-003 | High | Collections Due empty | Deployed; production audit found four pending Design Saga milestones, all linked to projects |
| BR-004 | High | Vendor ledger shows wrong balance | Verified live: sample vendor summary and full ledger both return ₹29,500 |
| BR-005 | High | AR and client receivables not reflected | Fixed and verified live: issue posted ₹59,000 A/R against ₹50,000 revenue + ₹9,000 GST; payment settled A/R, and the full rollback returned every tested balance to baseline |
| BR-006 | High | Attendance check-in and employee-login link broken | Fixed and deployed; attendance identity/project access/idempotency covered by current tests |
| BR-007 | High | Notifications and settings unavailable | Fixed and deployed: each user controls task, finance, attendance and calendar alerts; mandatory account notices remain enabled and preferences are tenant/user scoped |
| BR-008 | Medium | Chart of Accounts balances show zero/opening only | Fixed and verified live: all listed accounts include journal-derived current balances |
| BR-009 | Medium | Duplicate account codes | Future duplicates are rejected; exact unused live duplicates were safely deactivated/re-coded and both affected audit chains pass |
| BR-010 | Medium | Inconsistent monthly balances | Requires exact screen/period data trace after DS-022 current-balance correction |
| BR-011 | Medium | Tasks without due dates marked overdue | Current dashboard and scheduler explicitly require a due date; retain as regression coverage |
| BR-012 | Medium | Preview broken | Needs workflow-specific reproduction; invoice PDF and document preview must be assessed separately |
| BR-013 | Medium | Expense invalid URL | URL handling/security correction is present; production reproduction still useful for affected legacy record |
| BR-014 | Medium | Invoice sending not implemented | Confirmed gap: status/PDF exist, outbound email delivery does not |
| BR-015 | Medium | Invoice payment link/UPI missing | Confirmed product gap; requires payment-provider/security design, not a hard-coded link |
| BR-016 | Medium | GST incomplete | Partial: input/output posting exists; tenant GST settings, split GST and GSTR reports remain |
| BR-017 | Medium | Tally export missing | Confirmed export gap |
| BR-018 | Medium | AI assistant not functional | Requires provider/config/runtime audit; not an accounting source of truth |
| BR-019 | Medium | File upload unavailable | Fixed in code: project/vendor UI uploads to tenant-isolated persistent storage with permission checks, verified file signatures, 15 MB limits, safe delivery/deletion and backup inclusion; production verification pending |
| BR-020 | Medium | Client portal link missing | Explicit share-token/link UI is implemented and deployed |
| BR-021 | Medium | Search misses quotations/events | Fixed and deployed: advanced quotations and privacy-filtered calendar events are included in global search |
| BR-022 | Medium | Slow page loading | Frontend route splitting implemented and smoke-tested across dashboard, accounting, attendance, calendar, audit and privacy; API tracing/pagination remains under DS-008 |
| BR-023 | Medium | Cash-flow split missing | Fixed: report and CSV now split operating/investing/financing activities and reconcile every cash/bank account while preserving existing totals |
| BR-024 | Medium | Draft invoice counts inconsistent | Not reproducible in the 24/10 production trace: the sole current invoice is one explicit sample-tenant draft and all active invoice queries count it consistently; monitor as data grows |
| BR-025 | Low | Date formats inconsistent | Fixed and deployed at `c89907d`: major ERP display surfaces consistently use DD/MM/YYYY while browser form controls and database/API values correctly retain ISO storage |
| BR-026 | Low | New-tenant PO dead-end | Send/GRN paths exist; empty master-data onboarding needs live workflow verification |
| BR-027 | Low | Bill creation location confusing | UX review item; preserve vendor and PO context while improving discoverability |
| BR-028 | Low | Unsafe automatic matching by name | Fixed for task/user and vendor legacy fallbacks: name-only links resolve only when unique within the active tenant; new self-assignments persist IDs. Deployment pending |
| BR-029 | Low | Large flat dropdowns | Confirmed usability gap; replace only high-volume selectors with searchable controls |
| BR-030 | Low | System account codes missing | Current defaults have codes; audit legacy/generated accounts and fill only unambiguous gaps |
| BR-031 | Low | Account edit/deactivate missing | Fixed and deployed through the Chart of Accounts UI with non-destructive deactivation/restore |
| BR-032 | Low | Gujarati text in English UI | Confirmed one Collections heading; removed under DS-022 while retaining English accounting terminology |
| BR-033 | Low | Demo data unclean | Sample tenant only; clean via backup and explicit scoped scripts, never production tenants |
| BR-034 | Low | Backup missing | Fixed: checksummed daily database/deployment backup and restore validation active on VPS; offsite copy remains |
| BR-035 | Low | Help and audit-log screens missing | Tenant-admin audit screen and integrity verification are deployed; a generic help manual remains a product-content decision, not a production defect |

### Accounting workflow extension (DS-021/DS-022)

- Reuse the existing journal, ledger, tenant scope, RBAC, reversal and audit mechanisms.
- Add simple balance-sheet workflows for owner capital, owner drawings, gold purchase, money given, money received and repayments.
- Person-wise balances use separate `Advance to - <name>` asset or `Loan from - <name>` liability accounts. Repayments cannot exceed the ledger outstanding amount.
- Do not classify capital, investments, loans or advances as business income/expense.
- Do not add gold sale/profit valuation until cost-basis and gain/loss treatment are explicitly designed and reviewed with the accountant.
- Show derived current balance in Chart of Accounts, while preserving opening balance as accounting input.
- Expose existing edit/deactivate/restore controls; posted account type/opening balance remain locked by the backend.

## Issue Log

### DS-020: All-time accounting and reversal correction

- Root causes:
  - Selecting `All time` sent no period parameter, while report and journal APIs interpret an omitted period as the current Indian financial year. Daybook and account-ledger presets had the same ambiguity.
  - Income/Expense history used the legacy unpaginated journal response and silently showed only the newest 200 rows.
  - Reversal entries were intentionally immutable but had no safe way to correct an accidental reversal.
- Correction:
  - Add an explicit `fy=all` contract that resolves to an unbounded date range, use it across reports, exports, Daybook, account ledgers, Income, and Expense, and show the selected report label.
  - Make Income/Expense history server-filtered and paginated, include reversal/reinstatement records, and open the shared transaction detail view.
  - Add `Undo reversal` for direct manual/income/expense entries. It posts an idempotent reinstatement journal, retains the original reversal and audit event, heals interrupted retries, and does not support source-driven invoice/milestone/payroll/vendor entries whose business document must be restored through its own workflow.
- Verification: Python compilation, period-contract assertion, `git diff --check`, frontend ESLint, and Vite production build pass. A pinned local backend environment additionally passed 57 focused accounting, vendor-payment, URL/download safety, RBAC/session, attendance, and Google Calendar tests. The build retains the existing large-chunk warning; FastAPI reports only its existing lifespan deprecation warnings.
- Production status: not deployed. The named ₹10,000 Ritesh Soni reversal has not been changed because the exact tenant, original journal, reversal journal, and linked source cannot be safely inspected while SSH/public access is unavailable.
- Database effect after deployment: no migration or automatic rewrite. Using Undo reversal adds one balanced reinstatement journal and audit record; it never deletes posted accounting evidence.

### DS-019: Vendor bills, A/P and three-way matching

- Root causes:
  - Received vendor bills updated the vendor UI but posted no journal, while vendor payments debited Accounts Payable. A/P could therefore become negative without a booked liability.
  - Bill schemas could not carry a purchase-order or PO-line link, while the three-way matcher queried those links and obsolete `lines`/`amount` fields. The advertised PO/GRN/bill comparison could not succeed.
  - Unallocated vendor payments also debited A/P instead of a vendor-advance asset.
  - Posted bills could be financially edited or hard-deleted, and paid bills could be cancelled without first reversing their payments.
  - Draft bills leaked into billed/performance/commission totals, reversed payments inflated the vendor summary, and filtered vendor ledgers lost their pre-period opening balance.
- Correction:
  - New received non-PO bills post DR expense + DR Input GST / CR Accounts Payable + CR TDS Payable. The UI requires an explicit expense account; legacy API clients fall back to `Miscellaneous Expenses` with an `accounting_warning` marker.
  - New PO bills carry `po_id`/`po_line_id`, verify the vendor and received quantities, and post DR GRN Clearing + DR Input GST / CR Accounts Payable + CR TDS Payable. The existing three-way report now reads `items` and `total` and excludes draft/cancelled bills.
  - Allocated payments debit A/P; excess/on-account amounts debit the new `Vendor Advances` asset; both use the central journal validator and a linked source ID.
  - Vendor bill and payment creation use idempotency keys. Posted financials require reversal; paid bills cannot be cancelled until linked payments are reversed; cancellation posts an idempotent bill reversal and preserves/corrects commission audit state.
  - Drafts are excluded from billed, ledger, performance, and commission figures; reversed payments are excluded from paid summaries; date-filtered vendor ledgers carry the correct opening balance.
  - The vendor bill form can select a purchase order and prefill linked PO lines, or select an expense account for a non-PO bill. Failed API calls remain visible with an error instead of closing the form.
- Files changed: `backend/core/indexes.py`, `backend/models/accounting.py`, `backend/models/vendor.py`, `backend/routes/purchase.py`, `backend/routes/vendors.py`, vendor/purchase/accounting regression tests, and `frontend/src/pages/VendorDetail.jsx`.
- Verification: Python compilation and `git diff --check` pass; frontend ESLint and Vite production build pass; 20 focused accounting/vendor-payment/purchase/release tests pass locally.
- Database effect: startup/account seeding adds the zero-balance `Vendor Advances` asset when missing and adds non-destructive vendor-bill PO/idempotency indexes. No historical bill or journal is rewritten automatically.
- Production gate: audit historical non-draft vendor bills for missing `journal_entry_id`, compare bill totals to existing payment/AP activity, back up the database, and run an explicit reviewed backfill only where evidence is unambiguous.

### DS-018: Accounting integrity controls

- Root causes:
  - Journal posting accepted malformed dates, blank narrations, inactive accounts, non-finite/negative values, and lines containing both or neither debit and credit.
  - Posted standalone journals could be amount/date edited or hard-deleted, bypassing a durable correction trail.
  - A date-filtered account ledger started from the static account opening balance and omitted every movement before the selected range; large ledgers were silently cut at 2,000 entries.
  - Expense and recurring-expense input GST debited the `GST Payable` liability instead of an input-tax asset.
  - Manual bank matching did not verify account, direction, amount, date proximity, reversal state, or duplicate use; unmatched rows could be marked reconciled.
  - Recurring-expense journal idempotency keyed only by rule, so a later period could conflict with the first successful posting.
  - Balance-sheet reconcile directly mutated an equity opening balance, hiding the source of an imbalance.
- Correction:
  - Validate journal dates, narration, line cardinality, finite non-negative values, exactly-one-side debit/credit, balance, and active same-tenant accounts.
  - Require reversal for posted date/amount corrections and disable physical journal deletion in API/UI; descriptive metadata remains auditable and editable.
  - Carry pre-period movements into filtered ledger opening balances and fail explicitly above 10,000 rows instead of silently truncating.
  - Seed and use `Input GST Credit` as an asset for new expense input-tax postings. Historical GST rows are not rewritten automatically.
  - Require a unique, unreversed journal with the same bank account, signed direction, exact paise amount, and a three-day date window before match/reconcile; audit both actions.
  - Key recurring postings by rule and run date, and tighten automatic bank matching to one paisa.
  - Disable automatic balance-sheet opening-balance mutation and direct users to diagnose and reverse the actual bad entry.
  - Lock account type and opening balance after journal activity; reject duplicate account names and audit account updates.
- Files changed: `backend/core/finance.py`, `backend/models/accounting.py`, `backend/routes/accounting.py`, `backend/routes/finance_extras.py`, `backend/tests/test_accounting_safety.py`, `frontend/src/components/TransactionDetail.jsx`, `frontend/src/pages/Accounting.jsx`.
- Verification: Python compilation and `git diff --check` pass; frontend ESLint and Vite production build pass; the focused accounting/vendor-payment/purchase/release suite passes 20/20 locally. Container integration and production data audits remain required before deployment.
- Database effect: startup/account-list seeding adds one zero-balance asset account (`Input GST Credit`) per tenant when missing. No existing journal, opening balance, or business record is rewritten.
- Deployment: pending VPS access, verified backup, disposable integration test, and service-specific health checks.

### DS-015: Central project collections due (ઉઘરાણી)

- Existing behavior: payment milestones can already be created and paid inside each individual project, and Accounting shows only the first eight milestones due in the next 30 days.
- Gap: there was no tenant-wide view for accountants to see total pending, overdue, next-30-day, later, and undated project collections with project/client context.
- Correction: added a tenant-scoped read endpoint over existing payment milestones, project/client enrichment, outstanding-amount calculation, due buckets, an indexed query path, search/filter controls, DD/MM/YYYY rendering, and direct navigation to the original project. No second payment or accounting engine was introduced.
- Files changed: `backend/routes/accounting.py`, `backend/core/indexes.py`, `backend/tests/test_accounting_safety.py`, `frontend/src/pages/Accounting.jsx`.
- Verification: backend modules compile; frontend ESLint passes; Vite production build passes. The focused pytest file could not run locally because this Windows Python installation does not include pytest. No production data was read or changed.
- Deployment: pending. `gamaa.in:443` and `187.52.124.46:22` timed out on 2026-10-20, so backup, service deployment, and live verification were not attempted.
- Rollback: revert the DS-015 commit and redeploy backend/web. The added non-unique milestone index is backward-compatible and may remain. No data migration or rewrite is involved.

### DS-001: Server-side financial read authorization

- Symptom/risk: an authenticated user without `invoices.read` or `finance.read` can call invoice list/detail/PDF APIs directly. `/dashboard/stats` also calculates and returns tenant revenue and collection totals to every authenticated user. Navigation hiding is not an authorization boundary.
- Severity: High. Tenant scoping prevents cross-tenant reads, but restricted users can read sensitive financial data from their own tenant.
- Evidence collected:
  - `GET /invoices`, `GET /invoices/{id}`, and authenticated `GET /invoices/{id}/pdf` only called authentication helpers before the repair.
  - `/dashboard/stats` exposed journal-derived revenue and invoice-derived collections without financial permission checks.
  - The accounting router is protected by a router-level `finance.read` dependency and is not affected by this finding.
- Root cause: incomplete server-side authorization on monolithic invoice/dashboard handlers; the frontend sidebar was incorrectly relied on to hide access.
- Local correction:
  - Enforce `invoices.read` or `finance.read` for invoice list/detail/authenticated PDF reads.
  - Keep unauthenticated project share-token PDFs working through the existing token validation path.
  - Require `dashboard.read`; query and return revenue only for `finance.read`, and collections only for `invoices.read` or `finance.read`.
  - Hide unauthorized dashboard finance cards and protect the `/invoices` frontend route.
- Files changed: `backend/server.py`, `backend/tests/test_financial_read_permissions.py`, `frontend/src/App.js`, `frontend/src/pages/Dashboard.jsx`.
- Pre-fix isolated reproduction against the production backend image and a disposable database:
  - Restricted Employee received HTTP 200 from invoice list, invoice detail, and authenticated invoice PDF endpoints.
  - Restricted Employee dashboard exposed revenue `54321` and collections due `12345` from synthetic records.
  - Cross-tenant invoice detail returned 404, confirming tenant scoping remained intact while role authorization was missing.
- Post-fix isolated integration results against candidate commit `1a1903c`:
  - Restricted Employee received 403 from invoice list, detail, and authenticated PDF; dashboard omitted revenue, collection totals, and collection alerts.
  - Project Manager retained same-tenant invoice/collection visibility, did not receive revenue, and received 404 for another tenant's invoice.
  - Accountant retained revenue, collection, and authenticated PDF access.
  - A valid unauthenticated project share token still returned its invoice PDF with HTTP 200.
  - Focused permission-helper assertions passed.
  - Candidate backend and frontend Docker images both built successfully. The frontend build completed with existing dependency/hook warnings and no errors.
- Cleanup verification: the disposable database, candidate containers/images, temporary worktree, repair ref, and transfer bundle were removed after testing.
- Production deployment:
  - Captured a 22 MB custom-format PostgreSQL backup, globals, environment/Caddy snapshots, commit/image metadata, and checksums before deployment.
  - Tagged the prior backend and web images as `rollback-dbf6595`.
  - Deployed backend and web only; PostgreSQL, FerretDB, and Caddy were not restarted.
  - Both new containers became healthy; site and API returned HTTP 200, protected unauthenticated endpoints returned 401, runtime permission assertions passed, and recent logs contained no critical errors.
- Current state: deployed at `1a1903c` within production checkpoint `a659939` and verified live.
- Rollback: revert the DS-001 commit. No database migration or data rewrite is involved.

### DS-003: Dedicated Design Saga backup and restore path

- Symptom/risk: Design Saga had no confirmed scheduled backup. Existing encrypted ERP timers pull Gamma and jewellery ERP payloads from another VPS; their manifests do not include this VPS's Design Saga PostgreSQL volume.
- Severity: High. A host or volume failure could otherwise make current Design Saga data unrecoverable.
- Root cause: Design Saga was deployed after the independent cross-server backup workflow and was never added to a dedicated backup schedule.
- Correction:
  - Added `deploy/backup.sh` with a non-overlapping lock, root-only permissions, atomic publication, custom PostgreSQL dump, role dump, Caddy/environment/Git/image metadata, archive listing validation, SHA-256 checksums, and seven-day retention.
  - Added a hardened systemd oneshot service and daily persistent timer. It runs at 18:22 UTC with randomized delay and does not stop or write to application services.
- Verification:
  - Shell syntax and systemd unit validation passed.
  - Manual systemd execution created `/opt/design-saga-backups/20261012T092326Z`; all checksums and the `pg_restore` catalogue validation passed.
  - Restored that archive into a memory-limited temporary DocumentDB/PostgreSQL container using a filtered restore list for the two image-preseeded `pg_cron` rows. Restore completed with 76 non-system tables and 535 document rows.
  - The restore container and temporary list were removed. `design-saga-backup.timer` is enabled and active; its next run was scheduled for 2026-10-12 18:22 UTC.
- Files changed: `deploy/backup.sh`, `deploy/systemd/design-saga-backup.service`, `deploy/systemd/design-saga-backup.timer`.
- Current state: deployed at `1bafdea` and verified. No application/database restart or data mutation was required.
- Limitation: dedicated archives currently remain on the same VPS. Configure an independently controlled offsite destination before treating this as host-loss disaster recovery.
- Rollback: disable/remove `design-saga-backup.timer` and its two units, then revert `1bafdea`. Existing archives can remain for recovery or be removed separately after explicit approval.

#### 2026-10-24 recovery revalidation

- Added `deploy/restore-drill.sh`, which accepts only a timestamped archive directly under the configured backup root, verifies database and uploaded-file checksums, restores into a memory/CPU-limited container with no published ports, compares non-system table and DocumentDB row counts with production, and always removes its temporary container and volume.
- Backup `/opt/design-saga-backups/20261024T062601Z` passed the drill: 106 non-system tables and 1,015 document rows matched production; database restore completed in 2 seconds.
- Added `docs/runbooks/DISASTER-RECOVERY.md` with the initial 24-hour engineering RPO, 8-hour engineering RTO, restore validation sequence, and explicit provider-loss limitation. Encrypted off-server replication still requires a destination and credentials.

### DS-002A: Attendance identity, punch idempotency, and business date

- Symptom/risk:
  - Check-in, check-out, leave creation, and leave-balance endpoints trusted a client-supplied `employee_id`. A regular employee could act for a coworker in the same tenant.
  - A regular employee could list tenant-wide leave requests when `mine=true` was omitted.
  - Attendance day/month defaults used UTC, producing the previous business date between midnight and 05:29 IST.
  - Check-in used a read-then-insert flow with a non-unique employee/date index, allowing concurrent requests to create duplicates.
- Severity: High. This enabled within-tenant attendance/leave impersonation and could corrupt payroll inputs.
- Production precondition audit: 33 attendance rows, zero duplicate `(org_id, employee_id, date)` groups, and zero rows missing `org_id`. An isolated FerretDB probe confirmed a unique index can coexist with the legacy index.
- Pre-fix isolated reproduction against rollback image `dbf6595`:
  - Employee check-in for a coworker returned 200.
  - Employee leave creation for a coworker returned 200.
  - Employee tenant-wide leave listing exposed the coworker's row.
  - Employee coworker leave-balance request returned 200.
- Correction:
  - Resolve self-service attendance identity from the authenticated employee link; only attendance managers may target another employee.
  - Enforce the same self-only boundary for leave lists and leave balances.
  - Use the shared IST clock for attendance dates and default reporting periods.
  - Add a unique `(org_id, employee_id, date)` index, atomic conditional punch updates, and duplicate-key handling.
- Isolated post-fix verification:
  - Coworker check-in, leave creation, and leave balance returned 403; own leave/list/balance paths remained available.
  - Admin delegated attendance remained available.
  - Eight concurrent check-ins produced one HTTP 200, seven HTTP 400 responses, and exactly one stored attendance row.
  - Eight concurrent check-outs produced one HTTP 200 and seven HTTP 400 responses.
  - Unique-index and IST midnight-boundary assertions passed. The disposable database and containers were deleted.
- Production deployment:
  - Created and verified pre-deploy backup `/opt/design-saga-backups/20261012T093311Z`.
  - Deployed the already-tested backend image only; web, PostgreSQL, FerretDB, and Caddy were not restarted.
  - Backend became healthy; site/API returned HTTP 200; production unique index is active; duplicate groups remain zero; recent backend logs contain no critical errors.
- Files changed: `backend/routes/attendance.py`, `backend/core/indexes.py`, `backend/tests/test_attendance_safety.py`.
- Current state: deployed at `c836807` and verified live.
- Rollback: retag `design-saga-backend:rollback-a659939`, recreate only the backend service, and revert `c836807`. The added unique index is compatible with the prior code and need not be removed during an emergency rollback.

### DS-002B: Approval atomicity and attendance-to-payroll integrity

- Symptom/risk:
  - Attendance, leave, and correction reviews used read-then-write transitions, so concurrent reviewers could both succeed or overwrite each other.
  - Leave approval could overwrite an existing worked/punched attendance day with `leave`.
  - Correction review completed the request before safely applying attendance and accepted invalid, cross-day, or reversed timestamps.
  - Concurrent salary submissions could post duplicate journals/runs, and payroll could proceed while attendance, leave, or correction reviews were unresolved.
- Production precondition audit: no pending attendance/late/correction/leave reviews, no leave rows with a real punch, no duplicate payroll period groups, and no existing payroll runs requiring repair.
- Correction:
  - Added atomic review claims and conditional updates for attendance, leave, and correction decisions, with stale-claim recovery and audit preservation.
  - Leave approval now fills only absent/missing/leave days and never overwrites a real punch, worked day, or holiday.
  - Correction requests require valid ISO timestamps on the requested IST business date with checkout after check-in; review applies attendance before finalizing approval.
  - Added a unique sparse `(org_id, period_key)` payroll index and a processing reservation before journal posting.
  - Payroll now blocks unresolved attendance/late/leave/correction reviews and validates expense and cash/bank account types.
- Verification:
  - 17 focused backend tests passed.
  - Candidate backend/frontend images built successfully; frontend emitted only the existing hook warnings.
  - Disposable FerretDB/PostgreSQL integration: six concurrent attendance approvals and four concurrent leave approvals each produced exactly one winner; a worked punch was preserved; one missing leave day was created; correction conflicts remained coherent; eight concurrent salary submissions created exactly one payroll run and one journal; pending correction blocked payment.
  - Temporary QA containers/database were deleted; no production business rows were written.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261012T141305Z` and tagged prior images `rollback-c4df434`.
  - Deployed backend/web at `bbb0442`; PostgreSQL, FerretDB, and Caddy remained running.
  - All services are healthy, site/API return 200, the unique payroll index is active, duplicate period groups remain zero, pending review counts remain zero, and recent logs show no critical errors.
- Files changed: `backend/core/indexes.py`, `backend/routes/attendance.py`, `backend/routes/payroll.py`, `backend/tests/test_attendance_safety.py`, `backend/tests/test_payroll_safety.py`, `frontend/src/pages/Attendance.jsx`.
- Rollback: retag `design-saga-backend:rollback-c4df434` and `design-saga-web:rollback-c4df434`, recreate only backend/web, and revert `bbb0442`. No historical data rewrite occurred.

### DS-009: Compensation and private employee data authorization

- Symptom/risk: users with broad `employees.read` access, including Project Manager and Designer roles, received full employee documents containing salary history, bank details, government IDs, documents, emergency contacts, and performance data. Salary preview/history and another employee's generated payslip also accepted employee-read permission.
- Severity: High. Tenant isolation was intact, but sensitive same-tenant HR/payroll data was exposed beyond intended roles.
- Root cause: employee APIs returned raw database documents and payroll reads reused the broader employee permission.
- Correction:
  - Employee list/detail/create/update responses now project compensation fields by `payroll.read` and private HR fields by `employees.update`.
  - Compensation writes require `payroll.create`; salary history/preview/all-payroll preview and another employee's payslip require `payroll.read`.
  - Employee account metadata requires `users.read`.
  - Attendance summaries/configuration omit compensation without payroll permission.
  - Frontend salary columns, cards, tabs, bank controls, private HR tabs, and employee-account tab follow the corresponding permissions.
- Verification:
  - Project Manager synthetic API tests retained basic employee list/detail access while salary, salary history, bank, Aadhaar/PAN, gender, documents, and performance were absent; salary history/preview/payroll preview/other-user payslip returned 403.
  - Runtime production projection assertion passed after deployment; unauthenticated employee endpoint returns 401.
- Files changed: `backend/server.py`, `backend/routes/attendance.py`, `backend/routes/payroll.py`, `backend/tests/test_financial_read_permissions.py`, `frontend/src/pages/Attendance.jsx`, `frontend/src/pages/EmployeeDetail.jsx`, `frontend/src/pages/Employees.jsx`.
- Current state: deployed at `bbb0442` and verified live.

### DS-004: Linked financial posting integrity and dashboard reversals

- Symptom/risk:
  - Invoice and milestone status handlers could create or reverse accounting entries using document permissions without the matching `finance.create`/`finance.update` permission.
  - The linked income endpoint accepted arbitrary partial/over-payments, wrong account types, both invoice and milestone IDs together, and concurrent duplicate receipts; it could mark the source paid even when the amount did not settle it.
  - Milestone-linked income was mislabeled as generic income, so reversal did not reset the milestone.
  - Paid invoices/milestones could be deleted with financial history removed or left orphaned.
  - The finance dashboard excluded reversed originals but included reversal entries, showing negative monthly income instead of a net-zero reversal.
- Production precondition audit: no current invoices or milestones, no duplicate active receipts, no reversal chains, and zero unbalanced journal entries. No production financial records required repair.
- Correction:
  - Payment transitions now require `finance.create`; reversals require `finance.update`.
  - Linked payments require exactly one valid source, exact full settlement, correct asset/income accounts, and trusted project/client linkage from the source record.
  - Journal entries use a tenant-embedded single-field idempotency key with a unique sparse index, preventing concurrent duplicates while allowing a later payment after a legitimate reversal.
  - Payroll period keys were similarly upgraded to a tenant-embedded single-field unique key after a disposable FerretDB test exposed compound-sparse behavior.
  - Paid sources must be reversed before deletion, and journal history is preserved.
  - Dashboard month P&L and today's collections now include reversal pairs so they net correctly.
- Verification:
  - 20 focused backend tests passed; backend/frontend candidate images built successfully.
  - Disposable integration blocked invoice/milestone payment transitions without finance write permissions, rejected partial settlement and wrong account types, preserved two-entry reversal history, netted dashboard income/collections to zero, and produced one receipt from eight concurrent submissions.
  - A second payment after a full reversal succeeded with exactly one active receipt, confirming the idempotency lifecycle.
  - Temporary QA database, containers, worktree, scripts, and candidate images were deleted.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261012T143132Z`; prior images tagged `rollback-bbb0442`.
  - Deployed backend/web at `8ca840d`; PostgreSQL, FerretDB, and Caddy remained running.
  - All services are healthy; site/API return 200; unauthenticated accounting returns 401; both v2 unique indexes are active; production has zero unbalanced journals; recent logs show no critical errors.
- Files changed: `backend/core/indexes.py`, `backend/routes/accounting.py`, `backend/routes/payroll.py`, `backend/server.py`, `backend/tests/test_accounting_safety.py`, `backend/tests/test_payroll_safety.py`, `frontend/src/pages/Invoices.jsx`.
- Rollback: retag `design-saga-backend:rollback-bbb0442` and `design-saga-web:rollback-bbb0442`, recreate backend/web, and revert `8ca840d`. No production business row was rewritten.

### DS-005: Project, task, file and attachment authorization

- Symptom/risk:
  - Several project, task, follow-up, reminder, project-setting, and file endpoints authenticated the caller but did not enforce module permissions or project membership.
  - A same-tenant user could read or modify a guessed task/project/file identifier even when the frontend hid it.
  - User-supplied attachment links accepted executable or local URL schemes such as `javascript:`, `data:`, and `file:`.
- Production precondition audit: production contained zero files, zero tasks, zero vendors, zero expense claims, zero journal entries, and six employees; no unsafe legacy attachment URLs were found. No data rewrite was required.
- Correction:
  - Added one shared same-tenant visibility policy for projects/tasks, including linked employee identities and organization-wide finance/project roles.
  - Enforced read/create/update permissions and visibility on project lists/details/stages, task CRUD/status/bulk/follow-ups/reminders/settings, and file list/create/delete.
  - Added a shared external URL policy allowing only credential-free HTTP/HTTPS URLs and applied it to project files, task links/attachments, employee/vendor documents, expense receipts, and accounting bills.
- Verification:
  - 18 focused security/accounting tests passed in the candidate image.
  - Disposable-database integration proved assigned staff access, same-tenant outsider denial, HR permission denial, cross-tenant denial, zero-row unauthorized bulk updates, unchanged protected task data, and unsafe URL rejection.
  - Temporary QA database, container, scripts, image, and worktree were deleted.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261013T092427Z`; prior backend tagged `rollback-8ca840d`.
  - Deployed backend at `236d7c7`; web, PostgreSQL, FerretDB, and Caddy were not restarted.
  - Backend and dependent services are healthy; site/API return 200; protected project/task/file endpoints return 401 without authentication; recent logs contain no application errors.
- Files changed: `backend/core/access_control.py`, `backend/core/url_security.py`, `backend/models/accounting.py`, `backend/models/expense.py`, `backend/models/task.py`, `backend/models/vendor.py`, `backend/routes/tasks.py`, `backend/server.py`, `backend/tests/test_access_and_url_safety.py`.
- Rollback: retag `design-saga-backend:rollback-8ca840d`, recreate only the backend service, and revert `236d7c7`. No database schema or business records were changed.

### DS-006: Account-management isolation and Super Admin escalation

- Symptom/risk:
  - A tenant Admin could reset another tenant user's password by guessing a global user ID.
  - Tenant role-assignment, approval, registration, and employee-account paths accepted `SuperAdmin`, while the scoped database treated that role string as a global bypass.
  - The first Google user in an empty database was implicitly promoted, and the repository contained a hard-coded Super Admin fallback email.
  - Bearer-only logout did not revoke the server session; self-service password changes left existing sessions active.
  - The legitimate production platform-owner row retained a legacy `org_id`, making tenant-route context ambiguous.
- Production precondition audit: one explicitly allowlisted platform owner, zero unauthorized Super Admins, zero duplicate email groups, and one legacy tenant-scoped platform-owner row. Production uses local FerretDB, not the exposed Atlas connection.
- Correction:
  - Tenant ownership is verified before password reset; tenant admins cannot assign, create, or approve `SuperAdmin` through any tenant workflow.
  - A role string alone no longer bypasses scoped storage; only an explicit flag or configured allowlist identity does.
  - Removed first-user elevation and all hard-coded Super Admin defaults; production requires `SUPER_ADMIN_EMAILS` configuration.
  - Allowlisted platform owners are reconciled without `org_id` during startup and Google sign-in.
  - Logout revokes cookie and bearer sessions; password changes invalidate every active session.
- Verification:
  - 12 focused auth/permission tests passed.
  - Disposable-database integration blocked cross-tenant reset/role changes and all tenant Super Admin creation paths, kept a forged role tenant-scoped, preserved legitimate platform access, and verified logout/password session revocation.
  - Production post-deploy audit: one authorized platform owner, zero unauthorized or tenant-scoped Super Admins, explicit allowlist active, local FerretDB active.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261013T131412Z`; prior backend tagged `rollback-236d7c7`.
  - Deployed backend at `e086089`; backend is healthy, site/API return 200, protected auth/platform endpoints return 401 without authentication, and recent logs contain no application errors.
- Rollback: retag `design-saga-backend:rollback-236d7c7`, recreate only backend, and revert `e086089`. The platform-owner `org_id` cleanup is correct under either version.

### DS-010: Password-login source rate limiting

- Symptom/risk: password login limited failures per identifier but not per network source. An attacker could rotate through many email or employee IDs and avoid the five-attempt account threshold.
- Correction: hash the client address before storage, count failures per opaque source over the existing 15-minute window, block the thirty-first source failure, bound identifier/password request sizes, and expire attempt records after 24 hours. Existing email, employee-ID, tenant disambiguation, and account-lockout behavior remains unchanged.
- Verification: 8 focused auth tests passed in the candidate image. A disposable PostgreSQL/FerretDB/API stack returned 401 for 30 distinct failed identifiers and 429 for attempt 31, confirmed all identifier/source/TTL indexes, and confirmed stored rows contain only opaque source hashes. All temporary containers, network, database, and test script were removed.
- Files changed: `backend/routes/auth.py`, `backend/models/user.py`, `backend/core/indexes.py`, `backend/tests/test_auth_tenant_safety.py`.
- Database effect: startup creates two non-business indexes on `login_attempts`; no user or ERP business records are rewritten.
- Production deployment: verified backup `/opt/design-saga-backups/20261013T133112Z`; prior backend tagged `rollback-bd3b796`; deployed only backend at `d14fc5d`. Site/API returned 200, unauthenticated auth returned 401, all services are healthy, recent logs contain no application errors, and the identifier/source/TTL indexes are active.
- Rollback: retag `design-saga-backend:rollback-bd3b796`, recreate only backend, and revert `d14fc5d`. The new indexes are compatible with the prior application.

### DS-011: Attendance retry and integrity hardening

- Production evidence: Hiren Panchal's account/employee linkage is valid. His 2026-10-13 site punch matched Oeuvre_2 at 23.2 m with 16.7 m GPS accuracy, was accepted automatically, and checked out successfully. Two older in-fence punches from before `c4df434` were rejected under the former approval behavior; no duplicate, missing-tenant, checkout-without-checkin, or future attendance rows exist.
- Root causes:
  - A rejected punch retained `check_in`, while backend and frontend treated any stored check-in as final for the day. Employees could not retry after reaching an authorized location.
  - Late-arrival review used an unrestricted update, so later or concurrent reviewers could overwrite an earlier decision.
  - Manual attendance silently accepted malformed, cross-day, or reversed timestamps and manager workflows could reference nonexistent employees.
  - Check-in used organization weekly offs even when an employee had an explicit schedule; overlapping pending/approved leave requests were accepted.
- Correction: allow exactly one atomic retry of a rejected/absent punch, archive the rejected attempt in the same attendance record, clear stale checkout/review fields, and show a clear retry state in the UI. Late review now changes only `pending` rows. Manual timestamps and employee references are validated, employee weekly offs take precedence, overlapping active leave is rejected, leave ranges are bounded, and attendance/geofence/config inputs have strict type/range validation.
- Verification: 25 focused attendance/payroll/auth tests passed; backend and frontend production images built successfully. A disposable PostgreSQL/FerretDB/API workflow proved rejected-punch retry/history, duplicate-punch denial, overlapping-leave denial, reversed-time and unknown-employee denial, and exactly one winner from six concurrent late-review requests. Temporary database, containers, network, and scripts were removed.
- Files changed: `backend/models/attendance.py`, `backend/routes/attendance.py`, `backend/tests/test_attendance_safety.py`, `frontend/src/pages/Attendance.jsx`.
- Database effect: no migration or production business-data rewrite; future rejected retries append an embedded audit snapshot to the existing daily row.
- Production deployment:
  - Verified pre-deploy backup `/opt/design-saga-backups/20261014T080312Z`; all SHA-256 checks passed. Prior backend/web images remain tagged `rollback-eae36f1`.
  - Deployed backend and web at `35d07c6`; PostgreSQL, FerretDB, and Caddy were not restarted. Both rebuilt services became healthy and public site/API/auth smoke checks returned 200/200/401 as expected.
  - Hiren Panchal successfully checked in on 2026-10-14 as `site_visit` with `present/auto` status. Production still has zero duplicate employee/date groups, zero checkout-without-check-in rows, and zero future-dated attendance rows.
  - Recent backend/web logs contain no application errors, systemd reports no failed units, protected VPS Caddy changes remain untouched, and disposable candidate images/worktrees were removed.

### DS-012: RBAC override and session lifecycle enforcement

- Root causes:
  - Permission checks and user serializers treated an explicit empty permission list as if no override existed, restoring the role's static defaults. A tenant could not fully revoke a role even though the Team & Roles UI saved the empty override.
  - Legacy routes in `server.py`, including `/auth/me`, used a duplicate account gate that did not check tenant suspension/deactivation. Missing tenant records were also allowed by login and request gates.
- Correction: an attached permission list is now authoritative even when empty. Account approval/activation and secure SuperAdmin-aware tenant existence/status checks are centralized in `ensure_user_access` and reused by password login, modular routes, legacy routes, and `/auth/me`. The Google session cookie now uses `SameSite=Lax` for the same-origin deployment.
- Verification:
  - 37 focused RBAC/auth/attendance/payroll/accounting tests passed; the production backend image built successfully.
  - Disposable PostgreSQL/FerretDB/API testing proved an empty Employee override blocks a default `projects.read` grant, serializers return `permissions: []`, and suspended or missing tenants receive 403. Disposable containers, network, database, image, and worktree were removed.
  - Production had zero empty permission overrides before deployment, so no current user was unexpectedly locked out.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261014T081519Z`; all SHA-256 checks passed. Prior backend remains tagged `rollback-b20cb9c`.
  - Deployed backend only at `767bfee`; web, PostgreSQL, FerretDB, and Caddy were not restarted. Public site/API/auth smoke checks returned 200/200/401, backend is healthy, systemd has no failed units, and logs contain no application errors.
  - A temporary production QA org/user/session/override proved active `/auth/me` 200 with an empty permission list, project access 403, suspended tenant 403, and missing tenant 403. Every QA row was deleted and a zero-row cleanup assertion passed.
- Files changed: `backend/core/deps.py`, `backend/core/rbac.py`, `backend/routes/auth.py`, `backend/server.py`, `backend/tests/test_rbac_session_safety.py`.
- Database effect: no migration or permanent business-data changes.

### DS-013: Secondary-surface visibility enforcement

- Root causes:
  - Global search applied tenant and module permission checks but skipped the assignment/team visibility rules used by project and task endpoints.
  - Comments required authentication only, so a user could list or add comments against a guessed hidden project/task/entity ID.
  - The calendar feed exposed all tenant tasks, project deadlines, approved employee leave names, and payment milestone amounts to any role with `calendar.read`.
  - Calendar attendee IDs were not tenant-validated before notification fan-out, and unbounded search/date inputs allowed unnecessarily expensive requests.
- Correction: search now merges the shared project/task visibility queries and uses the correct purchase-order permission. Comment list/create/delete validates the target entity, module read permission, and project/task visibility. Calendar sources are independently permission-gated; tasks/projects use shared visibility, ordinary employees see only their own approved leave, milestone amounts require invoice/finance access, and direct notification recipients must belong to the creator's tenant. Search and calendar ranges are bounded and validated.
- Verification:
  - 50 focused visibility/RBAC/auth/attendance/payroll/accounting tests passed; the production backend image built successfully.
  - A disposable two-tenant PostgreSQL/FerretDB/API workflow proved hidden project/task search results are absent, hidden comments return 404, calendar returns only the employee's visible task/project and own leave, milestones remain hidden without financial permission, oversized ranges return 400, a foreign-tenant attendee receives zero notifications, and vendor-only search cannot reveal purchase orders.
  - The disposable database, containers, network, candidate image, and worktree were removed; production business data was not used or changed.
- Production deployment:
  - Verified backup `/opt/design-saga-backups/20261014T082426Z`; all SHA-256 checks passed. Prior backend remains tagged `rollback-1f891dc`.
  - Deployed backend only at `cf82c92`; web, PostgreSQL, FerretDB, and Caddy were not restarted. Public site/API/auth smoke checks returned 200/200/401, backend is healthy, systemd has no failed units, protected Caddy changes remain untouched, and recent logs contain no application errors.
- Files changed: `backend/routes/calendar.py`, `backend/routes/comments.py`, `backend/routes/search.py`, `backend/tests/test_visibility_surfaces.py`.
- Database effect: no migration or business-data rewrite.

### DS-014: Repair release integrity and concurrency gates

- Root causes: scheduled work bypassed the shared job lock and used the wrong tenant field; audit verification could miss a deleted tail and did not require a production HMAC key; password-reset throttling missed the direct user route; several finance workflows used UTC calendar dates; optional compound sparse indexes could reject normal records without idempotency/GSTIN values; and employee numbering used a racy count-based allocator without a unique counter invariant.
- Correction: route both recurring jobs through persisted single-run locks and health state; require an audit HMAC key in production and verify stored chain head/count; cover every reset-password route; centralize business dates on `BUSINESS_TIMEZONE`; use normalized single-field sparse keys for optional uniqueness; add unique scheduler/audit/business indexes; and allocate employee/document numbers through a unique per-tenant atomic counter.
- Candidate verification at `b28a373`: 62 deterministic backend tests passed; backend and frontend production images built; a disposable PostgreSQL/FerretDB workflow passed tenant-admin and employee-ID login, first-attempt authorized site attendance, expense retry, invoice terminal-state guards, PO/GRN over-receipt rejection, concurrent EMI protection, and cross-tenant 404 checks. Eight concurrent employee creates produced eight unique IDs and one counter row. Optional-key tests proved multiple keyless expenses/vendors/bills/payments remain valid while keyed retries remain single-write.
- Production preflight: six employee rows have IDs; zero duplicate groups were found for employee IDs, counters, audit chains, job state, expense/payment request IDs, vendor bill numbers, GSTINs, or invoice numbers, including case-folded identity checks.
- Files changed: `backend/core/audit.py`, `backend/core/helpers.py`, `backend/core/http_security.py`, `backend/core/indexes.py`, `backend/core/jobs.py`, `backend/server.py`, finance/notification route modules, `backend/tests/test_repair_release_safety.py`, `.env.example`, and `docker-compose.yml`.
- Database effect: startup creates/promotes indexes and initializes job state. No historical business rows are rewritten.
- Production deployment: verified backup `/opt/design-saga-backups/20261015T132809Z`; rollback images tagged `rollback-831bb19`; production audit HMAC and IST business timezone configured; backend/web replaced while PostgreSQL, FerretDB, and Caddy remained running. Site/API returned 200, unauthenticated `/api/auth/me` returned 401, all services became healthy, all 11 required unique indexes are active, and both scheduled jobs completed successfully on their first attempt with zero failures. Protected VPS Caddy changes remain untouched.
- Credential hygiene: removed obsolete test scripts containing historical login strings. The named demo tenant accounts do not exist in production and the historical Super Admin string does not match the live password. Previously exposed external MongoDB/viewer credentials still require rotation at their provider.

### DS-015: Runtime dependency, container and monitoring hardening

- Root causes: production dependency pins included known-vulnerable FastAPI/Starlette, PyMongo/Motor and multipart versions; the frontend build was not lockfile-reproducible; the Nginx 1.27 runtime contained 43 fixed high/critical OS findings; backend ran without a non-root/read-only boundary; download filenames were assembled inconsistently; and production had no recurring local health/backup/disk monitor.
- Correction: upgraded the Python runtime dependencies and replaced Passlib with bcrypt's compatible native API; committed the npm lockfile and switched builds to `npm ci`; upgraded the final Nginx runtime to 1.31 Alpine; centralized safe RFC 5987 download headers; ran backend as UID/GID 10001 with a read-only root filesystem, writable `/tmp`, dropped capabilities and no-new-privileges; and installed a deduplicating five-minute systemd monitor for all five containers, public HTTP, disk usage, backup age and backup checksums.
- Verification: 53 focused backend tests passed. A disposable two-tenant workflow passed Super Admin, tenant-owner and employee-ID login, first-attempt authorized attendance for Hiren Panchal, duplicate-punch rejection and cross-tenant denial. Exact candidate containers passed startup and read-only/non-root checks. `pip-audit` and both final runtime-image Trivy scans report zero known high/critical findings; the production npm runtime tree reports zero vulnerabilities. The legacy CRA build-only tree still reports findings and remains a modernization item.
- Production deployment: verified backup `/opt/design-saga-backups/20261015T190147Z` passed every SHA-256 check and `pg_restore -l`; deployed commit `bad2f103ce3c47df5b21608e5ca62191b06fcf17` to backend/web only; PostgreSQL, FerretDB and Caddy retained their uptime. Site/API/auth checks returned 200/200/401, all containers are healthy, both scheduled jobs succeeded with zero failures, the audit chain verifies, systemd has zero failed units, and the protected VPS Caddy changes remain untouched.
- Database effect: startup reconciled one existing platform-owner/user document and ensured indexes; no ERP business records were migrated or deleted. Rollback images are `design-saga-backend:rollback-bf9745c-hardening` and `design-saga-web:rollback-bf9745c-hardening`.
- Remaining external operations: configure `DESIGN_SAGA_ALERT_WEBHOOK_URL` for off-host notifications, add encrypted off-server backup replication, and rotate the previously exposed Atlas/viewer credentials at their providers.

### DS-068: Professional invoice PDF and foreign-key integrity

- Root causes: invoice PDFs displayed stored ISO dates, truncated long service
  descriptions, split payment/terms content onto an orphan page, and did not
  retain a safe client-facing snapshot. A caller-supplied display name could
  also accompany an invalid client/project ID until after a document number
  was allocated.
- Correction: client/project IDs are resolved before numbering, invoice-facing
  client details are snapshotted without internal fields, dates render as
  DD/MM/YYYY, item rows wrap across repeated multipage headers, and the
  payment/terms/footer block stays together when the remaining page is short.
- Verification: 45 focused invoice/accounting/public-share tests pass. A
  four-page A4 invoice with 28 long service rows was rendered and inspected;
  headers, rows, totals, payment details and terms remain readable without
  clipping or an orphan terms page.
- Database effect: none. Existing invoices without a snapshot continue to use
  their stored client name.

### DS-069: Accounting source correction actions and employee names

- Root causes: the shared transaction modal intentionally blocked generic
  journal deletion for source-controlled records, but did not route its Delete
  action to existing commission/vendor/payroll correction APIs. Employee
  selectors and Daybook labels read `employee.name`, while the Employee Master
  stores `first_name`/`last_name`, leaving only the employee code visible.
- Correction: Delete now routes commission receipts, vendor bills, vendor
  payments and payroll runs to their authoritative reversal/cancellation
  workflows with their existing backend permission checks. Accounting employee
  selectors, employee ledgers and Daybook party labels use the shared defensive
  full-name formatter and retain the employee code as secondary context.
- Existing related repair verified: vendor profile Edit/Archive, planned
  commission Edit/Cancel, commission-receipt Delete with balanced reversal,
  responsive non-scrolling accounting navigation, explicit payroll Cash/Bank
  selection, and the generic Employee Salary expense shortcut are already in
  the repair branch. The salary shortcut is intentionally blocked so Payroll is
  the single authoritative transaction and employee history cannot diverge.
- Verification: 262 mandatory backend security/integrity regressions pass;
  frontend ESLint passes with zero warnings and the production Vite bundle
  builds.
- Production status: pending deployment with the rest of the repair branch;
  the live runtime remains `3b15e23` and therefore does not yet show these UI
  changes.

## Deployment Safety

### DS-020: Mandatory personal App PIN and five-minute lock

- Root cause: the inactivity lock was server-enforced but optional, accepted only six-digit PINs, and could be disabled by the user. Accounts without a configured PIN and sessions created before rollout could continue without the second local security step.
- Correction: every active approved user must create a separate 4- or 6-digit PIN before business APIs or screens are available. New and existing sessions are upgraded fail-closed, existing PINs remain valid, PINs stay bcrypt-hashed, predictable shared defaults are rejected for new PINs, and users can no longer disable the control. The five-attempt/15-minute lockout, five-minute inactivity timeout, manual Lock now action, session isolation, and audit logging remain in place.
- Safety: no shared `1234`/`123456` credential is assigned and no existing password or PIN is overwritten. Pending and deactivated users retain their existing lifecycle screens. An administrator password reset still clears the old PIN as an account-recovery action, after which the user must enroll a new personal PIN at next login.
- Verification: 196 backend security/integrity regressions passed, full frontend lint passed with zero warnings, and the production frontend bundle built successfully.
- Database effect: no migration or business-data rewrite. Session rows are upgraded lazily on first authenticated request; PIN hashes are written only when each user completes enrollment.

### DS-019: Attendance project selection for authorized sites

- Root cause: the Attendance page reused the general `/projects` list, whose project-team visibility correctly hid projects from unassigned employees. Hiren Panchal is in the `Site Execution` department but was not a project team member, leaving his site-project selector empty despite his cross-site supervision duties.
- Correction: added an attendance-only project-options endpoint that returns only project `id` and `name`. Site Supervisor and Site Execution/Site Supervision employees may choose any active project for a punch; ordinary employees remain limited to assigned projects or active authorized site fences, and archived projects remain hidden. Check-in and geo-check reject unavailable or unauthorized project IDs without weakening normal project visibility.
- Verification: production data identifies Hiren as `Site Execution`; the candidate rule gives him all active attendance project choices while excluding archived projects. Focused attendance, payroll, authentication and tenant-scope tests pass; frontend lint/build and diff checks pass.
- Database effect: none. No attendance, employee, project, geofence, or business record was changed.

### DS-018: Accounting all-time, reversal recovery, and deployment resilience

- Root causes: accounting views treated a missing financial-year filter as the current FY, so "All time" omitted older transactions; reversal recovery had no audit-safe user action; vendor bill posting could leave accounts-payable activity disconnected; and the VPS deployment/monitor scripts depended on the host's failing outbound IPv4 path.
- Correction: added an explicit `fy=all` contract across Income, Expenses, Daybook, ledgers, reports and exports; added paginated transaction history/detail; introduced an idempotent `undo-reversal` operation that posts a reinstatement instead of deleting audit history; tightened accounting/vendor posting invariants; and made trusted image builds use a configurable host build network with direct container smoke checks.
- Verification: 57 focused accounting, vendor, attachment, RBAC/session, attendance and Google Calendar tests passed, plus frontend lint/build and Python compilation. Production contains four journal entries spanning 22/11/2025 through 05/08/2026, proving the all-time range crosses financial years.
- Ritesh Soni entry: `je_9201f35ac20e`, dated 22/11/2025 for Rs 10,000, remains present as an income journal. Production contains zero linked or global reversal entries, so no financial row was deleted or altered.
- Production deployment: verified backups `/opt/design-saga-backups/20261021T071920Z` and `/opt/design-saga-backups/20261021T072737Z` passed all SHA-256 checks. Backend and web were deployed at `cddc2dad4e9538ad033407c4d0c1d285ff97f8e6`; PostgreSQL, FerretDB and Caddy retained uptime. All five containers are healthy, site/API/auth return 200/200/401, UFW is active, SSH key access works over IPv6, and VPS-only Caddy changes remain untouched.
- VPS networking: persistent IPv6 DNS was added because provider-side outbound IPv4 is unavailable. The independent off-server backup and attendance-evidence jobs still require the provider to restore outbound IPv4 access to their IPv4-only source; same-host Design Saga backups remain current and verified.
- Files changed: accounting/vendor backend routes and models, accounting frontend views, focused tests, `deploy/update-production.sh`, and `deploy/monitor.sh`.
- Database effect: no migration, deletion, reversal, reinstatement, or permanent QA data was created.

### DS-007: Safe Git-driven production updates

- Symptom/risk: the VPS `post-merge` hook rebuilt backend and web and ran unrestricted `docker compose up -d` after every merge, including documentation-only changes. It performed no pre-deploy backup, changed-service detection, readiness rollback, or infrastructure-change gate.
- Correction: added tracked `deploy/update-production.sh` with a deployment lock, revision diff classification, documentation-only skip, automatic refusal for Compose/Caddy infrastructure changes, verified pre-deploy backup, affected-service-only build/recreate, health wait, HTTP smoke checks, and automatic image rollback.
- VPS configuration: replaced the ad-hoc hook with a minimal hook that executes the tracked updater. Existing VPS-only Caddy modifications remain untouched.
- Verification: shell syntax passed; the installer merge and explicit updater run identified no runtime changes and skipped all container work. A docs-only end-to-end post-merge test is recorded in the following documentation commit.

### DS-016: Tenant scope and lifecycle completion

- Root causes: the scoped database merge allowed a caller-supplied `org_id` to win over the trusted request scope; several secondary attendance, task, master-data and vendor-rating lookups used global queries; portal/chat/AI message ownership was incomplete; tenant purge omitted business, integration, session, login-attempt and audit-chain records; and orphaned organization logos remained retrievable.
- Correction: trusted scope now overwrites conflicting tenant fields; affected lookup/update paths are tenant-bound; new portal/chat/AI records carry ownership with legacy ownership inferred safely at startup; tenant purge covers 52 explicit tenant-owned collections plus sessions, normalized login identities and audit-chain state; deleted/inactive tenant logos return 404; supporting indexes were added.
- Verification: 88 local-safe backend tests and Python compilation passed. The exact `7cf22c1` image started against disposable PostgreSQL/FerretDB; a two-tenant workflow proved scope override resistance, all 52 purge collection classes, session/login cleanup and the three new indexes. Temporary containers, volume, image and worktree were deleted.
- Production precondition: 46 attendance, 420 master-data and 20 notification records all had valid tenant ownership; tasks, ratings, chat and AI collections were empty. No production business-data rewrite was required.
- Production deployment: backup `/opt/design-saga-backups/20261016T211613Z` passed every SHA-256 check; prior backend is tagged `rollback-be360c8`; only backend was recreated. Site/API returned 200, protected auth/platform endpoints returned 401, all services and the local monitor passed, affected collections retained zero missing/unknown tenant ownership, indexes are active, and recent backend logs contain no errors. VPS-only Caddy changes remain untouched.
- Files changed: tenant scope/index modules, attendance/master-data/organization/platform/task/vendor routes, legacy server message handling, focused tests, and planning evidence under `docs/planning`.

### DS-017: Public share-link tenant isolation

- Root cause: public client-portal and shared-invoice routes resolved a random project token globally, but then loaded child records through an unscoped context using only `project_id` or invoice `id`. Globally random IDs made collision unlikely but did not provide a tenant-isolation guarantee. Suspended tenant share links also remained available.
- Correction: share tokens must match the application-generated format and resolve to an active, unsuspended tenant; every public task, file, invoice, milestone, PDF and message operation is bound to both project and owner `org_id`.
- Verification: all 15 production project share tokens were format-compatible. Ninety-two local-safe backend tests passed. A disposable two-tenant HTTP workflow deliberately reused project and invoice IDs and proved the token exposed only its tenant, wrote its message to that tenant, rendered its invoice, and returned 404 after tenant suspension. Temporary containers, volume, image and worktree were removed.
- Production deployment: backup `/opt/design-saga-backups/20261016T212145Z` passed all checksums; prior backend remains available as a rollback image; backend-only deployment completed at `56e465b`. An existing production share link returned its expected 200 response, site/API/auth smoke checks passed, every service and the local monitor are healthy, and recent logs contain no errors. Caddy changes remain untouched.
- Files changed: `backend/server.py`, `backend/tests/test_public_share_safety.py`.

### OPS-001: VPS access, firewall, and backup health

- SSH: installed `/etc/ssh/sshd_config.d/00-design-saga-hardening.conf`; password and keyboard-interactive authentication are disabled, root is limited to public-key login, `MaxAuthTries` is 3, and `LoginGraceTime` is 30 seconds. `sshd -t`, daemon reload, and fresh key-only connections passed before and after firewall activation.
- Firewall: enabled UFW with default deny inbound and only 22/tcp, 80/tcp, 443/tcp, and 443/udp allowed for IPv4 and IPv6. The public site and API remained HTTP 200 and every Compose service remained healthy.
- Backup health: `design-saga-backup.timer` is enabled and its latest scheduled service run completed successfully. The newest archive `/opt/design-saga-backups/20261013T131412Z` passed every SHA-256 check and `pg_restore -l` parsed its 24.5 MB database dump successfully.
- Service health: cleared the failed-state marker for the obsolete six-day-old transient `tanvika-clean-reset.service`; systemd now reports zero failed units. No application service or business data was changed.
- Rollback evidence: original SSH configuration is retained under `/root/ssh-config-backup-20261013T131903Z`. Firewall rules can be inspected with `ufw status verbose`; keep an established SSH session open for any future SSH/firewall change.
- Remaining operations risk: same-host backups do not protect against VPS loss. Add encrypted off-server replication, backup-failure/uptime/disk alerts, and a documented recovery-time/recovery-point target.

- Before any production repair: capture database backup, record image/commit rollback target, verify the exact Compose service affected, and preserve the VPS Caddy modifications.
- Prefer service-specific rebuild/restart after testing. Do not run `docker compose down -v`.
- Current rollback baseline: backend/web images tagged `rollback-bf9745c-hardening`; the newest verified database/config archive is `/opt/design-saga-backups/20261015T190147Z`.

## Next Action

Rotate the exposed external MongoDB/viewer credentials, configure an external alert webhook and encrypted off-server backups, modernize the legacy CRA build toolchain, and continue the remaining route-by-route business/security audits in `PRODUCTION-RISK-REGISTER.md`.
