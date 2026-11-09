#!/bin/sh
set -eu

repo_root=${DESIGN_SAGA_ROOT:-/opt/design-saga-git}
backup_root=${DESIGN_SAGA_BACKUP_ROOT:-/opt/design-saga-backups}

latest=$(find "$backup_root" -mindepth 1 -maxdepth 1 -type d \
  -name '20??????T??????Z' -printf '%T@ %p\n' 2>/dev/null | \
  sort -n | tail -1 | cut -d' ' -f2-)

[ -n "$latest" ] || {
  echo "No Design Saga backup is available for a restore drill" >&2
  exit 1
}

exec "$repo_root/deploy/restore-drill.sh" "$latest"
