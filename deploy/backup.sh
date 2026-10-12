#!/bin/sh
set -eu

umask 077

repo_root=${DESIGN_SAGA_ROOT:-/opt/design-saga-git}
backup_root=${DESIGN_SAGA_BACKUP_ROOT:-/opt/design-saga-backups}
retention_days=${DESIGN_SAGA_BACKUP_RETENTION_DAYS:-7}

case "$retention_days" in
  ''|*[!0-9]*) echo "Retention must be a non-negative integer" >&2; exit 2 ;;
esac

mkdir -p "$backup_root"
chmod 700 "$backup_root"

exec 9>"$backup_root/.backup.lock"
if ! flock -n 9; then
  echo "Another Design Saga backup is already running" >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
temporary="$backup_root/.${timestamp}.tmp"
destination="$backup_root/$timestamp"

cleanup() {
  if [ -d "$temporary" ]; then
    find "$temporary" -type f -delete
    find "$temporary" -depth -type d -empty -delete
  fi
}
trap cleanup EXIT INT TERM

mkdir "$temporary"
cd "$repo_root"

git rev-parse HEAD > "$temporary/git-commit.txt"
git status --short > "$temporary/git-status.txt"
docker compose images > "$temporary/compose-images.txt"
git diff -- deploy/Caddyfile > "$temporary/Caddyfile.patch"
cp -p deploy/Caddyfile "$temporary/Caddyfile"
cp -p .env "$temporary/production.env"

docker compose exec -T postgres sh -lc \
  'pg_dump -U "$POSTGRES_USER" -Fc postgres' > "$temporary/postgres.dump"
docker compose exec -T postgres sh -lc \
  'pg_dumpall -U "$POSTGRES_USER" --globals-only' > "$temporary/postgres-globals.sql"
docker compose exec -T postgres pg_restore -l \
  < "$temporary/postgres.dump" > "$temporary/postgres-archive.list"

test -s "$temporary/postgres.dump"
test -s "$temporary/postgres-globals.sql"
test -s "$temporary/postgres-archive.list"

(
  cd "$temporary"
  sha256sum Caddyfile Caddyfile.patch compose-images.txt git-commit.txt \
    git-status.txt postgres.dump postgres-globals.sql postgres-archive.list \
    production.env > SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)

mv "$temporary" "$destination"
trap - EXIT INT TERM

find "$backup_root" -mindepth 1 -maxdepth 1 -type d \
  -name '20??????T??????Z' -mtime "+$retention_days" -print | while IFS= read -r old; do
    [ "$(dirname "$old")" = "$backup_root" ] || exit 1
    find "$old" -type f -delete
    find "$old" -depth -type d -empty -delete
  done

echo "Design Saga backup completed: $destination"
