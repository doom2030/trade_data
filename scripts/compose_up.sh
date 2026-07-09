#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose --env-file .env up -d --build

echo "Services started. migrate runs once on first boot; check /health for database/schema/migration status."
