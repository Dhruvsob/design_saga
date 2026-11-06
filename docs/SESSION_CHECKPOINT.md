# Session Checkpoint

Read this first, then `DESIGN-SAGA-REPAIR-TRACKER.md` → "Canonical Open Backlog".
Last updated: 06/11/2026 16:30 IST.

## Where things stand

- Branch `codex/repair-release`; see `git log -5 --oneline` for the exact head.
- Production runtime is `7edf02e` (deployed 06/11/2026 10:43 UTC, backup
  `/opt/design-saga-backups/20261106T104203Z`). Head `6dc7382` (employee
  advances + unsaved warnings, DS-091) is pushed, tested and its verified bundle
  is at `/root/ds-6dc7382.bundle` on the VPS; deploy is waiting for the owner's
  explicit approval.
- Deploy recipe: `git bundle create x.bundle <prod-head>..codex/repair-release`,
  `scp` to `root@srv2020574.hstgr.cloud` (IPv6), verify sha256 both ends, then on
  the VPS in a transient unit: `git fetch /root/x.bundle codex/repair-release:refs/remotes/origin/codex/repair-release && git merge --ff-only origin/codex/repair-release`
  (post-merge hook: backup -> rebuild -> health check -> auto rollback).
- Completed this session: DS-085 phases, DS-086 logo + upload normalisation,
  DS-087 consultancy proposal + quotation modes + flowing turnkey PDF, DS-088
  collections active/history, DS-089 leave privacy, DS-090 salary working +
  styled confirms, DS-091 employee advances + unsaved warnings.
- Gates: backend mandatory list 366 passed; Playwright full run passed (35) plus
  targeted runs of proposal/ux/forms/money/pdf/navigation after later changes;
  ESLint 0 warnings; Vite build pass. OneDrive placeholder note (DS-083) still applies.
- Logo: production tenant DESIGN SAGA (`org_759bcccd654c`) still has the 6250px
  JPG with grid. Owner to re-upload `Design Saga - logo (final, transparent).png`
  via Company Settings (direct DB write is blocked by the safety classifier).

## Next executable tasks (in order)

1. Deploy `6dc7382` once approved; verify live (advances panel, payroll recovery).
2. Attendance policy: effective-dated versions, late tiers with preview (mandate 09, T07).
3. Tenant-editable phase templates; link phase progress to lifecycle stage.
4. A11Y-01 remainder: modal focus traps, tablet visual QA, screen-reader pass.
5. Edit/Delete matrix re-audit across modules (mandate 13) and vendor/project
   commission views (mandate 12).

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
