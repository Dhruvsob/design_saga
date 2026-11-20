# GAMAA ERP: production sign-off (2026-11-20)

**Verdict: GO WITH LIMITATIONS** for revision `504a2c3` on production
(`gamaa.in`, host `srv2020574`, checkout `/opt/design-saga-git`).
**It is already live** (deployed 2026-11-20 09:06 UTC and verified, below).

No open critical access-control, data-loss, accounting or payroll defect is
known. The limitations are external configuration the owner controls, plus
checks that need a real person or device (listed at the end).

## 1. What is running

| Item | Observed | Evidence |
|---|---|---|
| Release candidate | `504a2c3` (branch `claude/improvements-20261116`) | `git log` |
| Production checkout | `504a2c3`, fast-forward from `200aa28` | `git log --oneline -1` on the VPS |
| Backend and web images | both labelled `revision:504a2c3ea2c2...` | `docker inspect` labels |
| Containers | backend, web healthy; FerretDB, Postgres healthy; Caddy up 4 days | `docker compose ps` |
| Protected files | only `M deploy/Caddyfile` and `?? deploy/Caddyfile.pre-tanvika-20261003T154040Z` (untouched) | `git status --short` |
| Tanvika (`gamaa.tech`) | HTTP 200 after the deploy; nothing of Tanvika touched | `curl` |
| GitHub | branch carries `504a2c3` plus a docs/test-only commit (no runtime change); `main`/`production` still `200aa28` until the owner OKs the push | `git ls-remote` |

## 2. Gates

| Gate | Result | Evidence |
|---|---|---|
| Build | pass (Vite production build) | `FINAL_TEST_RESULTS.md` §1 |
| Backend tests (all non-live files) | 684 passed, 0 failed | `FINAL_TEST_RESULTS.md` §1 |
| Browser tests | desktop 30 passed, 2 skipped; phone 23 passed, 6 skipped (skips are layout-specific); workflow suites 42/42 after one test fix | `FINAL_TEST_RESULTS.md` §1 |
| Accounting acceptance fixtures | 37 of 37 checks match hand-worked figures | `FINAL_BUSINESS_LOGIC_VERIFICATION.md` |
| Access control | server denials verified; restricted-role UI fixed | `FINAL_SECURITY_REPORT.md` |
| Database compatibility | additive fields only (`authorized_at`, `reconnect_required_at`, `reconnect_notified_at` on calendar connections; a new notification kind). No migration, nothing removed | code review of `bcb5e3b` |
| Recoverable backup | pre-deploy backup `20261120T090540Z`, checksums OK, isolated restore passed (166 tables, 2,468 documents, 2 s) | `FINAL_BACKUP_AND_RECOVERY.md` |
| Rollback method | automatic image rollback on failed health check; manual redeploy of `200aa28` through the same guarded script | `FINAL_RELEASE_AND_RECOVERY.md` §5 |
| Maintenance authorization | owner's standing permission for continuous changes and deploys (2026-11-07); no customer-interrupting action taken | session record |

## 3. Post-deploy checks (production, read-only)

* `https://gamaa.in/` 200, `/api/` 200, `index.html` `Cache-Control: no-cache`, HSTS present.
* Backend log: 0 tracebacks or errors in the 5 minutes after the restart.
* Calendar: the paused production connection received exactly one
  "Reconnect Google Calendar" notice (`[Scheduler] Google Calendar reconnect notices: 1`).
* Disk 53% of 48 GB.
* Sign-in, PIN unlock and dashboard with a real production account were **not**
  exercised: no production credentials are used by design. The same flows
  pass against the release candidate locally (`smoke.spec`, `navigation.spec`).

## 4. Limitations (GO WITH LIMITATIONS)

| Affected users | Restriction | Workaround | Owner |
|---|---|---|---|
| Anyone using Google Calendar sync | Google stops accepting the calendar grant 7 days after each connection while the studio's Google OAuth app is in **Testing** mode | Reconnect from Calendar when the bell says so; publish the OAuth app in Google Cloud Console to end the weekly expiry | Owner (Google Cloud) |
| Everyone (data safety) | All backups are on the same VPS disk; no off-site copy | Daily backups + weekly restore drill on the host | Owner (storage account) |
| Owner/operator | Alerts stay in the server journal; no phone/e-mail alert | Check `systemctl status design-saga-monitor` | Owner (Telegram/webhook) |
| Developers | GitHub Actions locked for billing since 2026-10-24, so CI does not run | Tests run locally before every deploy | Owner (GitHub billing) |
| Employees wanting phone reminders | Reminders appear only in an open browser tab | Keep the ERP tab open; Google Calendar sync once reconnected | Decision on e-mail/push (see recommendations) |

## 5. Lists

**What employees can rely on today**
* Projects, quotations and invoices load for every role, including roles the
  studio has restricted in Team & Roles.
* Money postings: one receipt per retry, cash-basis income equal to cash
  received, loans and owner movements kept out of profit, year-end dates
  falling in the right financial year (37 checks).
* Calendar sync tells you when it stops, and catches up when you reconnect.
* The notification panel works on phones.
* Daily backups that restore cleanly.

**What still needs attention**
* Reconnect Google Calendar for the paused account, and publish the OAuth app.
* Off-site backup copy and an alert channel.
* A screen-reader pass and real iPhone/Android checks (not done; see
  `FINAL_UI_UX_REVIEW.md`).
* Gold or other investments sold in part need a manual journal; there is no
  investment register.

**Decisions that need your approval**
1. Push GitHub `main` and `production` to `504a2c3` (fast-forward).
2. Publish the Google OAuth app (Testing → In production). Calendar is a
   sensitive scope, so users may see Google's "unverified app" screen until
   Google verifies it.
3. The three proposals in `FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md`.
