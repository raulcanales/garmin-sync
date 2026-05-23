# garmin-sync

On-demand Garmin Connect → PostgreSQL sync with `GET /health` and `POST /sync`. No API auth (personal LAN / Unraid). Trigger syncs from n8n or any HTTP client.

Synced tables (JSONB payloads): `activities`, `sleep`, `daily_summary`, `body_battery`, `hrv`, `heart_rate`, `stress`, `body_composition`, `floors`, `training_readiness`, `morning_training_readiness`, `training_status`, `max_metrics`.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GARMIN_EMAIL` | user 1 | — | Garmin email (alias: `GARMIN_USER_1_EMAIL`) |
| `GARMIN_PASSWORD` | user 1 | — | Garmin password (alias: `GARMIN_USER_1_PASSWORD`) |
| `GARMIN_USER_1_ID` | no | `user1` | DB / token subfolder id for user 1 |
| `GARMIN_USER_2_EMAIL` | user 2 | — | Second Garmin account email |
| `GARMIN_USER_2_PASSWORD` | user 2 | — | Second Garmin account password |
| `GARMIN_USER_2_ID` | no | `user2` | DB / token subfolder id for user 2 |
| `GARMIN_TOKEN_CACHE_PATH` | no | `/data/garmin_tokens` | Token cache root (`<path>/<user_id>/` per account) |
| `DATABASE_URL` | yes | — | PostgreSQL DSN (`postgresql://user:pass@host:5432/db`) |

Append `?sslmode=require` to `DATABASE_URL` if your Postgres host requires SSL.

## Local testing (Mac / Linux)

Bundled Postgres is enabled with the `local` profile. Unraid production uses your external database only (no `local` profile).

### 1. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and set `GARMIN_EMAIL` and `GARMIN_PASSWORD` (user 1). Add `GARMIN_USER_2_EMAIL` and `GARMIN_USER_2_PASSWORD` for a second account. You do not need `DATABASE_URL` for local testing — the default points at the compose Postgres service.

### 2. Build and start

```bash
./scripts/local-up.sh
```

Or manually:

```bash
docker compose --profile local build
docker compose --profile local up -d
```

### 3. First run — Garmin 2FA (interactive, once)

Garmin sends an email OTP on first login. Run a one-off login (does not start the web server):

```bash
./scripts/local-login.sh user1
```

Or manually:

```bash
docker compose --profile local run --rm -it garmin-sync \
  python -c "from garmin_client import garmin_login; from users import load_users; garmin_login(load_users()[0]); print('login ok')"
```

For user 2:

```bash
./scripts/local-login.sh user2
```

Or manually:

```bash
docker compose --profile local run --rm -it garmin-sync \
  python -c "from garmin_client import garmin_login; from users import load_users; garmin_login(next(u for u in load_users() if u.user_id=='user2')); print('login ok')"
```

When prompted, enter the MFA code from your email. Tokens are saved under `./data/garmin_tokens/<user_id>/` (user 1 keeps using `./data/garmin_tokens/` if you already logged in there).

If you see **429 / rate limited**, Garmin temporarily blocked login from your IP — usually from too many attempts. Wait **30–60 minutes**, then retry once. Do not loop the login command.

If login keeps failing after a wait, clear stale tokens and try again:

```bash
rm -rf ./data/garmin_tokens
```

