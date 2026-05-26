# garmin-sync

On-demand Garmin Connect → PostgreSQL sync with `GET /health` and `POST /sync`. No API auth (personal LAN / Unraid). Register Garmin accounts via a web login page; tokens and user profiles live in Postgres.

Synced tables (JSONB payloads): `activities`, `activity_details`, `sleep`, `daily_summary`, `body_battery`, `hrv`, `heart_rate`, `stress`, `body_composition`, `floors`, `training_readiness`, `morning_training_readiness`, `training_status`, `max_metrics`.

After each activity sync, running and strength workouts are enriched via Garmin detail APIs (`split_summaries`, `hr_zones`, `exercise_sets`).

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | yes | — | PostgreSQL DSN (`postgresql://user:pass@host:5432/db`) |

Append `?sslmode=require` to `DATABASE_URL` if your Postgres host requires SSL.

Garmin credentials are **not** configured via environment variables. Use `GET /login` or the API below.

## Users and login

Each account has:

- **user_id** — auto-increment integer primary key (internal)
- **nickname** — slug you choose (e.g. `raal`, `partner`); used in Grafana and workout URLs
- **name** — display name from the login page
- **date_of_birth** — date from the login page
- **gender** — `male` or `female`
- **telegram_id** — optional Telegram user id
- **email** — Garmin Connect email
- **tokens** — DI OAuth tokens stored in `garmin.users` after login (passwords are never stored)

### Web login (recommended)

Open `/login` after the app starts, fill in nickname, name, date of birth, gender, email, and password. If Garmin sends an MFA code, enter it on the same page.

```bash
./scripts/local-login.sh
# or open http://localhost:8080/login
```

### API login

Register a new user and log in:

```bash
curl -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  -d '{"nickname":"raal","name":"Raal","date_of_birth":"1990-01-15","gender":"male","email":"you@example.com","password":"your-garmin-password"}'
```

If MFA is required:

```json
{"status":"mfa_required","login_id":"…","nickname":"raal","message":"…"}
```

Complete MFA:

```bash
curl -X POST http://localhost:8080/users/raal/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"your-garmin-password","login_id":"…","mfa_code":"123456"}'
```

Re-login an existing user (refresh tokens):

```bash
curl -X POST http://localhost:8080/users/raal/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"your-garmin-password"}'
```

List users:

```bash
curl http://localhost:8080/users
curl http://localhost:8080/health
```

Bind a Telegram id to an existing user (by `nickname`):

```bash
curl -X PATCH http://localhost:8080/users/raal/telegram \
  -H 'Content-Type: application/json' \
  -d '{"telegram_id":123456789}'
```

## Local testing (Mac / Linux)

Bundled Postgres is enabled with the `local` profile. Unraid production uses your external database only (no `local` profile).

### 1. Configure database (optional)

```bash
cp .env.example .env   # optional — compose defaults to bundled Postgres
```

### 2. Build and start

```bash
./scripts/local-up.sh
```

Or manually:

```bash
docker compose --profile local build
docker compose --profile local up -d
```

### 3. Register Garmin account(s)

```bash
./scripts/local-login.sh
```

When prompted for MFA, enter the code from your email. Tokens are saved in Postgres.

If you see **429 / rate limited**, Garmin temporarily blocked login from your IP — usually from too many attempts. Wait **30–60 minutes**, then retry once.

To force re-login, clear tokens for a user:

```bash
docker compose --profile local exec postgres psql -U garmin -d garmin \
  -c "UPDATE garmin.users SET tokens = NULL WHERE nickname = 'raal';"
```

