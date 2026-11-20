# GAMAA ERP: production sign-off (2026-11-20, second release of the day)

**Verdict: GO WITH LIMITATIONS** for revision `1cdac8c` on production
(`gamaa.in`, host `srv2020574`, checkout `/opt/design-saga-git`).
**It is already live**: deployed 2026-11-20 13:26 UTC, verified 13:30 UTC.
The day's releases: `504a2c3` (09:06), `74aff6e` (11:18), `915a6f2` (drill
script only, no runtime change), `1cdac8c` (variation billing, 13:26).

No open critical access-control, data-loss, accounting or payroll defect is
known. Three P1 defects were found and fixed in this release (client PDF
showed the studio's margin; mid-month pay; construction drawings replaced by
drafts). The limitations are owner-controlled configuration and checks that
need a real person or device.

## 1. What is running

| Item | Observed | Evidence |
|---|---|---|
| Application images | backend and web both labelled `revision:1cdac8c` | `docker inspect` labels |
| Production checkout | `1cdac8c` (fast-forwards only: `504a2c3`, `74aff6e`, `915a6f2`, `1cdac8c`) | `git log --oneline -1` on the VPS |
| Containers | backend, web healthy; FerretDB, Postgres healthy; Caddy up 4 days | `docker compose ps` |
| Protected files | only `M deploy/Caddyfile` and `?? deploy/Caddyfile.pre-tanvika-20261003T154040Z` | `git status --short` |
| Tanvika (`gamaa.tech`) | HTTP 200 after every deploy (one client-side connection failure at 13:28 UTC; 200 three times right after and from the server; no Caddy errors); nothing of Tanvika touched | `curl` |
| New collection | `project_selections` with its two indexes; approvals gained the quotation index | `index_information()` (read-only) |

## 2. Gates

| Gate | Result | Evidence |
|---|---|---|
| Build and lint | pass | `FINAL_TEST_RESULTS.md` §1 |
| Backend tests (non-live) | **702 passed**, 0 failed | §1 |
| Frontend logic tests | 11 passed | §1 |
| Browser tests | `74aff6e`: desktop **75 passed** across all 19 suites, phone **27 passed**; `1cdac8c`: selections (3), ux, a11y, smoke (21) rerun, all pass | §1 |
| Screen sweep, 7 widths x 2 roles | 29 findings (all at 768 px) fixed; re-sweep at 768/1024 px: 0 | §2 |
| Accounting fixtures | 37/37 | `FINAL_BUSINESS_LOGIC_VERIFICATION.md` |
| Payroll proration (hand-worked) | 4 tests, defect fixed | same |
| Permissions, 6 roles | **153/153** role x action checks; demotion and deactivation take effect on live sessions | `FINAL_SECURITY_REPORT.md` |
| Generated PDFs | 37/37 checks; before/after evidence | `FINAL_UI_UX_REVIEW.md` §3 |
| Scans | bandit 0 medium/high; pip-audit 0; npm audit 0 | `FINAL_SECURITY_REPORT.md` |
| Database compatibility | additive only: new collection, new index, new optional fields; the payroll rule change affects future computations only (stored runs untouched) | code review |
| Recoverable backup | pre-deploy `20261120T132645Z`, checksums OK, isolated restore passed (168 tables and 2,475 documents, both equal to live) | `FINAL_BACKUP_AND_RECOVERY.md` |
| Rollback | image rollback on failed health check; manual redeploy of `74aff6e` (or `504a2c3`) through the guarded script | `FINAL_RELEASE_AND_RECOVERY.md` §5 |
| Authorization | owner: "continue ... don't ask for any permission until each and everything is completed" (2026-11-20) and the standing deploy permission | session record |

## 3. Post-deploy checks (production, read-only)

* `gamaa.in` 200, `/api/` 200; the new endpoints refuse unauthenticated calls (401).
* Backend: 0 tracebacks or errors after the `74aff6e` deploy (100 minutes
  observed) and after `1cdac8c`; non-2xx responses were only 401s (my
  unauthenticated probes and one expired session).
* Disk 53% of 48 GB.
* Real-account sign-in, PIN unlock and dashboard were not exercised in
  production (no production credentials by design); the same flows pass
  locally: PIN unlock to dashboard data median 408 ms, p95 498 ms.

## 4. Limitations (GO WITH LIMITATIONS)

| Affected users | Restriction | Workaround | Owner |
|---|---|---|---|
| Google Calendar users | Calendar grants expire 7 days after each connection while the OAuth app is in Testing mode; one account is paused now | Reconnect from Calendar; publish the OAuth app | Owner (Google Cloud) |
| Everyone (data safety) | Backups only on the VPS disk | Daily backups + weekly restore drill | Owner (storage account) |
| Owner/operator | Alerts stay in the server journal | `systemctl status design-saga-monitor` | Owner (alert channel) |
| Developers | GitHub Actions locked for billing | Tests run locally before each deploy | Owner (GitHub billing) |
| Employees | Reminders only in an open browser tab | Calendar sync once reconnected | Decision on e-mail/push (paid service) |
| Accountant | No investment register (gold quantity, partial sale) | Manual journal | Accountant's valuation policy |
| Multi-office firms | No branch level inside a firm | One workspace per firm | Decision (architecture change) |

## 5. Lists

**What employees can rely on today**
* Client PDFs show selling rates only; long specifications print in full.
* Pay for people who join or leave mid-month counts only the days in employment.
* The drawing register and transmittals always point the site at the
  construction (GFC) sheet, even when a newer draft exists.
* Room-wise selections approved by the client in the portal, with the
  approver's name, flowing into purchase orders; quotations accepted in the
  portal for the exact version sent; approved variations added to the fee
  milestones in one step.
* Projects, quotations, invoices and accounting load for every role; the bell
  and top bar fit phones and tablets.
* Money postings, permissions and backups verified as listed above.

**What still needs attention**
* Reconnect Google Calendar; publish the OAuth app.
* Off-site backup copy, alert channel, GitHub billing, SEC-01 credential rotation.
* Screen-reader and real-device (iPhone/Android, Safari) checks.
* October payroll for the employee who joined on 23 Oct: the corrected figure
  is Rs 2,308 lower than the old engine showed (nothing was paid on the old
  figure; that run was reversed).

**Decisions that need your approval**
1. E-mail (and later phone push) for reminders: provider choice, paid service.
2. Investment register: the accountant's valuation policy (average cost or lots).
3. Branches inside a firm: only if a customer runs several offices.
