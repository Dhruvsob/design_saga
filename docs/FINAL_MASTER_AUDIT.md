# GAMAA ERP: master audit (release `6647768`, 2026-11-20)

Companion reports: `FINAL_SECURITY_REPORT.md`, `FINAL_BUSINESS_LOGIC_VERIFICATION.md`,
`FINAL_UI_UX_REVIEW.md`, `FINAL_BACKUP_AND_RECOVERY.md`, `FINAL_TEST_RESULTS.md`,
`FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md`, `FINAL_PRODUCTION_SIGNOFF.md`.
Earlier cycles: `FINAL_PRODUCTION_READINESS_AUDIT.md` (2026-11-15),
`IMPROVEMENT_FINDINGS_2026-11-16.md` (rounds 1-2).

## 1. What is running

* Repository `Dhruvsob/design_saga`; release branch `claude/improvements-20261116`.
* Production `gamaa.in` = host `srv2020574`, checkout `/opt/design-saga-git` at
  `6647768`; web image `6647768`, backend image `1cdac8c` (no backend change since).
* GitHub `main` / `production`: aligned with the release branch after this
  report (fast-forward, separate pushes; see the sign-off). No staging
  environment exists; the local QA stack plays that role.
* `gamaa.tech` (Tanvika) shares the host and was not touched.
* Tenancy (preserved as built): GAMAA is the platform (super-admin,
  `/platform`); each customer firm is an organisation (`org_id`) with its own
  branding and role permissions (Team & Roles); projects carry assignment-based
  visibility; client-portal users act only through personal links.
  **Branches (offices inside a firm) are not modelled**; adding them is a
  data-architecture change (REQUIRES OWNER APPROVAL).

## 2. Inventory (from code, 2026-11-20)

| Area | Count | Source |
|---|---|---|
| API operations | 504 (212 GET, 180 POST, 45 PATCH, 15 PUT, 52 DELETE) on 396 paths | `app.openapi()` |
| Front-end routes | 39 (36 code-split pages); project workspace tabs grouped Overview / Work / Design (Drawings, Selections, Files) / Site / Commercial / Client | `frontend/src/App.js`, `ProjectDetail.jsx` |
| Tenant collections | 75, each registered for export/purge (new: `project_selections`) | `core/tenant_registry.py` |
| In-app background jobs | 4: notification scan, check-out reminders, Google Calendar sync and reconnect notices, collection reminders | `server.py` |
| Host jobs (systemd) | daily backup, 5-min monitor, weekly restore drill, payload validation | `systemctl list-timers` |
| Generated documents | quotation, consultancy proposal, invoice, receipt, reminder, client statement, purchase order, payslip (two kinds), transmittal, vendor commission statement, platform invoices | PDF routes |
| Integrations | Google sign-in, Google Calendar (per user), client portal links; e-mail, push and AI storage not configured | env and code |

## 3. Completion matrix

Status words: VERIFIED, FIXED AND VERIFIED, PARTIAL, MISSING, EXTERNALLY
BLOCKED, REQUIRES OWNER APPROVAL, NOT YET VERIFIED. Revision `74aff6e` unless noted.

