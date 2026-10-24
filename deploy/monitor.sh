#!/bin/sh
set -eu

repo_root=${DESIGN_SAGA_ROOT:-/opt/design-saga-git}
backup_root=${DESIGN_SAGA_BACKUP_ROOT:-/opt/design-saga-backups}
state_dir=${DESIGN_SAGA_MONITOR_STATE_DIR:-/var/lib/design-saga-monitor}
max_backup_age=${DESIGN_SAGA_MAX_BACKUP_AGE_SECONDS:-129600}
max_disk_percent=${DESIGN_SAGA_MAX_DISK_PERCENT:-85}
max_memory_percent=${DESIGN_SAGA_MAX_MEMORY_PERCENT:-90}
max_load_per_cpu_percent=${DESIGN_SAGA_MAX_LOAD_PER_CPU_PERCENT:-200}
max_db_connection_percent=${DESIGN_SAGA_MAX_DB_CONNECTION_PERCENT:-80}
min_tls_valid_seconds=${DESIGN_SAGA_MIN_TLS_VALID_SECONDS:-1209600}
public_host=${DESIGN_SAGA_PUBLIC_HOST:-gamaa.in}
webhook=${DESIGN_SAGA_ALERT_WEBHOOK_URL:-}

mkdir -p "$state_dir"
state_file="$state_dir/state"
problems=""

add_problem() {
  if [ -n "$problems" ]; then
    problems="$problems; $1"
  else
    problems=$1
  fi
}

for setting in "$max_backup_age" "$max_disk_percent" "$max_memory_percent" \
  "$max_load_per_cpu_percent" "$max_db_connection_percent" "$min_tls_valid_seconds"; do
  case "$setting" in
    ''|*[!0-9]*) echo "Monitor thresholds must be non-negative integers" >&2; exit 2 ;;
  esac
done

cd "$repo_root"
for service in postgres ferretdb backend web caddy; do
  cid=$(docker compose ps -q "$service" 2>/dev/null || true)
  if [ -z "$cid" ]; then
    add_problem "$service container missing"
    continue
  fi
  status=$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)
  [ "$status" = "running" ] || add_problem "$service is $status"
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null || true)
  [ -z "$health" ] || [ "$health" = "healthy" ] || add_problem "$service health is $health"
done

docker exec design-saga-web-1 wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || \
  add_problem "web origin did not respond"
docker exec design-saga-backend-1 python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/', timeout=5)" \
  >/dev/null 2>&1 || add_problem "API origin did not respond"

if command -v openssl >/dev/null 2>&1; then
  cert_path=$(docker exec design-saga-caddy-1 find /data/caddy/certificates -type f \
    -name "$public_host.crt" -print 2>/dev/null | head -1 || true)
  if [ -z "$cert_path" ] || ! docker exec design-saga-caddy-1 cat "$cert_path" 2>/dev/null | \
    openssl x509 -checkend "$min_tls_valid_seconds" -noout >/dev/null 2>&1; then
    add_problem "TLS certificate expires within ${min_tls_valid_seconds}s or could not be read"
  fi
else
  add_problem "openssl is unavailable for TLS expiry monitoring"
fi

disk_percent=$(df -P / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
case "$disk_percent" in
  ''|*[!0-9]*) add_problem "disk usage could not be read" ;;
  *) [ "$disk_percent" -lt "$max_disk_percent" ] || add_problem "root disk is ${disk_percent}% full" ;;
esac

mem_total=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
mem_available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
case "$mem_total:$mem_available" in
  *[!0-9:]*) add_problem "memory usage could not be read" ;;
  0:*|*:) add_problem "memory usage could not be read" ;;
  *)
    memory_percent=$(( (mem_total - mem_available) * 100 / mem_total ))
    [ "$memory_percent" -lt "$max_memory_percent" ] || \
      add_problem "memory usage is ${memory_percent}%"
    ;;
esac

cpu_count=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 1)
load_one=$(awk '{print $1}' /proc/loadavg)
if ! awk -v load_value="$load_one" -v cpus="$cpu_count" -v limit="$max_load_per_cpu_percent" \
  'BEGIN { exit !((load_value * 100) < (cpus * limit)) }'; then
  add_problem "one-minute load ${load_one} exceeds ${max_load_per_cpu_percent}% per CPU"
fi

db_user=$(docker compose exec -T postgres printenv POSTGRES_USER 2>/dev/null | tr -d '\r' || true)
if [ -z "$db_user" ]; then
  add_problem "database user could not be read"
else
  db_connections=$(docker compose exec -T postgres psql -U "$db_user" -d postgres -Atc \
    "SELECT count(*) || ':' || current_setting('max_connections') FROM pg_stat_activity" \
    2>/dev/null | tr -d '\r' || true)
  case "$db_connections" in
    *:*)
      active_connections=${db_connections%%:*}
      max_connections=${db_connections#*:}
      case "$active_connections:$max_connections" in
        *[!0-9:]*) add_problem "database connection usage could not be read" ;;
        *:0) add_problem "database max_connections is zero" ;;
        *)
          db_connection_percent=$(( active_connections * 100 / max_connections ))
          [ "$db_connection_percent" -lt "$max_db_connection_percent" ] || \
            add_problem "database connections are ${db_connection_percent}% used"
          ;;
      esac
      ;;
    *) add_problem "database connection usage could not be read" ;;
  esac
fi

latest=$(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '20??????T??????Z' \
  -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
if [ -z "$latest" ]; then
  add_problem "no verified backup directory found"
else
  age=$(( $(date +%s) - $(stat -c %Y "$latest") ))
  [ "$age" -le "$max_backup_age" ] || add_problem "latest backup is ${age}s old"
  (cd "$latest" && sha256sum -c SHA256SUMS >/dev/null 2>&1) || add_problem "latest backup checksum failed"
fi

new_state=ok
[ -z "$problems" ] || new_state="failed: $problems"
old_state=$(cat "$state_file" 2>/dev/null || true)

if [ "$new_state" != "$old_state" ]; then
  if [ "$new_state" = "ok" ]; then
    message="Design Saga production monitor recovered"
    logger -t design-saga-monitor "$message"
  else
    message="Design Saga production alert: $problems"
    logger -p user.err -t design-saga-monitor "$message"
  fi
  if [ -n "$webhook" ]; then
    escaped=$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')
    curl -fsS --max-time 15 -H 'Content-Type: application/json' \
      --data "{\"text\":\"$escaped\"}" "$webhook" >/dev/null || \
      logger -p user.err -t design-saga-monitor "alert webhook delivery failed"
  fi
  printf '%s\n' "$new_state" > "$state_file"
fi

[ "$new_state" = "ok" ]
