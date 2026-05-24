#!/usr/bin/env bash
# Open the web login page (Garmin credentials + MFA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="${GARMIN_SYNC_HOST:-http://localhost:8080}"
URL="${HOST%/}/login"

echo "Open ${URL} in your browser to register or log in a Garmin account."
if command -v open >/dev/null 2>&1; then
  open "${URL}"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${URL}"
fi
