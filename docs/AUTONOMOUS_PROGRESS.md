# Autonomous Repair Progress

Last updated: 05/11/2026 (Asia/Kolkata)

## Resume checkpoint

- Branch: `codex/repair-release`
- 05/11/2026 (later): canonical open backlog added to the tracker (12 streams,
  stable IDs). DS-073 (Decimal invoice footing, scoped-DB fail-closed) and DS-074
  (grouped permission-aware navigation) tested locally; backend gate 297 passed.
  Decisions awaiting owner: SEC-02 default client/lead visibility, ACC-02 GST
  split/rounding. Next: OPS-06 disposable-DB + browser E2E harness, UX-04
  searchable selectors, ACC-04 shared money helper adoption.
- 05/11/2026 Claude Code session: baseline at `dd480d2` re-verified (279 backend
  tests incl. three suites missing from CI, ESLint 0 warnings, Vite build, secret
  scan). Batch DS-071 (write-route authorization gate + CI coverage) and DS-072
  (read-only `/api/accounting/integrity/source-links` report) completed; expanded
  mandatory list 286 passed. Next executable: run DS-072 on production after
  deployment; continue P1 with Decimal/rounding policy evidence and object-level
  assignment-visibility tests for limited roles.
- Last verified checkpoint before the 03/11 batch: `53c33c7`
- Production remains at last verified runtime `3b15e23`; SSH to `gamaa.in:22`
  times out before authentication.
- Canonical backlog: `DESIGN-SAGA-REPAIR-TRACKER.md`
- Risk/evidence register: `PRODUCTION-RISK-REGISTER.md`
- Protected VPS-only files: `deploy/Caddyfile` and
  `deploy/Caddyfile.pre-tanvika-20261003T154040Z`; never overwrite or reset them.

## Current execution stream

1. Continue P0/P1 resource-level RBAC/IDOR audit without repeating the completed
   route-authentication inventory.
2. Verify accounting and cross-module correction workflows with focused tests.
3. Run the mandatory backend suite, frontend lint/build and tracked-secret scan
   after each logical release batch.
4. Push `codex/repair-release`, generate a checksummed delta bundle from
   `3b15e23`, and deploy only after stable VPS access, backup and health gates.

## Current local batch

- DS-070: Vendor payments and commission receipts now support bounded
  reference/notes correction from their authoritative source records. Reference
  changes synchronize the linked journal atomically under a document lock and
  emit an audit event. Daybook/Ledger no longer offer generic journal metadata
  edits or direct reversals for source-driven entries; their Edit/Delete actions
  route to the source-safe workflow so vendor history and accounting cannot
  diverge. Amount/date/account/allocation corrections remain reversal/re-record.
- Focused vendor correction suite: 6 passed. Complete mandatory backend
  security/integrity suite: 268 passed. Frontend ESLint, production Vite build,
  tracked-secret scan and diff checks pass.

- DS-061/DS-062: Google Calendar retry state and scheduled-job status now retain
  only bounded exception type/HTTP status, never raw provider/database messages.
- DS-063: tenant notification-scan results and logo-storage API errors no longer
  return raw exception text to callers.
- DS-064: expired/revoked sessions now clear protected UI immediately; auth and
  five-minute app-lock activity synchronize across same-origin browser tabs.
- DS-065: Employee Performance warnings/rewards now have permission-aware,
  audited edit/delete APIs and UI actions. The cross-module correction inventory
  is maintained in `docs/CORRECTION-CAPABILITY-MATRIX.md`.
- DS-066: Vendor and employee document metadata can now be corrected in place
  with nested-record scoping, URL/date validation and content-free audit events.
- DS-067: the latest active salary revision now uses immutable supersession
  instead of deletion, preserving old payroll snapshots and audit history.
- DS-068: invoice creation now validates linked client/project IDs before
  numbering and the professional PDF uses client snapshots, DD/MM/YYYY dates,
  wrapped multipage items and grouped payment/terms content.
- DS-069: source-controlled accounting Delete actions now invoke commission,
  vendor and payroll correction workflows; employee selectors, ledgers and the
  Daybook display first/last names instead of only internal employee codes.
- Focused invoice/accounting/public-share suite: 45 passed. The prior complete
  mandatory backend security/integrity suite passed 262 tests before DS-070.
- Frontend ESLint passes with zero warnings and the production Vite build
  succeeds for the current batch.
- Current dependency audit could not be refreshed: npm registry TLS validation
  failed locally and pip-audit could not reach its package index. Existing CI
  enforcement remains, but this batch must not be described as a fresh clean
  dependency audit.
- Git-history search found old commits containing previously supplied Atlas and
  viewer credential material. The current tree is clean. Provider-side rotation
  remains mandatory; destructive history rewriting is not authorized and would
  not invalidate already exposed credentials.

## External blockers

- Rotate the previously exposed Atlas/viewer credentials at their providers.
- Configure encrypted off-server backup replication and an external alert
  destination. These cannot be proven by local code changes.
- Production deployment and live role/workflow validation require stable VPS SSH
  or an authenticated Hostinger terminal.
