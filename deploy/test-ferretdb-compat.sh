#!/bin/sh
set -eu

network=design-saga-security-compat-network
volume=design-saga-security-compat-volume
database=design-saga-security-compat-db
ferretdb=design-saga-security-compat-ferretdb
database_image=${DESIGN_SAGA_RESTORE_IMAGE:-design-saga-postgres-documentdb:17-0.107.0-ferretdb-2.7.0-hardened}
ferretdb_image=${DESIGN_SAGA_FERRETDB_IMAGE:-design-saga-ferretdb:2.7.0-hardened}
backend_image=${DESIGN_SAGA_BACKEND_IMAGE:-design-saga-backend}

cleanup() {
  docker rm -f "$ferretdb" "$database" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
cleanup

docker network create "$network" >/dev/null
docker volume create "$volume" >/dev/null
docker run -d --name "$database" \
  --network "$network" --network-alias postgres \
  --memory 1g --pids-limit 256 --security-opt no-new-privileges:true \
  -e POSTGRES_USER=compatuser \
  -e POSTGRES_PASSWORD=compatpass \
  -e POSTGRES_DB=postgres \
  -v "$volume:/var/lib/postgresql/data" \
  "$database_image" >/dev/null

attempt=0
until docker exec "$database" \
  pg_isready -h 127.0.0.1 -U compatuser -d postgres >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 90 ]; then
    docker logs "$database" >&2
    echo "Compatibility database did not become ready" >&2
    exit 1
  fi
  sleep 2
done

docker run -d --name "$ferretdb" \
  --network "$network" --network-alias ferretdb \
  --memory 512m --pids-limit 256 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -e FERRETDB_POSTGRESQL_URL=postgres://compatuser:compatpass@postgres:5432/postgres \
  "$ferretdb_image" >/dev/null

attempt=0
until docker exec "$ferretdb" /ferretdb ping >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    docker logs "$ferretdb" >&2
    echo "Compatibility FerretDB did not become ready" >&2
    exit 1
  fi
  sleep 1
done

docker run --rm -i --network "$network" "$backend_image" python - <<'PY'
from pymongo import MongoClient

client = MongoClient(
    "mongodb://compatuser:compatpass@ferretdb:27017/",
    serverSelectionTimeoutMS=5_000,
)
collection = client.security_compat.probe
inserted_id = collection.insert_one(
    {"marker": "security-compat", "amount": 125}
).inserted_id
assert collection.find_one({"_id": inserted_id})["amount"] == 125
assert collection.update_one(
    {"_id": inserted_id}, {"$set": {"amount": 250}}
).modified_count == 1
summary = list(
    collection.aggregate(
        [
            {"$match": {"marker": "security-compat"}},
            {"$group": {"_id": "$marker", "total": {"$sum": "$amount"}}},
        ]
    )
)
assert summary[0]["total"] == 250
assert collection.delete_one({"_id": inserted_id}).deleted_count == 1
print("FERRETDB_COMPAT_RESULT=pass")
PY
