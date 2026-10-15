#!/bin/sh
set -eu

repo_root=${DESIGN_SAGA_ROOT:-/opt/design-saga-git}
backup_root=${DESIGN_SAGA_BACKUP_ROOT:-/opt/design-saga-backups}
state_dir=${DESIGN_SAGA_MONITOR_STATE_DIR:-/var/lib/design-saga-monitor}
max_backup_age=${DESIGN_SAGA_MAX_BACKUP_AGE_SECONDS:-129600}
max_disk_percent=${DESIGN_SAGA_MAX_DISK_PERCENT:-85}
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

site_code=$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' https://gamaa.in/ || true)
[ "$site_code" = "200" ] || add_problem "site returned ${site_code:-no response}"
api_code=$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' https://gamaa.in/api/ || true)
[ "$api_code" = "200" ] || add_problem "API returned ${api_code:-no response}"

disk_percent=$(df -P / | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
case "$disk_percent" in
  ''|*[!0-9]*) add_problem "disk usage could not be read" ;;
  *) [ "$disk_percent" -lt "$max_disk_percent" ] || add_problem "root disk is ${disk_percent}% full" ;;
esac

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