### 4. Verify

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/sync
curl -X POST "http://localhost:8080/sync?user_id=user2"
curl -X POST "http://localhost:8080/sync?start_date=2026-05-01&end_date=2026-05-23"
```

Watch logs:

```bash
docker compose --profile local logs -f garmin-sync
```

Inspect the database (optional):

```bash
docker compose --profile local exec postgres psql -U garmin -d garmin -c "SELECT id, user_id, status, finished_at, items_fetched FROM garmin.sync_log ORDER BY id DESC LIMIT 10;"
docker compose --profile local exec postgres psql -U garmin -d garmin -c "SELECT user_id, COUNT(*) FROM garmin.activities GROUP BY user_id;"
```

Without date parameters, sync fetches **today only**. Pass `start_date` and optionally `end_date` (YYYY-MM-DD) to backfill a range.

### 5. Stop / reset

```bash
./scripts/local-down.sh
```

Or manually:

```bash
docker compose --profile local down
```

Remove DB volume and start fresh:

```bash
docker compose --profile local down -v
rm -rf ./data
```

## First run (2FA / OTP) — Unraid / external Postgres

Garmin email OTP is prompted once on stdin. Run interactively so you can enter the code; tokens are written under `GARMIN_TOKEN_CACHE_PATH` on the mounted volume.

```bash
docker compose build
docker compose run --rm -it garmin-sync
```

Complete login, then start normally:

```bash
docker compose up -d
```

## Unraid (Compose Manager)

Do **not** use `--profile local` on Unraid — use your external Postgres only.

1. Clone or copy this repo to the Unraid host.
2. Set `DATABASE_URL` to your external Postgres instance in `.env` or Compose Manager env.
3. Set `GARMIN_DATA_DIR=/mnt/user/appdata/garmin-sync` (or mount `/data` in the UI to that path).
4. Import `docker-compose.yml`; set `GARMIN_EMAIL` and `GARMIN_PASSWORD`.
5. First login: `docker compose run --rm -it garmin-sync`, then `docker compose up -d`.

Schema `garmin` and tables are created on startup from SQL migrations in `migrations/`.

## Database migrations

Schema changes live in numbered SQL files under `migrations/` (e.g. `001_initial_schema.sql`). Pending migrations are applied automatically on app startup and recorded in `garmin.schema_migrations`.

To add a schema change:

1. Create the next file, e.g. `migrations/003_add_foo.sql`.
2. Write forward-only SQL (`ALTER TABLE`, new indexes, etc.).
3. Rebuild/restart the app — the migration runs once.

Inspect applied migrations:

```bash
docker compose --profile local exec postgres psql -U garmin -d garmin -c "SELECT * FROM garmin.schema_migrations ORDER BY version;"
```

## Scripts

One-shot helpers in `scripts/` (all executable):

| Script | Purpose |
|--------|---------|
| `./scripts/local-up.sh` | Build and start local Postgres + garmin-sync |
| `./scripts/local-down.sh` | Stop the local stack |
| `./scripts/local-login.sh [user_id]` | Interactive Garmin MFA login (default `user1`) |
| `./scripts/publish.sh` | Build `linux/amd64` image and push to `10.0.0.60:5001/garmin-sync:latest` |

Before first publish, add your registry to Docker Desktop → Settings → Docker Engine as an insecure registry (HTTP, not HTTPS):

```json
"insecure-registries": ["10.0.0.60:5001"]
```

Apply & Restart Docker Desktop, then publish.

Publish overrides:

```bash
REGISTRY=10.0.0.60:5001 IMAGE_NAME=garmin-sync TAG=latest ./scripts/publish.sh
```

On Unraid, use `docker-compose-unraid.yml` (pulls the published image). Local dev uses `docker-compose.yml` with `--profile local`.

## Grafana views

Migration `002_grafana_views.sql` creates read-only views for Grafana Postgres datasource queries:

| View | Use |
|------|-----|
| `garmin.v_users` | User dropdown variable |
| `garmin.v_daily_metrics` | Recovery / wellness time series (HRV, sleep, stress, steps, etc.) |
| `garmin.v_activities` | Workout history |
| `garmin.v_body_composition` | Weight and body composition |
| `garmin.v_sync_log` | Sync job history |

Views apply automatically on app restart after the migration runs. Example Grafana panel query:

```sql
SELECT time, hrv_last_night, hrv_weekly_avg, sleep_score, resting_hr
FROM garmin.v_daily_metrics
WHERE user_id = ${user:singlequote}
  AND $__timeFilter(date)
ORDER BY time
```

User variable query: `SELECT user_id FROM garmin.v_users`.

### Dashboards

Import JSON from `grafana/` (Dashboards → Import). All use datasource UID `ffmyrywbxaq68e` and `${user:singlequote}` — remap on import if your Postgres UID differs.

| File | Title | Default range |
|------|-------|---------------|
| `recovery-dashboard.json` | Garmin Recovery | Last 1 year |
| `activity-dashboard.json` | Garmin Activity | Last 1 year |
| `body-composition-dashboard.json` | Garmin Body Composition | Last 1 year |
| `sync-health-dashboard.json` | Garmin Sync Health | Last 90 days |

Create a read-only Postgres user for Grafana scoped to the `garmin` schema.

## Manual sync

```bash
curl -X POST http://host:8080/sync
curl -X POST "http://host:8080/sync?start_date=2026-05-01&end_date=2026-05-23"
curl -X POST "http://host:8080/sync?user_id=user2&start_date=2026-05-23"
curl http://host:8080/health
```

Returns `{"status":"started","start_date":"...","end_date":"...","sync_log_id":...}` for one user, or `{"status":"started","sync_log_ids":{"user1":1,"user2":2}}` when syncing all. Optional query params:

- `user_id` — sync a single account
- `start_date` — first day to fetch (defaults to today)
- `end_date` — last day to fetch (defaults to `start_date`)

If a sync is already running: HTTP 409 and `{"status":"already_running"}`.
