# GAMAA ERP: improvement findings (2026-11-16)

How these were found:
* **Screen sweep** (`frontend/e2e/audit-sweep.mjs`, now covering timesheets,
  capacity, payroll, live map and the project tabs): every page as Admin and
  as Employee, desktop and phone width, checking crashes, console errors,
  failed API calls, "undefined/NaN/null" text, raw codes and sideways scroll.
  Result: **no findings** (sessions confirmed signed in).
* **Production traffic** since the last deploy (read-only, 1,936 requests,
  108 endpoints): latency, errors and call volume per endpoint.
* **Production data** (read-only counts) and code review.

## Fixed in this round

| # | Finding (evidence) | Fix |
|---|---|---|
| 1 | A site-visit check-in failed in production with 422. Leaving "Expected time" blank sent `""`, which the time validator rejected, so every such check-in failed | Blank optional times now mean "not set" (`expected_time`, employee shift start/end); policy office hours stay required. The screen no longer sends blank fields. Tests: `test_attendance_optional_times.py` |
| 2 | The same failure showed "Request failed with status code 422" | One shared `lib/errors.js` turns validation lists into readable text ("Expected time: Time must be HH:MM ..."); used on check-in |
| 3 | Staff without dashboard permission had the studio statistics refused (7x 403 in production) and the page then showed "Active projects 0, Overdue tasks 0 - All clear" | Those users now see their own "My day" (tasks, attendance, leave) and no studio statistics |
| 4 | 632 of 1,936 production requests were background polling; polls while the App PIN lock was up were refused (14x 423) | The notification bell pauses in hidden tabs and while locked and refreshes when the tab is shown again; reminders keep running in background tabs (the beep matters there) but stop while locked |
| 5 | 8 of 9 production Admin logins had no employee record, so owners could not check in or use My day for themselves | "Create my employee profile" in My day and on Attendance (`POST /employees/me`, people who can create employees only): links the login, keeps the login's code when free, uses the workspace's office hours, links an existing unlinked record instead of duplicating, audited. Staff without a record are told to ask an administrator. Tests: `test_self_employee_profile.py` |

## Round 2 (2026-11-20)

Found by reproducing in the browser (local QA stack), production data and logs
(read-only), the screen sweep (now including the Product library) and the
cross-tenant probe (53 reads, 94 writes and 61 body references from another
workspace, product routes included: no leaks, no foreign writes, nothing accepted).

| # | Finding (evidence) | Fix |
|---|---|---|
| 6 | **Any server validation error (422) blanked the whole app** on 116 save/load paths in 52 screens: they pass the server's `detail` to a toast, FastAPI sends a list of objects, and React cannot render objects (React error #31, empty page). Reproduced on Holidays | The API layer turns a validation list into readable text once (`normalizeErrorDetail` in `lib/errors.js`; raw list kept in `errors`). Same case now shows "Date: Input should be a valid string · Name: Field required" and the page stays |
| 7 | **Tabs open during a deploy went blank** when they next opened a page they had not loaded: each deploy replaces the hashed bundles, nginx returns 404 for the old names, and there was no error boundary at all. `index.html` also had no cache header, so a browser could reuse an old shell | A stale bundle reloads the tab once (never loops: a second failure within a minute, or blocked storage, shows a message instead); error boundaries inside the layout (sidebar stays usable) and around the router; `index.html` is served `Cache-Control: no-cache` while the security headers still apply (checked with `nginx -t`) |
| 8 | 51 of 100 production attendance rows (5 people, one alone 24) had a check-in but no check-out, so hours were unknown and nothing reminded anyone | An hour after the shift ends (employee shift, else office end, else 19:00) the person gets one bell notification per day; My day points at the latest day still missing a check-out and opens the correction form with the date and reason filled in. Records are never auto-completed. Tests: `test_checkout_reminders.py` |
| 9 | Four screens kept their own copy of the error-text helper (no field names, no offline message) | They use the shared `lib/errors.js` |

## Recommended next, by value

| Priority | Improvement | Why (evidence) |
|---|---|---|
| High | **E-mail delivery** (invites, client portal links, reminders, payslips) | Today links are copied by hand; needs an SMTP/e-mail provider account |
| High | **Phone notifications** (Web Push / PWA, Telegram per user) | Calendar reminders only appear in an open browser tab; employees asked for phone and watch reminders |
| High | **Project selections** (P2.3): area-wise selections from the library -> client approval -> BOQ -> PO -> delivery | Builds on the library and the portal approvals already live |
| Medium | **Bill approved timesheet hours** onto invoices (time-and-materials projects) | Timesheets and profitability exist; billing them closes the loop |
| Medium | **Quotation e-acceptance in the client portal** | Portal approvals exist for drawings/variations; quotations still need offline sign-off |
| Medium | **One lightweight "updates" call** (or server-sent events) instead of separate bell + reminder polls | Polling is a third of all traffic on a 1-vCPU shared server |
| Medium | **Server-side pagination** for task and invoice lists | 1.7 MB task list on a 5,000-task tenant |
| Medium | **HR** (P2.9): onboarding/exit checklists, document-expiry alerts, appraisal notes | Roadmap |
| Medium | **Accounting** (P2.10): TDS on bills, credit notes, Tally export, budgets vs actuals | Needs accountant decisions (GST rounding, TDS) |
| Low | Prune old Docker build cache after deploys (`docker builder prune --filter until=168h`) | 0.8 GB reclaimable on the server; disk is 50% today, so not urgent |
| Low | Short per-tenant cache for dashboard statistics | Only matters for much larger tenants |