| Component / workflow | Role | Evidence | Status | Remaining action |
|---|---|---|---|---|
| Enquiry → lead → client → quotation → project (retry = one project) | studio | `crm-chain`, `proposal`, `ux` specs; `test_conversion_safety.py` | VERIFIED | none |
| Quotation acceptance by the client (exact version) | studio, client | 12 backend tests; `selections.spec` | FIXED AND VERIFIED (new) | none |
| Fee type switching clears obsolete inputs | studio | server keeps only the chosen type's fields | VERIFIED | none |
| Concept → GFC → site; site copy when a newer draft exists | designer, site | `test_drawings.py`, `drawings.spec` (both tests) | FIXED AND VERIFIED | none |
| Room-wise selections → client approval → purchase order | designer, procurement | `selections.spec`, backend tests | FIXED AND VERIFIED (new) | none |
| Measurement → BOQ → PO → GRN → bill | procurement | `procurement-chain`, `collections` specs | VERIFIED | none |
| PO form project field and specification lines | procurement | `selections.spec` | FIXED AND VERIFIED | none |
| Snags with photos; failed upload keeps input; site visits | site | `snags`, `site-visits`, `expense-receipts` specs; code review | VERIFIED | Real-device photo upload: NOT YET VERIFIED |
| Client decision → change → milestone | client, studio | approvals tests; variation → milestone tests (backend + `selections.spec`) | FIXED AND VERIFIED | Invoice the milestone as usual |
| Reminder → notification → source record | all | check-out reminder; calendar reconnect notice (prod) | VERIFIED | Phone/e-mail delivery: REQUIRES OWNER APPROVAL (paid) |
| Google Calendar: outage vs expiry, notice, catch-up | employee | 10 unit tests; prod notice | FIXED AND VERIFIED | Owner publishes OAuth app; user reconnects |
| Google Calendar reconnect with a real account | employee | needs the account holder | NOT YET VERIFIED | Reconnect from Calendar |
| Loans, invoice receipts, commissions, gold, personal bill, FY boundary | finance | 37/37 fixture checks | VERIFIED | Investment register MISSING (REQUIRES OWNER APPROVAL: valuation policy) |
| Payroll: mid-month joining and leaving | HR, finance | 4 hand-worked tests | FIXED AND VERIFIED | Pay the October joiner on the corrected figure |
| Payroll posting, edit, reversal, advances; period close | finance, HR | `money`, `period-close` specs | VERIFIED | none |
| GST on invoices | finance | invoice tests | VERIFIED | TDS: MISSING (roadmap P2.10) |
| Tenant isolation | all | cross-tenant probe round 2 | VERIFIED | none |
| Role × action × resource, 6 tenant roles; demotion; offboarding | all | `role_probe.py` 153/153 | VERIFIED | Portal users: covered by unit tests only |
| Restricted roles' pages (studio overrides) | Designer | `ux.spec` desktop + phone | FIXED AND VERIFIED | none |
| Client-facing PDFs (margin, wrapping, totals, A4, headers) | client, supplier | `pdf_inspection.py` 37/37; before/after | FIXED AND VERIFIED | ₹ glyph needs a bundled font |
| Layout at 320-1920 px, 200% zoom | all | sweep: 29 → 0 | FIXED AND VERIFIED | none |
| Form labels and error summary | all | unit tests; `forms.spec` (summary takes focus, link jumps to line 1's rate, input kept) on desktop and phone | FIXED AND VERIFIED (project, employee, invoice forms) | Add to other long forms as they are touched |
| Accessibility (axe A/AA) | all | `a11y.spec` | VERIFIED | Screen reader, real devices: NOT YET VERIFIED |
| Performance (search, reports, PDFs, PIN → dashboard) | all | `perf_release.py` | VERIFIED (local) | Production timing with a real account: NOT YET VERIFIED |
| Backups and isolated restore | operator | drill pass 12:24 UTC | FIXED AND VERIFIED (drill script) | Off-site: EXTERNALLY BLOCKED |
| Alerts | operator | monitor runs; alerts local only | EXTERNALLY BLOCKED | Alert channel |
| CI | developers | billing lock since 2026-10-24 | EXTERNALLY BLOCKED | GitHub billing |
| Credential rotation SEC-01 | owner | not rotated | EXTERNALLY BLOCKED | Rotate |

## 4. Defects found on 2026-11-20

| # | Severity | Defect (evidence) | Root cause | Fix | Commit |
|---|---|---|---|---|---|
| 1 | P2 | Production's only Google Calendar connection paused since late October, unnoticed | 7-day grant limit while the OAuth app is in Testing mode; no notice | One notice per pause; clear status; Testing-mode hint; Disconnect | `bcb5e3b` |
| 2 | P2 | A Google outage during token refresh would pause sync until the user reconnected | Every non-200 refresh treated as expiry | Only refused grants pause; outages retry | `bcb5e3b` |
| 3 | P2 (privacy) | After a pause, Google kept copies of items deleted or reassigned meanwhile | Nothing queued while paused | Reconnect removes stale copies | `bcb5e3b` |
| 4 | P2 | Two active Designers saw empty Projects and Quotations | A 403 lookup rejected the whole page load | `optionalList`; Projects loading/error states | `504a2c3` |
| 5 | P3 | Notification panel 22-45 px off-screen on phones | Anchored to the bell | Full-width panel on small screens | `504a2c3` |
| 6 | P3 | "No projects yet" shown while loading or after a failure | One empty state | Separate states | `504a2c3` |
| 7 | test | `drawings.spec` failed on every run since P2.7 | Substring name match | Test uses the item's test id | `f66c5c8` |
| 8 | **P1** | Client quotation PDF printed the studio's margin % and base cost rate | PDF table printed internal fields | Selling rate only; no margin column | `74aff6e` |
| 9 | **P1** | Mid-month joiners/leavers paid for Sundays and holidays outside employment (Rs 8,500 on Rs 85,000 for a 16 Oct joining) | Weekly-off/holiday precedence ignored the employment window | Days outside employment unpaid unless worked | `74aff6e` |
| 10 | **P1** | A review revision superseded the construction (GFC) drawing; register and transmittals pointed the site at a draft | Every new issue superseded the previous revision | Construction set stays the site copy until a new construction issue | `74aff6e` |
| 11 | P2 | Quotation and PO PDFs cut descriptions at 55/58 characters | Fixed-width cells with slicing | Wrapped rows, kept on one page | `74aff6e` |
| 12 | P2 | PO form had no project field or line specification (API supported both) | Form omitted stored fields | Project picker, specification per line, selections check | `74aff6e` |
| 13 | P3 | Top bar overflow at 768 px on 20 pages | Breadcrumb could not shrink | Truncating breadcrumb | `74aff6e` |
| 14 | P3 | Employee form: placeholder-only labels, unlabelled joining date; errors only in a toast | Form built without labels | Labels + error summary (also on the project form) | `74aff6e` |
| 15 | P3 | Quotation PDF amounts in Western grouping without paise | `:,.0f` formatting | Indian grouping with paise | `74aff6e` |
| 16 | P3 (ops) | Restore drill failed on the pre-deploy backup of a release that adds tables | Compared with live table count | Live count reported, not failed | `915a6f2` |
| 17 | P2 | An approved variation had no path to billing (only a total on the Approvals tab) | Approvals and milestones not connected | "Add to fee milestones": one milestone per approved variation, linked, refused twice | `1cdac8c` |
| 18 | P2 (branding) | The invoice preview said "DESIGN SAGA · Studio OS" in every firm's workspace | Hard-coded text from before multi-tenancy | Signed-in firm's name | `6647768` |
| 19 | P2 (compliance) | The public privacy policy named "Design Saga ERP" and described a tenant-admin Google connection; Google's OAuth review reads this page | Not updated with the Gamaa rebrand (12 Nov) or per-user calendar sync (10 Nov) | Names Gamaa; describes per-user connections; nothing else changed | `6647768` |
| 20 | P3 | Invoice form fields had no labels; a refused save showed only a toast | Placeholder-only inputs | Labels, field names, error summary with line numbers | `6647768` |
| 21 | **P1** (owner report, 23 Nov) | "Still to receive" was the client's whole project value minus receipts: a 6% fee on Rs 3 crore showed Rs 2,85,57,500 instead of Rs 3,57,500. Percentage milestones, phase fee milestones and profitability also used the project value | Every money figure read `budget` whatever the fee type | One rule (`core/fees.py`): agreed fee for lump sum / consultancy % / per sq ft, contract value for turnkey; project value shown separately. 7 of 9 live projects corrected on screen; no stored amount changed | `baa110e` |
| 22 | Owner request, 23 Nov | No way to record cash deposited into a bank (Rs 50,000 of cash into SBI) | Only capital, loans, advances and gold were offered | "Deposit cash / move money between your accounts": From goes down, To goes up, profit unchanged; overdrawing cash refused | `cd95076` |
| 23 | **P1** (owner report, 23 Nov) | Vendor incentives reduced what the client still owes: project D_1101 showed Rs 14,52,500 received (Rs 11,00,000 client fee + Rs 3,52,500 vendor incentives), still to receive Rs 3,47,500 instead of Rs 7,00,000 | Project "Received" added every money-in entry on the project, whatever the income account or payer | Received counts client fee payments only; incentives (vendor-linked, incentive/commission account, vendor-module receipts) shown on a separate line; reversals undo only their own kind. Live: 2 of 9 projects change (D_1101 Rs 3,47,500 -> Rs 7,00,000; Naitik Soni Rs 1,16,900 -> Rs 1,30,000); ledgers, P&L and stored records untouched | `30141d2` |
| 24 | P2 (owner report, 23 Nov) | Repaying a loan meant retyping the person's name; a spelling variant opened a second "Loan from" ledger or failed | Party ledger found by typed name | Searchable picker (typing "K" lists KPR with the ledger and what is outstanding); repayments must pick an existing ledger and post by account ID; wrong-kind, non-party and other-workspace accounts refused (400); overpayment refused (409). Live: 2 party ledgers, no duplicates | `30141d2` |
| 25 | **P1** (found in live data, 23 Nov) | KPR's client statement PDF showed Rs 14,00,000 paid: three Rs 1,00,000 vendor incentives (Vittaazio) counted as KPR's payments, revealing incentives on a document sent to the client; the client ledger, Money In list and receipt PDF named KPR as payer | The income form let a receipt name both the client and the vendor; every client view filtered only by client | One payer rule (`core/receipts.py`) everywhere; the API refuses client + vendor, an incentive booked to a client, and a project's money booked to another client. Live: KPR's statement Rs 14,00,000 -> Rs 11,00,000; nothing stored changed | `237cc4e` |
| 26 | P1 (live data) | Ritesh Soni's statement left out a Rs 50,000 milestone payment | Milestone collections were saved without the client | Milestone and project receipts carry the project's client; older ones attributed through the project. Live: Rs 50,000 -> Rs 1,00,000 | `237cc4e` |
| 27 | P2 (live data) | No credit card: the owner created "Credit Card HDFC" as an expense, booked the whole Rs 33,585 bill as one expense and a friend's Rs 15,000 repayment as Other Income (income and expenses both overstated) | Expenses could only be paid from cash/bank | Credit-card accounts (liability): pay expenses, pay for a person (paid back) or the owner from the card; pay the bill from a bank. The two live entries are for the owner to correct (reverse and re-enter) | `237cc4e` |
| 28 | P2 (live data) | An equity "yash drawings" account and Gold were flagged as banks; income was received into Gold (demo workspace) | Any account could be flagged as bank | Only cash/bank asset accounts; pickers use one shared filter | `237cc4e` |
| 29 | P2 (live data) | Cash was Rs -89,440 from Jul 2024 to Nov 2025: gold bought from Cash before any cash was recorded | No check on cash payments | Cash payments refused beyond what the till holds on that date, counting later days | `237cc4e` |

Production impact of #9 (read-only): one employee joined on 23 Oct; the only
October payroll run was reversed, so no wrong payment stands. Nothing in
finalised history was recomputed.

## 5. Outstanding work

* **Owner (external):** publish the Google OAuth app; reconnect the paused
  calendar (account holder); off-site backup target; alert channel; GitHub
  billing; SEC-01 rotation.
* **Approvals:** e-mail/push provider; investment valuation policy; Tally
  export; branches (`FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md`).
* **Verification that needs a person or device:** screen reader, real
  iPhone/Android and Safari, production sign-in timing with a real account,
  Google reconnect.
* **Small follow-ups (no approval needed):** error summary on other long
  forms as they are touched; ₹ font for PDFs (needs a bundled Unicode font).
