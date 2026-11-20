# GAMAA ERP: backup and recovery (2026-11-20)

Production host `srv2020574`, shared with Tanvika (never touched). Procedure,
rollback steps and earlier drills: `FINAL_RELEASE_AND_RECOVERY.md`; disaster
runbook: `docs/runbooks/DISASTER-RECOVERY.md`; off-site design:
`docs/runbooks/OFFSITE-BACKUP-AND-ALERTS.md`.

## 1. Coverage (observed today, read-only)

| Item | Observed |
|---|---|
| Daily backup | `design-saga-backup.timer`, next 2026-11-20 18:25 UTC; last run success 2026-11-19 18:26 UTC |
| Pre-deploy backup | taken by the deploy script for every release; today `20261120T090540Z` (release `504a2c3`) |
| Contents | `pg_dump` custom archive, globals, file-storage copy with SHA-256 manifest, image list, git commit |
| Retention | newest 4 kept, 7 days; 937 MB on disk |
| Integrity | `sha256sum -c SHA256SUMS` passes for `20261120T090540Z` |
| Encryption | none on the host (`backup.sh` has no encryption step); the off-site script encrypts with gpg AES-256 before upload |
| Off-host copy | **none**. No off-site timer or configuration present (`/etc/design-saga/offsite.env` absent) |
| Monitoring | `design-saga-monitor.timer` every 5 min, last result success; alerts stay in the server journal |

## 2. Isolated restore (run 2026-11-20 09:08 UTC)

`systemctl start design-saga-restore-drill.service` restores the newest backup
into a throw-away PostgreSQL/DocumentDB container with its own volume, compares
counts, then removes both. Customer data never leaves the host.

| Backup | Tables | Documents restored | Live documents | Files | Restore | Wall clock | Result |
|---|---|---|---|---|---|---|---|
| `20261120T090540Z` | 166 | 2,468 | 2,469 | 14 | 2 s | 9.6 s | **pass**; no leftover restore containers |

The one-document difference is expected: the calendar reconnect notice was
written at 09:07:12, after the 09:05:40 backup.

Earlier drills: 2026-11-15 (two runs, pass). Next scheduled: Sun 2026-11-22 03:40 UTC.

## 3. Recovery figures

* **Latest recoverable point:** 2026-11-20 09:05:40 UTC (pre-deploy backup).
* **RPO:** up to 24 h between daily backups, shorter on release days.
* **RTO (same host):** database restore 2 s at today's size; app rebuild about
  5 min. **RTO if the VPS is lost:** unbounded until an off-site copy exists.
* The firm has not stated target RPO/RTO; the figures above are what the setup
  delivers today.

## 4. Runbook (short)

| Situation | Action |
|---|---|
| Failed deployment | The deploy script health-checks and rolls back images automatically. Manually: redeploy the previous commit through the same guarded script; never `reset --hard`; never touch `deploy/Caddyfile*` |
| Low disk | `df -h /`; prune old build cache (`docker builder prune --filter until=168h`, about 0.8 GB); never delete volumes or the newest backups |
| Database outage | `docker compose ps`; restart only the affected service (`docker compose restart ferretdb` or `postgres`); never `docker compose down` (shared host) |
| Job failure | `systemctl status design-saga-<job>`; `journalctl -u design-saga-<job> --since -1d`; app jobs: `db.job_status` |
| Data loss | Rehearse with `restore-drill.sh` first, compare, take a fresh backup of the current state, then follow `DISASTER-RECOVERY.md` |

## 5. Gaps

| Gap | Status | Needs |
|---|---|---|
| Off-site copy | EXTERNALLY BLOCKED | an S3-compatible bucket or second host (owner account); the scripts are written and tested |
| Alert delivery | EXTERNALLY BLOCKED | Telegram bot or webhook from the owner |
| Separate encryption of on-host backups | REQUIRES OWNER APPROVAL | `deploy/backup.sh` writes plain archives (root-only directory); `deploy/offsite-backup.sh` encrypts with gpg AES-256 before upload. Decide whether on-host copies must also be encrypted |
