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

## Recommended next, by value

| Priority | Improvement | Why (evidence) |
|---|---|---|
| In progress | **Product & Material Library** (P2.2) | Being built in a separate session |
| High | **E-mail delivery** (invites, client portal links, reminders, payslips) | Today links are copied by hand; needs an SMTP/e-mail provider account |
| High | **Phone notifications** (Web Push / PWA, Telegram per user) | Calendar reminders only appear in an open browser tab; employees asked for phone and watch reminders |
| High | **Project selections** (P2.3): area-wise selections from the library -> client approval -> BOQ -> PO -> delivery | Builds on the library and the portal approvals already live |
| Medium | **Bill approved timesheet hours** onto invoices (time-and-materials projects) | Timesheets and profitability exist; billing them closes the loop |
| Medium | **Quotation e-acceptance in the client portal** | Portal approvals exist for drawings/variations; quotations still need offline sign-off |
| Medium | **One lightweight "updates" call** (or server-sent events) instead of separate bell + reminder polls | Polling is a third of all traffic on a 1-vCPU shared server |
| Medium | **Server-side pagination** for task and invoice lists | 1.7 MB task list on a 5,000-task tenant |
| Medium | **HR** (P2.9): onboarding/exit checklists, document-expiry alerts, appraisal notes | Roadmap |
| Medium | **Accounting** (P2.10): TDS on bills, credit notes, Tally export, budgets vs actuals | Needs accountant decisions (GST rounding, TDS) |
| Low | Merge the four remaining copies of the error-text helper into `lib/errors.js` | Code hygiene; behaviour is the same |
| Low | Short per-tenant cache for dashboard statistics | Only matters for much larger tenants |
