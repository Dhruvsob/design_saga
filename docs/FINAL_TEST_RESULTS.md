# GAMAA ERP: test results (release candidate `504a2c3`, 2026-11-20)

Environment unless stated: Windows 11 workstation, local QA stack (FastAPI
backend on :8002 from the release worktree, MongoDB 8.0.4 with a 0.5 GB cache,
Vite production build served on :4174), Playwright Chromium. Production checks
are read-only. Earlier cycles: `FINAL_ERP_QA_RESULTS.md` (2026-11-15/16).

## 1. Commands and results

| Check | Command (from the repo) | Result |
|---|---|---|
| Backend, all non-live files | `cd backend && MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=design_saga_unit ENV=dev python -m pytest -q --ignore=<15 live files>` | **684 passed**, 0 failed (35 s) |
| Backend, Google Calendar | `python -m pytest tests/test_google_calendar.py -q` | 31 passed (10 new) |
| Frontend lint (changed files) | `node node_modules/eslint/bin/eslint.js src/...` | clean |
| Frontend build | `node node_modules/vite/bin/vite.js build` | built (chunk-size warning only) |
| Browser suites, desktop | `playwright test smoke a11y forms navigation ux phases --project=desktop` | **30 passed, 2 skipped** (4.3 min) |
| Browser suites, phone | `playwright test smoke navigation ux forms --project=mobile` | **23 passed, 6 skipped** (desktop-only checks; 4.2 min) |
| New regression | `ux.spec`: "a role without client or employee access still sees projects and quotations" | passed on desktop and phone |
| Workflow suites, desktop | `playwright test money period-close drawings procurement-chain snags crm-chain site-visits collections consistency phase2 expense-receipts proposal --project=desktop` | 40 passed, 2 failed, then **42/42**: `drawings.spec` had a test defect (see below), fixed and passing; `collections.spec` "purchase order row menu" passed when rerun alone (local database stall) |
| Accounting acceptance | `python scripts/accounting_acceptance.py` (fresh local workspace) | **37/37** checks match |
| Isolated restore drill (production host) | `systemctl start design-saga-restore-drill.service` | pass, 2 s restore |

**Test defect fixed:** `drawings.spec` looked up the menu item by the name
"Approve", which since P2.7 also matches "Ask client to approve" (Playwright
matches names by substring), so it failed on every run. It now uses the item's
test id `drawing-approve-<number>`.

**Skipped or excluded, and why**
* 15 legacy "live" test files (`test_vendors_module.py`, `test_loans_audit_iter11.py`,
  and others reading `REACT_APP_BACKEND_URL`) call a retired Emergent preview
  server. Run without that variable they fail to connect (115 failures, 54
  errors in a full run): an environment limit, recorded since 2026-11-08
  (`DESIGN-SAGA-REPAIR-TRACKER.md`). They were not run. Vendor payments,
  loans and purchase orders are partly covered elsewhere (non-live unit tests,
  and the `money`/`procurement-chain` browser tests, rerun 2026-11-20), not
  line for line.
* Skips are by design: 2 phone-only tests on the desktop project (phone-width
  smoke, mobile navigation), which ran and passed on the phone project; 6
  desktop-only tests on the phone project.
* The laptop project and the a11y/phases suites at phone width were not rerun
  this cycle.

## 2. Manual browser checks (built-in browser, local)

| What | Viewport | Observed |
|---|---|---|
| Calendar, paused Google connection | 435 px CSS (pane), 1254 px | One message with the e-mail, pause date, 7-day hint, Disconnect and Reconnect; no truncation |
| Bell notice for the paused connection | 375 px (mobile emulation) | Notice "Reconnect Google Calendar" with link to Calendar |
| Notification panel before fix | 435 px | panel left edge at **-22 px** (cut off) |
| Notification panel after fix | 375 px / 1254 px | 12 px to 363 px (fully visible) / right-anchored 380 px, unchanged |

## 3. Performance

No performance-sensitive code changed in this release. The latest measurements
(PIN unlock to dashboard, project search, reports on a 5,000-task tenant, load
probe) are in `FINAL_ERP_QA_RESULTS.md` §5-5a and still apply. Production
traffic since the previous deploy: 2,075 successful requests in 30 h; only 4
non-2xx responses (two 401s at session expiry, and the three 403s that led to
the restricted-role fix).

## 4. Not tested (honest list)

* Google Calendar reconnect with a real Google account (needs the account
  owner to sign in to Google; the OAuth request URL itself is covered by tests).
* Real iPhone/Android devices, Safari, screen reader, 200% zoom and 320 px reflow
  this cycle (see `FINAL_UI_UX_REVIEW.md`).
* Production sign-in/PIN timing with a real account (no production credentials
  by design).
* Load beyond the concurrent-user probe of 2026-11-15.
