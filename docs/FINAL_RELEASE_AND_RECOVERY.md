# GAMAA ERP: Release and recovery record (2026-11-15)

## 1. Releases deployed today

| Time (UTC) | Commit | What | Rebuilt |
|---|---|---|---|
| 15:35 | `64d73a1` | Drawing transmittals, previews, portal sign-off (P2.7) | backend, web |
| 16:14 | `eaecdcf` | Capacity heatmap and task estimates (P2.5) | backend, web |
| 16:44 | `46eb9c2` | Security: same-workspace body references; audited account deactivation | backend |

Each release: local backend suite + lint + build + browser E2E, then
`git merge-base --is-ancestor vps/live HEAD` (fast-forward only), push, and
`ssh design-saga-vps` fast-forward of the `production` checkout. The
post-merge hook runs `deploy/update-production.sh`: pre-deploy backup,
rebuild of changed services only, health check, automatic rollback on failure.
It refuses changes to `docker-compose.yml` and `deploy/Caddyfile`.

## 2. Post-deploy verification (after `46eb9c2`)

| Check | Result |
|---|---|
| Checkout | `production` at `46eb9c2`; only the protected Caddyfile change and its untracked backup are local |
| Image revisions | backend `46eb9c2` (healthy), web `eaecdcf` (healthy), ferretdb and postgres healthy (up 3 days), caddy up 3 days |
| Public | `https://gamaa.in/`, `/login`, `/api/` 200; live bundle equals the local build |
| New routes | unauthenticated `/api/capacity`, `/api/projects`, `/api/transmittals/x/pdf` 401; unknown portal token 404 |
| Logs | 0 tracebacks, 0 HTTP 5xx in the 15 minutes after restart |
| Tanvika | `https://gamaa.tech/` 200 |
| TLS | gamaa.in valid to 2026-12-29; gamaa.tech to 2027-01-01 (Caddy renews) |

## 3. Backups

* **Daily:** `design-saga-backup.timer` (about 18:23 UTC) runs `deploy/backup.sh`:
  `pg_dump` custom archive, globals, file-storage copy with SHA-256 manifest,
  compose image list, git commit. Keep latest 4, retention 7 days.
* **Pre-deploy:** every release adds one (today `20261115T153522Z`,
  `20261115T161419Z`, `20261115T164411Z`).
* **Integrity:** `sha256sum -c SHA256SUMS` passes for the newest backup.
* **Location:** `/opt/design-saga-backups` on the **same VPS disk** (760 MB for
  11 sets). There is no off-site copy of GAMAA production backups. The
  `erp-independent-backup` job on this host pulls a *different* server
  (srv836208) here; it is not an off-site copy of GAMAA.

## 4. Restore verification

`design-saga-restore-drill.service` (weekly, Sundays 03:42 UTC; also run
manually today) verifies checksums, restores the newest backup into a
throw-away PostgreSQL/DocumentDB container with its own volume (1 GB memory
cap), compares counts, then deletes the container and volume.

| Run | Backup | Tables | Documents restored | Live documents | Files | Restore time | Result |
|---|---|---|---|---|---|---|---|
| 2026-11-15 03:42 (scheduled) | `20261114T182626Z` | 158 | 2,268 | 2,281 | 14 | 2 s | success |
| 2026-11-15 16:45 (manual, after release) | `20261115T164411Z` | 162 | 2,288 | 2,288 | 14 | 1 s | success; no leftover containers |

**RPO:** up to 24 h for data between daily backups (plus any release in
between, which takes its own backup). **RTO:** restoring the database takes
seconds at today's size; a full rebuild of the app on the same host is about
5 minutes. If the VPS itself is lost, RTO is unbounded until off-site copies
exist (see backlog item B1).

## 5. Rollback procedure

1. Automatic: `update-production.sh` rolls back to the previous images if the
   health check fails after a deploy.
2. Manual, code: on the VPS, `git -C /opt/design-saga-git log --oneline -5`,
   choose the previous good commit, and redeploy that commit through the same
   guarded script (do not `reset --hard`; never touch `deploy/Caddyfile*`).
3. Manual, data: rehearse the chosen backup with `deploy/restore-drill.sh`
   (side container) first, compare, then follow
   `docs/runbooks/DISASTER-RECOVERY.md`. Never restore over production
   without a fresh backup of the current state.

## 6. Monitoring

`design-saga-monitor.timer` every 5 minutes checks site, API, containers,
disk, memory, load, database capacity, TLS and backup age. Results go to the
system journal. **Alerts do not leave the VPS yet** (outbound delivery
blocked; owner channel needed, backlog B2).

## 7. Owner smoke test for 2026-11-16 morning (10 minutes)
1. Sign in as a normal employee on a phone; set or enter the App PIN.
2. Mark attendance check-in; open Tasks and update one task.
3. As an admin, open Dashboard, Projects → a project → Design → Drawings and
   Client tab, and Timesheets → Capacity.
4. Report anything unexpected; production logs are checked on request.

## 8. Infrastructure dependencies
Hostinger VPS `srv2020574` (1 vCPU, 3.8 GiB RAM, 48 GB disk, shared with
Tanvika), Docker Compose (`web`, `backend`, `ferretdb`, `postgres`, `caddy`),
Caddy TLS (Let's Encrypt), GitHub `Dhruvsob/design_saga`, Google Cloud OAuth
(calendar sign-in).
