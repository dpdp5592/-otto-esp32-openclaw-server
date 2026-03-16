#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_DIR="$REPO_ROOT/main/xiaozhi-server"

if [ -x "$REPO_ROOT/scripts/bootstrap_local_runtime.sh" ]; then
  "$REPO_ROOT/scripts/bootstrap_local_runtime.sh"
fi

cd "$STACK_DIR"

docker compose \
  -f docker-compose_all.yml \
  -f docker-compose_all.local.yml \
  up -d --build \
  xiaozhi-esp32-server-db \
  xiaozhi-esp32-server-redis \
  xiaozhi-esp32-server \
  xiaozhi-esp32-server-web

docker compose \
  -f docker-compose_all.yml \
  -f docker-compose_all.local.yml \
  ps
