#!/usr/bin/env bash
# Stop the local stack (keeps volumes and data).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker compose --profile local down
echo "Local stack stopped."
