#!/bin/sh
set -eu

repo_root=${DESIGN_SAGA_ROOT:-/opt/design-saga-git}
cd "$repo_root"

exec 8>/var/lock/design-saga-deploy.lock
if ! flock -n 8; then
  echo "Another Design Saga deployment is already running" >&2
  exit 1
fi

old_rev=$(git rev-parse ORIG_HEAD 2>/dev/null || true)
new_rev=$(git rev-parse HEAD)
if [ -z "$old_rev" ] || [ "$old_rev" = "$new_rev" ]; then
  echo "No new revision to deploy"
  exit 0
fi

changed=$(git diff --name-only "$old_rev" "$new_rev")
if printf '%s\n' "$changed" | grep -qx 'docker-compose.yml'; then
  echo "docker-compose.yml changed; refusing automatic infrastructure deployment" >&2
  exit 1
fi
if printf '%s\n' "$changed" | grep -qx 'deploy/Caddyfile'; then
  echo "deploy/Caddyfile changed; review and reload Caddy manually" >&2
  exit 1
fi

backend=false
web=false
if printf '%s\n' "$changed" | grep -Eq '^(backend/|\.dockerignore$)'; then backend=true; fi
if printf '%s\n' "$changed" | grep -Eq '^(frontend/|deploy/nginx\.conf$|\.dockerignore$)'; then web=true; fi

if [ "$backend" = false ] && [ "$web" = false ]; then
  echo "No runtime files changed; deployment skipped"
  exit 0
fi

./deploy/backup.sh
rollback=$(printf '%s' "$old_rev" | cut -c1-7)

wait_for() {
  service=$1
  container="design-saga-${service}-1"
  attempts=0
  while :; do
    state=$(docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')
    [ "$state" = healthy ] || [ "$state" = running ] || true
    if [ "$state" = healthy ] || { [ "$service" = web ] && [ "$state" = running ]; }; then return 0; fi
    attempts=$((attempts + 1))
    [ "$attempts" -lt 60 ] || return 1
    sleep 2
  done
}

build_service() {
  service=$1
  build_network=${DESIGN_SAGA_BUILD_NETWORK:-host}
  case "$service" in
    backend) docker build --network="$build_network" -t design-saga-backend:latest -f backend/Dockerfile . ;;
    web) docker build --network="$build_network" -t design-saga-web:latest -f frontend/Dockerfile . ;;
    *) echo "Unsupported service build: $service" >&2; return 1 ;;
  esac
}

deploy_service() {
  service=$1
  docker tag "design-saga-${service}:latest" "design-saga-${service}:rollback-${rollback}"
  build_service "$service"
  docker compose up -d --no-deps --force-recreate "$service"
  if ! wait_for "$service"; then
    docker logs --tail 100 "design-saga-${service}-1" >&2 || true
    docker tag "design-saga-${service}:rollback-${rollback}" "design-saga-${service}:latest"
    docker compose up -d --no-deps --force-recreate "$service"
    wait_for "$service" || true
    echo "$service deployment failed and was rolled back" >&2
    exit 1
  fi
}

if [ "$backend" = true ]; then deploy_service backend; fi
if [ "$web" = true ]; then deploy_service web; fi

docker exec design-saga-web-1 wget -qO- http://127.0.0.1/ >/dev/null
docker exec design-saga-backend-1 python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/', timeout=5)" >/dev/null
docker exec design-saga-backend-1 python -c \
  "import http.client; c=http.client.HTTPConnection('127.0.0.1', 8000, timeout=5); c.request('GET', '/api/auth/me'); r=c.getresponse(); assert r.status == 401, r.status"

echo "Design Saga deployment completed: $(printf '%s' "$new_rev" | cut -c1-7)"