### 4. Verify

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/sync
curl -X POST "http://localhost:8080/sync?telegram_id=123456789"
curl -X POST "http://localhost:8080/sync?start_date=2026-05-01&end_date=2026-05-23"
```

Watch logs:

```bash
docker compose --profile local logs -f garmin-sync
```

Inspect the database (optional):

```bash
docker compose --profile local exec postgres psql -U garmin -d garmin -c "SELECT user_id, nickname, name, email, tokens IS NOT NULL AS logged_in FROM garmin.users;"
docker compose --profile local exec postgres psql -U garmin -d garmin -c "SELECT sl.id, u.nickname, sl.status, sl.finished_at, sl.items_fetched FROM garmin.sync_log sl JOIN garmin.users u ON u.user_id = sl.user_id ORDER BY sl.id DESC LIMIT 10;"
```

Without date parameters, sync fetches **today only**. Pass `start_date` and optionally `end_date` (YYYY-MM-DD) to backfill a range.

### 5. Stop / reset

```bash
./scripts/local-down.sh
```

Remove DB volume and start fresh:

```bash
docker compose --profile local down -v
```

## Unraid (Compose Manager)

Do **not** use `--profile local` on Unraid — use your external Postgres only.

Use `docker-compose-unraid.yml` (host port **8081** — **8080** is often Immich on the same box).

1. Clone or copy this repo to the Unraid host.
2. Set `DATABASE_URL` to your external Postgres instance in Compose Manager env.
3. Import `docker-compose-unraid.yml`.
4. Start the container, open `http://<host>:8081/login`, and register each Garmin account.

Schema `garmin` and tables are created on startup from SQL migrations in `migrations/`.

## Database migrations

Schema changes live in numbered SQL files under `migrations/` (e.g. `001_initial_schema.sql`). Pending migrations are applied automatically on app startup and recorded in `garmin.schema_migrations`.

To add a schema change:

1. Create the next file, e.g. `migrations/005_add_foo.sql`.
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
| `./scripts/local-login.sh` | Open the web login page |
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

## LLM / n8n tools

HTTP endpoints under `/tools` expose Garmin data and coach state (goals, notes, planned workouts) for LLM agents. See **[LLM_TOOLS.md](LLM_TOOLS.md)** for tool names, paths, and n8n wiring.

`GET /users` and `GET /health` include `user_id` for each registered account.

## Grafana views

`001_initial_schema.sql` creates tables, the `garmin.users` registry, and read-only Grafana views. `002_activity_enrichment.sql` adds `activity_details` and type-specific activity views.

| View | Use |
|------|-----|
| `garmin.v_users` | User dropdown (`nickname`, `name`, `logged_in`, …) |
| `garmin.v_daily_metrics` | Recovery / wellness time series (HRV, sleep, stress, steps, etc.) |
| `garmin.v_activities` | Cross-type workout summary (duration, HR, training load, sets/reps when present) |
| `garmin.v_running` | Running-specific metrics + splits / HR zones |
| `garmin.v_strength` | Strength summary + compact `exercises_summary` |
| `garmin.v_strength_sets` | One row per strength set (exercise, reps, weight) |
| `garmin.v_body_composition` | Weight and body composition |
| `garmin.v_sync_log` | Sync job history |

Example Grafana panel query:

```sql
SELECT time, hrv_last_night, hrv_weekly_avg, sleep_score, resting_hr
FROM garmin.v_daily_metrics
WHERE nickname = ${user:singlequote}
  AND $__timeFilter(date)
ORDER BY time
```

User variable query: `SELECT nickname, name FROM garmin.v_users ORDER BY nickname`.

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
curl -X POST http://host:8081/sync
curl -X POST "http://host:8081/sync?start_date=2026-05-01&end_date=2026-05-23"
curl -X POST "http://host:8081/sync?telegram_id=123456789&start_date=2026-05-23"
curl http://host:8081/health
curl "http://host:8081/exercises?q=squat&limit=10"
```

Returns `{"status":"started","start_date":"...","end_date":"...","telegram_id":123456789,"sync_log_id":...}` for one user, or `{"status":"started","sync_log_ids":{"123456789":1,"987654321":2}}` when syncing all. Optional query params:

- `telegram_id` — sync a single account (must be registered on the user; see `GET /users`)
- `start_date` — first day to fetch (defaults to today)
- `end_date` — last day to fetch (defaults to `start_date`)

If a sync is already running: HTTP 409 and `{"status":"already_running"}`.

On startup, any `sync_log` rows still marked `running` (e.g. after a crash) are closed as `failed` with error `interrupted: service restarted`. When a sync finishes, `items_fetched` stores each table’s latest `synced_at` for that user (not row counts from the Garmin fetch).

## Fresh database

After a schema change that rewrites `001_initial_schema.sql`, wipe Postgres and re-register users:

```bash
docker compose --profile local down -v
./scripts/local-up.sh
./scripts/local-login.sh
```
