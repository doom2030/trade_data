#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose --env-file .env build
docker compose --env-file .env run --rm migrate
docker compose --env-file .env up -d --force-recreate api pending-worker

echo "Upgrade complete. App image rebuilt for migrate/api/collector/pending-worker."
echo "Verify /health reports migration=ok before serving traffic."
