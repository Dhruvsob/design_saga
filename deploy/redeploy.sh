#!/bin/sh
set -eu

cd "$(git rev-parse --show-toplevel)"
docker compose build backend web
docker compose up -d

echo "Design Saga updated successfully."
