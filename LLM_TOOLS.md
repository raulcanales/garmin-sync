# LLM tools (n8n / agent HTTP)

REST endpoints under `/tools` for an LLM coach agent. All tools take **`user_id`** (integer from `GET /users` or `GET /health`). No API auth — restrict to your LAN/VPN like the rest of garmin-sync.

Base URL examples: `http://localhost:8080` (local) or `http://<host>:8081` (Unraid).

OpenAPI schema: `GET /docs` (FastAPI).

**n8n pattern:** Telegram gives you `telegram_id`, not `user_id`. Call **`get_user_by_telegram`** once at the start of the workflow, then pass `user_id` to every other tool. You do not need `telegram_id` on the other endpoints.

---

## User lookup (call first in n8n)

### `get_user_by_telegram`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/user-by-telegram` |
| **Query** | `telegram_id` (required) |

**Description:** Maps a Telegram user id to the internal `user_id` used everywhere else. Also returns `nickname`, `name`, and whether Garmin is logged in.

**Example:**
```http
GET /tools/user-by-telegram?telegram_id=123456789
```

```json
{
  "user_id": 1,
  "nickname": "raal",
  "name": "Raal",
  "telegram_id": 123456789,
  "logged_in": true
}
```

If the telegram id is not bound to any account: HTTP 404.

Bind via `PATCH /users/{nickname}/telegram` or at registration.

---

## Garmin data (read)

### `get_recovery_snapshot`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/recovery-snapshot` |
| **Query** | `user_id` (required), `date` (optional, YYYY-MM-DD, default today UTC) |

**Description:** Recovery and readiness for one day: sleep score/hours, HRV (last night vs weekly avg and baseline band), resting HR, stress, body battery high/low, training readiness (current + morning), training status, weekly load, VO2 max, steps, intensity minutes. Includes a **prior 7 days** mini-trend (HRV, sleep score, resting HR, training readiness).

**Use when:** “How am I doing?”, “Can I train hard today?”, before prescribing intensity.

**Example:**
```http
GET /tools/recovery-snapshot?user_id=1
GET /tools/recovery-snapshot?user_id=1&date=2026-05-25
```

---

### `get_daily_metrics`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/daily-metrics` |
| **Query** | `user_id`, `start_date`, `end_date` (optional; defaults to `start_date`) |

**Description:** Wellness time series over a date range (same core fields as recovery snapshot, plus calories, distance, stress duration buckets, floors, etc.). Days ordered newest first.

**Use when:** Weekly/monthly trends, comparing sleep or HRV across a block.

---

### `get_recent_session_summaries`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/session-summaries` |
| **Query** | `user_id`, `limit` (default 14, max 100), `activity_type` (optional) |

**Description:** Recent completed activities: date, name, type, duration, distance, calories, HR, elevation, training load/TSS, aerobic/anaerobic TE, sets/reps for strength.

**Use when:** Conversation start, “what have I done lately?”, context before commenting on training.

---

### `get_activity`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/activities/{activity_id}` |
| **Query** | `user_id` |

**Description:** One activity in depth. Always includes `summary`. Running types add `running` (pace, cadence, splits, HR zones). Strength adds `strength` summary plus per-set `sets` (exercise, reps, weight kg).

**Use when:** “How was my run yesterday?”, analyzing a specific session. `activity_id` is Garmin’s activity id from session summaries.

---

### `get_strength_progression`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/strength-progression` |
| **Query** | `user_id`, `exercise_name` (substring match, case-insensitive), `limit` (default 20) |

**Description:** Recent sets for one exercise across workouts (date, reps, weight).

**Use when:** “Am I progressing on squat?”, load recommendations for lifting.

---

### `get_body_composition`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/body-composition` |
| **Query** | `user_id`, `limit` (default 30) |

**Description:** Recent weight (kg), body fat %, muscle mass, etc.

**Use when:** Weight trend questions (not moralizing — factual data only).

---

## Coach state (read/write)

Stored in Postgres (`garmin.goals`, `garmin.athlete_notes`, `garmin.planned_workouts`). Applied via migration `005_coach_state.sql` on startup.

### `get_goals`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/goals` |
| **Query** | `user_id`, `status` (default `active`; use empty string for all) |

**Description:** Training goals (title, description, target date, status, metadata JSON).

---

