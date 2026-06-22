#!/usr/bin/env bash
# Run the RaiRai Subnet API locally with hot reload.
#
# Brings up Postgres + Redis via docker compose, waits until they are healthy,
# then runs the API with --reload against them.
#
# Usage:
#   ./run.sh                 # run on default host/port with --reload
#   HOST=0.0.0.0 PORT=8080 ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

# Ensure a .env exists (copy from the example on first run).
if [[ ! -f .env ]]; then
  echo "No .env found — creating one from .env.example"
  cp .env.example .env
fi

# --- Start infra (Postgres + Redis) ---
echo "Starting Postgres + Redis (docker compose)..."
docker compose up -d db redis

# --- Wait until both are healthy ---
wait_healthy() {
  local service="$1" cid status
  cid="$(docker compose ps -q "$service")"
  if [[ -z "$cid" ]]; then
    echo "ERROR: $service container not found" >&2
    return 1
  fi
  echo -n "Waiting for $service to be healthy"
  for _ in $(seq 1 30); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo unknown)"
    if [[ "$status" == "healthy" ]]; then
      echo " — healthy"
      return 0
    fi
    echo -n "."
    sleep 1
  done
  echo " — TIMEOUT (last status: ${status:-unknown})" >&2
  return 1
}

wait_healthy db
wait_healthy redis

echo "Infra status:"
docker compose ps db redis

# --- Sync dependencies into the managed virtualenv ---
uv sync

echo "Starting API on http://${HOST}:${PORT} (hot reload enabled)"
exec uv run uvicorn app.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --reload \
  --reload-dir app
