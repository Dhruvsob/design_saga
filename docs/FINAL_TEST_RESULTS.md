# GAMAA ERP: test results (releases `74aff6e` and `1cdac8c`, 2026-11-20)

Environment unless stated: Windows 11 workstation, local QA stack (FastAPI
backend on :8002 from the release worktree, MongoDB 8.0.4 with a 0.5 GB cache,
Vite production build served on :4174), Playwright Chromium. Production checks
are read-only. The morning release (`504a2c3`) and earlier cycles:
`FINAL_ERP_QA_RESULTS.md`, git history of this file.

## 1. Commands and results

| Check | Command (from the repo) | Result |
|---|---|---|
| Backend, all non-live files | `cd backend && MONGO_URL=... DB_NAME=design_saga_unit ENV=dev python -m pytest -q --ignore=<15 live files>` | **702 passed**, 0 failed (34 s, on `1cdac8c`) |
| New backend tests | `test_selections_and_quote_acceptance.py` (12), `test_payroll_proration.py` (4), `test_drawings.py` (site copy), `test_google_calendar.py` (10, morning) | pass |
| Frontend logic | `node --test src/lib/frontend-logic.test.mjs` | 11 passed |
| Frontend lint / build | `eslint` on changed files; `vite build` | clean; built |
| Browser, desktop, all 19 suites | `playwright test smoke a11y forms navigation ux phases money period-close drawings procurement-chain snags crm-chain site-visits collections consistency phase2 expense-receipts proposal selections --project=desktop` | **75 passed**, 2 skipped (phone-only), 9.6 min |
| Browser, phone | `playwright test smoke navigation ux forms selections phases --project=mobile` | **27 passed**, 6 skipped (desktop-only), 2.7 min |
| Browser after `1cdac8c` | `selections.spec` (3, including variation → milestone); `ux`, `a11y`, `smoke` | 3 passed; 21 passed, 1 skipped |
| Browser after `6647768` | `forms`, `money`, `a11y`, `navigation`, desktop and phone | 24 passed, 8 skipped (layout-specific) |
| Frontend logic after `6647768` | `node --test src/lib/frontend-logic.test.mjs` | 12 passed |
| Accounting acceptance | `python scripts/accounting_acceptance.py` (fresh local workspace) | **37/37** |
| Generated PDFs | `python scripts/pdf_inspection.py` | **37/37** (quotation, invoice, purchase order, payslip) |
| Permissions | `python scripts/role_probe.py` (6 roles, 25 resource/actions, lifecycle) | **153/153** |
| Static and dependency scans | `python -m bandit -q -ll -r . -x ./tests,./scripts`; `python -m pip_audit -r requirements.production.txt`; `npm audit --omit=dev` | 0 medium/high; no known vulnerabilities; 0 vulnerabilities |
| Isolated restore drill (production) | `systemctl start design-saga-restore-drill.service` | pass after the drill fix (`915a6f2`), see `FINAL_BACKUP_AND_RECOVERY.md` |

**Defects found by these runs and fixed** (details in `FINAL_MASTER_AUDIT.md` §4):
quotation PDF margin column; truncated PDF descriptions; mid-month pay;
construction drawings superseded by drafts; purchase-order form without the
project; 768 px top bar; employee form labels; drill false failure.

**Test-side fixes, not product defects:** `drawings.spec` matched "Approve"
against "Ask client to approve" (substring) and failed on every run since
P2.7; `test_conversion_safety.py`'s fake database had no approvals collection
once quotation status changes started closing pending client requests; the
role probe initially called a non-existent salary URL and an unlinked leaver.

**Skipped or excluded, and why**
* 15 legacy "live" test files call a retired Emergent preview server
  (`REACT_APP_BACKEND_URL`); they were not run. An environment limit recorded
  since 2026-11-08.
* Layout-specific browser skips as above; the laptop project was not run.
* Local rate limits are real and were respected: registration 10/hour,
  PIN unlock 10/minute, exports 30/minute (the timing script pauses for them).

## 2. Screen sweep at the brief's widths

`SWEEP_WIDTHS=320,360,390,683,768,1366,1920 node e2e/audit-sweep.mjs`, Admin and
Employee, every page and project tab (683 px = 1366 px at 200% zoom; 320 px =
WCAG reflow). Checks: crashes, console errors, failed API calls, raw codes,
"undefined/NaN", sideways scroll, content cut off at the left edge.

| Width | Findings before | After |
|---|---|---|
| 320, 360, 390, 683, 1366, 1920 px | 0 | 0 |
| 768 px | 29 (20 pages 8-91 px wider than the screen: the top bar) | 0 (`SWEEP_WIDTHS=768,1024`) |

## 3. Performance (local, warm, release `74aff6e`)

`python scripts/perf_release.py`: fresh workspace, documents built by the
script; first request of each kind discarded.

| Request | n | Median ms | p95 ms |
|---|---|---|---|
| Project search (`q=Villa`) | 20 | 18 | 25 |
| Profit and loss (FY) | 20 | 28 | 33 |
| Project selections, 30 rows | 20 | 38 | 54 |
| Quotation PDF, 45-line BOQ | 9 | 689 | 792 |
| Invoice PDF, 40 lines | 9 | 473 | 555 |
| Purchase order PDF, 30 lines | 9 | 453 | 665 |
| PIN unlock + dashboard data | 8 | 408 | 498 |

Large-tenant and load measurements (5,000 tasks, concurrent users) are in
`FINAL_ERP_QA_RESULTS.md` §5-5a.

## 4. Manual browser checks (built-in browser, local)

| What | Viewport | Observed |
|---|---|---|
| Calendar, paused Google connection | 435 px, 1254 px | One message with the e-mail, pause date, 7-day hint, Disconnect and Reconnect |
| Notification panel | 375 px / 1254 px | 12-363 px (fits) / right-anchored 380 px |

## 5. Not tested (honest list)

* Google Calendar reconnect with a real Google account (needs the account holder).
* Real iPhone/Android, Safari, screen reader (NVDA/VoiceOver).
* Production sign-in/PIN timing with a real account.
* Load beyond the concurrent-user probe of 2026-11-15.
