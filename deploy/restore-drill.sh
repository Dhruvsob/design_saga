#!/bin/sh
set -eu

umask 077

repo_root=${DESIGN_SAGA_ROOT:-/opt/design-saga-git}
backup_root=${DESIGN_SAGA_BACKUP_ROOT:-/opt/design-saga-backups}
image=${DESIGN_SAGA_RESTORE_IMAGE:-ghcr.io/ferretdb/postgres-documentdb:17-0.107.0-ferretdb-2.7.0}
backup_dir=${1:-}

usage() {
  echo "Usage: $0 /opt/design-saga-backups/YYYYMMDDTHHMMSSZ" >&2
  exit 2
}

[ -n "$backup_dir" ] || usage
[ -d "$backup_root" ] || { echo "Backup root does not exist: $backup_root" >&2; exit 1; }
[ -d "$backup_dir" ] || { echo "Backup does not exist: $backup_dir" >&2; exit 1; }

backup_root=$(cd "$backup_root" && pwd -P)
backup_dir=$(cd "$backup_dir" && pwd -P)
backup_name=$(basename "$backup_dir")

case "$backup_name" in
  20??????T??????Z) ;;
  *) echo "Refusing non-standard backup directory: $backup_dir" >&2; exit 1 ;;
esac
[ "$(dirname "$backup_dir")" = "$backup_root" ] || {
  echo "Backup must be an immediate child of $backup_root" >&2
  exit 1
}

for required in SHA256SUMS postgres.dump postgres-archive.list file-storage.sha256; do
  [ -f "$backup_dir/$required" ] || {
    echo "Backup is missing $required" >&2
    exit 1
  }
done

(
  cd "$backup_dir"
  sha256sum -c SHA256SUMS >/dev/null
  if [ -s file-storage.sha256 ]; then
    cd file-storage
    sha256sum -c ../file-storage.sha256 >/dev/null
  fi
)

suffix="$(date -u +%Y%m%dT%H%M%SZ)-$$"
container="design-saga-restore-drill-$suffix"
volume="design-saga-restore-drill-$suffix"
filtered_list=$(mktemp)

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  rm -f "$filtered_list"
}
trap cleanup EXIT INT TERM

# pg_cron creates these rows during container initialization. Restoring their
# data again would duplicate extension-owned scheduler state.
grep -vE 'TABLE DATA cron (job|job_run_details) ' \
  "$backup_dir/postgres-archive.list" > "$filtered_list"

docker volume create "$volume" >/dev/null
docker run -d --name "$container" \
  --memory 1024m --cpus 1 \
  -e POSTGRES_USER=restoreuser \
  -e POSTGRES_PASSWORD=restore-drill-only \
  -e POSTGRES_DB=postgres \
  -v "$volume:/var/lib/postgresql/data" \
  "$image" >/dev/null

attempt=0
until docker exec "$container" pg_isready -U restoreuser -d postgres >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 90 ]; then
    docker logs "$container" >&2
    echo "Restore database did not become ready" >&2
    exit 1
  fi
  sleep 2
done

docker cp "$backup_dir/postgres.dump" "$container:/tmp/postgres.dump"
docker cp "$filtered_list" "$container:/tmp/postgres-archive.list"

started=$(date +%s)
docker exec "$container" pg_restore \
  -U restoreuser -d postgres \
  --clean --if-exists --no-owner --no-privileges --exit-on-error \
  -L /tmp/postgres-archive.list /tmp/postgres.dump
duration=$(( $(date +%s) - started ))

table_query="SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"
doc_union_query="SELECT string_agg(format('SELECT count(*)::bigint AS n FROM %I.%I', schemaname, tablename), ' UNION ALL ') FROM pg_tables WHERE schemaname = 'documentdb_data'"

cd "$repo_root"
source_user=$(docker compose exec -T postgres printenv POSTGRES_USER | tr -d '\r')
[ -n "$source_user" ] || { echo "Could not determine production database user" >&2; exit 1; }

source_tables=$(docker compose exec -T postgres \
  psql -U "$source_user" -d postgres -Atc "$table_query")
restored_tables=$(docker exec "$container" \
  psql -U restoreuser -d postgres -Atc "$table_query")

source_union=$(docker compose exec -T postgres \
  psql -U "$source_user" -d postgres -Atc "$doc_union_query")
restored_union=$(docker exec "$container" \
  psql -U restoreuser -d postgres -Atc "$doc_union_query")

source_documents=0
restored_documents=0
if [ -n "$source_union" ]; then
  source_documents=$(docker compose exec -T postgres \
    psql -U "$source_user" -d postgres -Atc \
    "SELECT COALESCE(sum(n), 0) FROM ($source_union) AS document_counts")
fi
if [ -n "$restored_union" ]; then
  restored_documents=$(docker exec "$container" \
    psql -U restoreuser -d postgres -Atc \
    "SELECT COALESCE(sum(n), 0) FROM ($restored_union) AS document_counts")
fi

[ "$source_tables" = "$restored_tables" ] || {
  echo "Table-count mismatch: source=$source_tables restored=$restored_tables" >&2
  exit 1
}
[ "$source_documents" = "$restored_documents" ] || {
  echo "Document-count mismatch: source=$source_documents restored=$restored_documents" >&2
  exit 1
}

echo "RESTORE_DRILL_RESULT=pass"
echo "BACKUP=$backup_name"
echo "RESTORE_SECONDS=$duration"
echo "NON_SYSTEM_TABLES=$restored_tables"
echo "DOCUMENT_ROWS=$restored_documents"
echo "FILE_MANIFEST=$(wc -l < "$backup_dir/file-storage.sha256" | tr -d ' ')"