### `save_goal`

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/tools/goals` |
| **Body** | JSON |

**Description:** Create or update a goal. Set `goal_id` to update.

```json
{
  "user_id": 1,
  "title": "Sub-45 10K",
  "description": "Copenhagen race in September",
  "target_date": "2026-09-15",
  "status": "active",
  "metadata": { "target_time_min": 45 }
}
```

---

### `get_athlete_notes`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/notes` |
| **Query** | `user_id`, `category` (optional: `injury`, `preference`, `schedule`, `pr`, `equipment`, `general`), `include_inactive` (default false) |

**Description:** Persistent notes the coach should remember.

---

### `save_athlete_note`

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/tools/notes` |
| **Body** | JSON |

**Description:** Add a note. Pass `supersedes_id` to deactivate an older note (e.g. injury resolved).

```json
{
  "user_id": 1,
  "category": "injury",
  "content": "Mild left knee pain on downhill — avoid aggressive descents for 2 weeks.",
  "supersedes_id": null
}
```

---

### `get_planned_workout`

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tools/planned-workouts` |
| **Query** | **Single day:** `user_id`, `date`. **Range:** `user_id`, `start_date`, optional `end_date` |

**Description:** Prescription the coach saved for a day (type, free-text prescription, status, link to completed Garmin activity id).

---

### `save_planned_workout`

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/tools/planned-workouts` |
| **Body** | JSON |

**Description:** Save or update a planned session. Set `workout_id` to update.

```json
{
  "user_id": 1,
  "planned_date": "2026-05-27",
  "workout_type": "easy_run",
  "prescription": "45 min easy, Z2 HR, flat route. RPE 3-4.",
  "status": "planned"
}
```

---

### `update_planned_workout_status`

| | |
|---|---|
| **Method** | `PATCH` |
| **Path** | `/tools/planned-workouts/{workout_id}` |
| **Body** | JSON |

**Description:** Mark planned workout `completed`, `skipped`, or `modified`. Optionally link the Garmin `activity_id` from a completed session.

```json
{
  "user_id": 1,
  "status": "completed",
  "linked_activity_id": "12345678901",
  "notes": "Cut short — felt heavy legs"
}
```

---

## Resolving `user_id` (alternatives)

| Approach | When |
|----------|------|
| `GET /tools/user-by-telegram?telegram_id=…` | **n8n / Telegram** — one lookup per run |
| `GET /users` or `GET /health` | Manual setup, Grafana, non-Telegram flows |

---

## n8n wiring tips

1. **First node:** `GET /tools/user-by-telegram?telegram_id={{ $('Telegram Trigger').item.json.message.from.id }}` (adjust to your trigger shape).
2. Store `user_id` from the response; pass it as `user_id` on every later HTTP Request.
3. Prefer **GET** for reads; **POST**/**PATCH** for writes with `Content-Type: application/json`.
4. On **404** / empty `today` in recovery snapshot, data may be missing — run `POST /sync` first or widen sync date range.
5. Tool names in agent prompts map to paths below (snake_case → kebab-case).

| Tool name (agent) | HTTP |
|-------------------|------|
| `get_user_by_telegram` | `GET /tools/user-by-telegram` |
| `get_recovery_snapshot` | `GET /tools/recovery-snapshot` |
| `get_daily_metrics` | `GET /tools/daily-metrics` |
| `get_recent_session_summaries` | `GET /tools/session-summaries` |
| `get_activity` | `GET /tools/activities/{activity_id}` |
| `get_strength_progression` | `GET /tools/strength-progression` |
| `get_body_composition` | `GET /tools/body-composition` |
| `get_goals` | `GET /tools/goals` |
| `save_goal` | `POST /tools/goals` |
| `get_athlete_notes` | `GET /tools/notes` |
| `save_athlete_note` | `POST /tools/notes` |
| `get_planned_workout` | `GET /tools/planned-workouts` |
| `save_planned_workout` | `POST /tools/planned-workouts` |
| `update_planned_workout_status` | `PATCH /tools/planned-workouts/{workout_id}` |

---

## Related (not under `/tools`)

| Endpoint | Purpose |
|----------|---------|
| `POST /sync` | Pull fresh Garmin data into Postgres |
| `GET /exercises` | Garmin strength exercise catalog (for building workouts) |
| `POST /workouts` | Upload workout to Garmin Connect |
