#!/usr/bin/env bash
# Build and start the full local stack (Postgres + garmin-sync).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example to .env and set Garmin credentials."
  exit 1
fi

COMPOSE=(docker compose --profile local)

echo "Building images..."
"${COMPOSE[@]}" build

echo "Starting Postgres..."
"${COMPOSE[@]}" up -d postgres

echo "Waiting for Postgres to become healthy..."
deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
  if "${COMPOSE[@]}" ps postgres 2>/dev/null | grep -q '(healthy)'; then
    break
  fi
  sleep 2
done

if ! "${COMPOSE[@]}" ps postgres 2>/dev/null | grep -q '(healthy)'; then
  echo "Postgres did not become healthy within 120s." >&2
  "${COMPOSE[@]}" ps postgres || true
  exit 1
fi

echo "Starting garmin-sync..."
"${COMPOSE[@]}" up -d garmin-sync

echo
echo "Local stack is up."
echo "  Health:  curl http://localhost:8080/health"
echo "  Sync:    curl -X POST http://localhost:8080/sync"
echo "  Postgres: localhost:5433 (garmin/garmin, db=garmin)"
echo "  Logs:    docker compose --profile local logs -f garmin-sync"
