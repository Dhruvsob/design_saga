# Design Saga Disaster Recovery

Last verified: 2026-10-24 (Asia/Kolkata)

## Recovery objectives

- Engineering RPO target: 24 hours, matching the current daily backup schedule.
- Engineering RTO target: 8 hours for a complete VPS rebuild and validation.
- The business owner must approve tighter targets before they are treated as a contractual SLA.

Same-host backups protect against bad releases and database corruption. They do not protect
against loss of the VPS or provider account. Encrypted off-server replication remains required.

## Backup contents

Each root-only archive under `/opt/design-saga-backups` contains the PostgreSQL/DocumentDB
dump and roles, uploaded files and their checksums, production environment, Caddy configuration,
Git revision/status, Compose image inventory, and a top-level SHA-256 manifest.

## Non-destructive restore drill

Run this only from the checked-out production repository. It creates a memory-limited temporary
database with no published network ports, restores the selected archive, compares table and
document counts with production, and removes the temporary container and volume on exit.

```sh
cd /opt/design-saga-git
sudo ./deploy/restore-drill.sh /opt/design-saga-backups/YYYYMMDDTHHMMSSZ
```

A valid drill ends with `RESTORE_DRILL_RESULT=pass`. Never treat catalogue inspection alone as
restore proof.

## Incident recovery sequence

1. Stop writes at the proxy or application layer and record the incident start time.
2. Preserve the failed database volume and current images; do not overwrite them.
3. Select the newest archive that passes `sha256sum -c SHA256SUMS` and the isolated restore drill.
4. Recreate the VPS from a controlled OS image and install Docker, Compose, UFW, and systemd units.
5. Restore the protected `.env` and Caddy configuration with root-only permissions.
6. Start PostgreSQL/DocumentDB, restore globals and the database, then restore uploaded files.
7. Deploy the Git commit and container versions recorded in the archive.
8. Start backend and web, then verify health, login, tenant isolation, accounting balances,
   attendance, scheduled jobs, TLS, and recent error logs before reopening writes.
9. Record the selected backup, actual data-loss window, recovery duration, and validation evidence.

Production restore commands are intentionally not automated in the drill script: destructive
replacement requires an active incident decision and a second operator reviewing the target.

## Verified evidence

On 2026-10-24, `/opt/design-saga-backups/20261024T062601Z` passed all archive and uploaded-file
checksums and restored into an isolated container in 2 seconds. The restored database matched
production at 106 non-system tables and 1,015 DocumentDB rows. No production service was stopped
or modified, and the temporary container and volume were removed automatically.
