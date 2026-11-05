# Session Checkpoint

Read this first, then `DESIGN-SAGA-REPAIR-TRACKER.md` → "Canonical Open Backlog".
Last updated: 05/11/2026 (Asia/Kolkata).

## Where things stand

- Branch `codex/repair-release`; see `git log -5 --oneline` for the exact head.
- Production runtime is still `3b15e23`. Nothing after it is deployed.
- Last completed: DS-080 (historical Cash/Bank mismatch listing and Data
  checks panel), after DS-076 (Cash/Bank mismatch), DS-077 (vendor page crash,
  `no-undef`, page smoke), DS-078 (Attendance without employee profile) and
  DS-079 (branded PDFs with logo, self-hosted logo storage).
- Gates at checkpoint: backend mandatory list 324 passed; Playwright E2E 17
  passed / 16 skipped (viewport-independent specs run on desktop only) against
  the production build; frontend logic 4 passed; ESLint 0 warnings (now with
  `no-undef`); Vite build pass; tracked-secret scan pass; npm audit 0.

## Next executable tasks (in order)

1. UX-04: searchable selectors for client/project/vendor/employee/account lists.
2. ACC-04: adopt `core/money.py` in PO, vendor bill, commission, payroll, loans.
3. PRJ-01: per-tenant architecture phase templates (smallest slice).

## Waiting on the owner

- SEC-02: should default Employee/Designer roles keep `clients.read`/`leads.read`?
- ACC-02: CGST/SGST vs IGST split and paisa vs whole-rupee GST rounding.
- SEC-01: rotate exposed Atlas password / viewer token at the provider.
- OPS-01: SSH to 187.52.124.46:22 times out from this workstation (443 is open);
  check Hostinger firewall / UFW / fail2ban.
- OPS-02/03: off-server backup destination and external alert destination.

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
