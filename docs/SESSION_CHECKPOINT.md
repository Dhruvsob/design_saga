# Session Checkpoint

Read this first, then `DESIGN-SAGA-REPAIR-TRACKER.md` → "Canonical Open Backlog".
Last updated: 06/11/2026 (Asia/Kolkata).

## Where things stand

- Branch `codex/repair-release`; see `git log -5 --oneline` for the exact head.
- Production runtime is `bfb70cf` (deployed 06/11/2026 08:10 UTC via git bundle;
  the VPS cannot reach github.com). Scheduled backups fixed and verified.
- Deploy recipe: `git bundle create x.bundle <prod-head>..codex/repair-release`,
  `scp` to `root@srv2020574.hstgr.cloud` (IPv6), then on the VPS run in a
  transient unit: `git fetch /root/x.bundle codex/repair-release:refs/remotes/origin/codex/repair-release && git merge --ff-only origin/codex/repair-release`.
- Last completed: DS-084, after DS-083, DS-082, DS-081, DS-080, DS-076..DS-079.
- Gates at checkpoint: backend mandatory list 330 passed; Playwright E2E full run
  (navigation 16 re-run after PIN-unlock fix; forms, money, pdf, smoke, a11y
  passed) against the production build; ESLint 0 warnings; Vite build pass;
  npm audit 0. Local note: OneDrive turns spec files into cloud placeholders that
  Playwright skips; re-create them locally before a run (see DS-083).

## Next executable tasks (in order)

1. Upload the Design Saga logo once the owner provides the file and confirms the tenant.
2. A11Y-01 remainder: modal focus traps, tablet visual QA, screen-reader pass.
3. UX: styled confirmation dialog (47 native confirms), unsaved-change warnings.

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
