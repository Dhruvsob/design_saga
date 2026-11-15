# GAMAA ERP: Final QA results (2026-11-15)

All runs below were on the release line that is now live (backend `46eb9c2`,
web `eaecdcf`). Local runs used a disposable QA database; no destructive test
touched production.

## 1. Summary

| Suite | Executed | Passed | Failed | Skipped |
|---|---|---|---|---|
| Backend unit/integration (pytest, all non-live files) | 640 | 639 | 0 | 1 |
| Browser E2E (Playwright, desktop project: smoke, a11y, forms, navigation, ux, phases) | 31 | 29 | 0 | 2 (by design) |
| Cross-tenant probe: GET routes | 63 | 63 (0 disclosures) | 0 | 68 parameter sets without fixture data |
| Cross-tenant probe: write routes | 144 | 144 (0 foreign records changed) | 0 | |
| Body foreign-reference sweep | 62 | 62 refused after fix | 6 endpoints before fix (fixed) | |
| Employee-role probe | 119 list routes + 8 escalations | all as expected | 0 | |
| Static/dependency scans (bandit, pip-audit, npm audit) | 3 | 3 clean | 0 | |
| Production read-only integrity checks | 9 | 9 (one false alarm explained, see 3) | 0 | |
| Isolated restore drill of today's backup (production host) | 1 | 1 | 0 | |

`pdf.spec` is not in the local run: it reads `deploy/nginx.conf` through a
path the local drive mapping cannot reach. It runs in CI.

## 2. Defects found during this QA cycle

| # | Defect | Severity | Status |
|---|---|---|---|
| 1 | Body references to another workspace's records accepted (6 endpoints) | P1 integrity | Fixed in `46eb9c2`, tests added |
| 2 | Account deactivation not audited, `ok` for unknown IDs | P2 | Fixed in `46eb9c2`, tests added |
| 3 | Capacity heatmap read only the first 5,000 open tasks of any kind, so on a large tenant estimated tasks could be missed | P1 (new feature) | Fixed before its release (`eaecdcf`), regression test |
| 4 | Transmittal PDF pushed the second recipient off the page | P2 | Fixed before release (`64d73a1`) |
| 5 | Drawing history said "Superseded by <client>" for an approved revision | P2 | Fixed before release (`64d73a1`) |
| 6 | Revision preview opened behind the history dialog | P2 | Fixed before release (`64d73a1`) |
| 7 | Project lifecycle bar overflowed the page between 1024 and 1280 px | P2 | Fixed (`3b91b07`) |

## 3. Financial and payroll reconciliation (production, read-only)
* 102 of 102 journal entries balance (debit = credit to the paisa).
* 0 duplicate invoice numbers per tenant and document type.
* Payroll: 7 runs = 3 paid, 2 reversed, 2 corrected. The first check counted
  "corrected" runs as live and flagged 2 "duplicate periods"; corrections
  archive the original run's period key, and a re-check of paid/processing
  runs found **0** employee-months with more than one live run.
* Attendance: 89 rows, 0 duplicate (employee, date).
* No record points at a missing or foreign project; 0 stored files missing.

Calculation rules themselves (paid-leave allowance, late fines, payroll
breakdown, GST split, P&L/balance sheet) are covered by the unit suite
(`test_auto_paid_leave`, `test_attendance_safety`, `test_accounting_safety`,
payroll and invoice tests). An accountant should still review the GST
rounding policy (`ACC-02`) and the first platform invoice.

## 4. Business workflow regressions checked in this cycle
* Lead board: conversion idempotency (409 on re-convert, one winner under
  concurrency), no conversion offered for converted leads, drag state always
  cleared, errors surfaced.
* Project fee structures: missing / null / zero / value contract pinned
  (8 new tests).
* Client portal approvals and transmittals: end-to-end in the browser
  (client approval lands on the drawing and in audit; acknowledgement from the
  portal and recorded by the studio; superseded marks in studio, portal, PDF).
* Capacity heatmap: rules unit-tested; verified in the browser at desktop and
  phone widths.

## 5. Performance measurements (local, largest QA tenant)

| Request | Median | Max (5 runs) |
|---|---|---|
| Login (bcrypt) | 331 ms | 340 ms |
| PIN unlock | 318 ms | 409 ms |
| `/auth/me` | 7 ms | 9 ms |
| `/dashboard/stats` | 254 ms | 346 ms |
| `/notifications` | 181 ms | 211 ms |
| `/projects` | 32 ms | 58 ms |
| `/tasks` (5,000+ open, 1.7 MB) | 502 ms | 545 ms |
| `/invoices` (733 KB) | 179 ms | 315 ms |
| `/capacity` (10 weeks, 44 people) | 75 ms | 84 ms |

Production public endpoints: `/`, `/login`, `/api/` about 0.3 s each.
No authenticated production timing was taken (no production credentials are
used by the agent).

## 5a. Concurrent-user load (local, `backend/scripts/load_probe.py`)
One backend worker (as in production), largest QA tenant, first-screen mix
(session, dashboard, notifications, projects, org, capacity, clients, leads),
one connection per request as production nginx does.

| Scenario | Requests | Throughput | Errors | Median | p95 |
|---|---|---|---|---|---|
| 40 users, one click every 5 s, 60 s | 478 | 8.0/s | 0 | 142 ms | 1.2 s |
| 25 users, no pause at all, 60 s | 968 | 16.1/s | 0 | 1.3 s | 3.2 s |

The first run with think time showed connection resets; they came from the
test client reusing connections that uvicorn closes after 5 s idle. Production
nginx opens a new backend connection per request, so the probe now does the
same, and the errors disappeared. This PC is faster than the 1-vCPU VPS, so
treat these as upper bounds.

## 5b. Added after the first report (same day)
* Reads keyed by a parent record (bank-reconciliation batches/rows, vendor
  commissions, collection entries) now answer 404 for another workspace's ID
  instead of an empty 200 (`test_foreign_parent_404.py`).
* Superseded drawing revisions are served with a SUPERSEDED stamp (studio
  preview, client-portal transmittal and approval files); stored originals are
  untouched; a PDF that cannot be parsed is served as-is with the in-app banner
  (`test_superseded_stamp.py`, verified in the browser on a real PDF).
* Off-site backup script tested locally: not configured (no-op), missing
  passphrase (recorded failure), success (encrypted, read back, retention),
  tampered local backup (refused). Monitor off-site check tested for five states.
* Backend suite after these changes: 650 passed, 1 skipped; cross-tenant probe
  clean (64 GET, 144 write, 62 body references).

## 6. Not tested (honest list)
* Authenticated production smoke test with a real employee account (owner:
  10-minute check tomorrow morning, see release doc).
* Concurrency/load beyond a handful of sessions; no stress test on the shared VPS.
* Safari, iOS and Edge (Chromium desktop/phone only).
* Google Calendar live OAuth (external publishing pending).
* E-mail delivery (not configured).
* Tenant purge on real data (never run on real data; covered by unit tests).
