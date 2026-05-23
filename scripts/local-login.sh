#!/usr/bin/env bash
# Interactive Garmin MFA login for one user (stores tokens under ./data/garmin_tokens/).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

USER_ID="${1:-user1}"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example to .env and set Garmin credentials."
  exit 1
fi

docker compose --profile local build garmin-sync

docker compose --profile local run --rm -it garmin-sync \
  python -c "from garmin_client import garmin_login; from users import load_users; garmin_login(next(u for u in load_users() if u.user_id=='${USER_ID}')); print('login ok for ${USER_ID}')"
