# Session Checkpoint

Read this first, then `DESIGN-SAGA-REPAIR-TRACKER.md` → "Canonical Open Backlog".
Last updated: 09/11/2026 23:05 IST.

## Where things stand

- Branch `codex/backend-completion`; implementation commit `c544d9e` follows the
  deployed integration `143c995`. The next commit updates this checkpoint/tracker.
- Production runtime/source is `143c995fb90bcc003d83510c3f7627148b709fee`.
  The pre-deploy backup for that release is `/opt/design-saga-backups/20261109T165423Z`.
  Caddy's protected checksum remains
  `e3fc3c8c96d3c84e37af6f0c5e8483481813960d477d64bf43558aa135acaedd`.
- DS-120 completes the three Claude backend handoffs: project invoice-linked
  collections now reconcile, branded payment-receipt/PO/client-statement PDFs
  and contextual UI actions are present, and the stale consultancy test matches
  the intentional letter-proposal contract. It also adds interrupted payroll
  reversal recovery coverage.
- Gates: canonical backend list **485 passed**; frontend ESLint and JSX checks,
  5 logic tests and Vite production build passed; diff and tracked/history
  secret scans passed. No new dependency or migration.
- Read-only production investigation found two Demo-only historical states:
  `pr_2ccbff137a52` was journal-reversed before its run status update completed;
  settlement `vcpay_45ca202c39a1` says bank transfer while journal
  `je_0bf99e7789dd` explicitly uses Cash. Repair only after the DS-120 backup,
  through the idempotent payroll workflow and one exact audited metadata update.

## Next executable tasks (in order)

1. Commit the DS-120 tracker update; push/fast-forward the repair release.
2. Fresh full backup, then rebuild/recreate only backend and web; preserve Caddy,
   FerretDB/PostgreSQL and Tanvika.
3. Apply the two exact Demo repairs with audit evidence; rerun integrity until all
   report sections are zero. Do not touch the real Design Saga tenant data.
4. Live-check auth guards, all three new PDF routes, project money, logs, Caddy
   checksum and `gamaa.tech` health.
5. Continue only genuinely open backlog rows; do not repeat deployed work.

## Waiting on the owner

- SEC-01: rotate/revoke the exposed historical Atlas password and viewer token
  at their providers; code cannot rotate external credentials.
- SEC-02/06: decide whether Employee/Designer defaults retain tenant-wide
  client/lead visibility.
- ACC-02/05/06: accountant/product decisions for GST split, TDS/credit notes,
  Tally/email/payment-link scope and retention.
- OPS-02/03: choose the encrypted off-server backup destination and external
  alert target. The host cannot invent provider credentials or recipients.
- Coordinate the pending kernel reboot because the VPS also hosts Tanvika.

## Resume the local QA stack (Windows, Git Bash)

QA secrets live outside the repo in the session scratchpad as `qa.env`
(`QA_SUPERADMIN_EMAIL`, `QA_PASSWORD`, `QA_PIN`, `AUDIT_HMAC_KEY`). If missing,
regenerate: a `.test` owner email, a 12+ character password and a 6-digit
non-sequential PIN. Never commit them.

```bash
T="$LOCALAPPDATA/DesignSagaTools"
"$T/mongodb/mongodb-win32-x86_64-windows-8.0.4/bin/mongod.exe" --dbpath "$T/qa-db" --bind_ip 127.0.0.1 --port 27017
```

```bash
cd backend && MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=design_saga_qa_e2e ../.venv/Scripts/python.exe scripts/qa_bootstrap.py
```

```bash
cd backend && FILE_STORAGE_ROOT="$LOCALAPPDATA/DesignSagaTools/qa-files" MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=design_saga_qa_e2e SUPER_ADMIN_EMAILS="$QA_SUPERADMIN_EMAIL" CORS_ORIGINS=http://127.0.0.1:5173 COOKIE_SECURE=false APP_ENV=development BUSINESS_TIMEZONE=Asia/Kolkata APP_BASE_URL=http://127.0.0.1:5173 PYTHONPATH=. ../.venv/Scripts/python.exe -m uvicorn server:app --host 127.0.0.1 --port 8001
```

```bash
cd frontend && node ./node_modules/vite/bin/vite.js build && node ./node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort
```

```bash
cd frontend && node ./node_modules/@playwright/test/cli.js test
```

The QA database `design_saga_qa_e2e` is disposable; delete `$T/qa-db` to reset.
