"""Read/write queries for LLM tool endpoints."""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import asyncpg

from db import SCHEMA, get_pool

RECOVERY_FIELDS = """
  date,
  sleep_score,
  sleep_hours,
  deep_sleep_hours,
  rem_sleep_hours,
  hrv_last_night,
  hrv_weekly_avg,
  hrv_status,
  hrv_baseline_low,
  hrv_baseline_high,
  resting_hr,
  stress_avg,
  stress_max,
  body_battery_high,
  body_battery_low,
  body_battery_charged,
  body_battery_drained,
  training_readiness,
  morning_training_readiness,
  training_status,
  weekly_training_load,
  vo2_max,
  steps,
  vigorous_minutes,
  moderate_minutes
"""

DAILY_METRICS_FIELDS = RECOVERY_FIELDS + """,
  total_calories,
  active_calories,
  distance_km,
  max_hr,
  min_hr,
  restless_moments,
  avg_sleep_hr,
  avg_sleep_hrv,
  low_stress_minutes,
  medium_stress_minutes,
  high_stress_minutes,
  load_focus,
  floors_climbed
"""


def _json_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        if v == v.to_integral_value():
            return int(v)
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return v
    return v


def row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {k: _json_value(row[k]) for k in row.keys()}


async def _require_user(user_id: int) -> None:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"SELECT 1 FROM {SCHEMA}.users WHERE user_id = $1",
        user_id,
    )
    if row is None:
        raise ValueError(f"unknown user_id: {user_id}")


async def resolve_user_by_telegram_id(telegram_id: int) -> dict[str, Any]:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT user_id, nickname, name, telegram_id,
               (tokens IS NOT NULL) AS logged_in
        FROM {SCHEMA}.users
        WHERE telegram_id = $1
        """,
        telegram_id,
    )
    if row is None:
        raise ValueError(f"unknown telegram_id: {telegram_id}")
    return row_to_dict(row)


async def get_recovery_snapshot(
    user_id: int, on_date: date | None = None
) -> dict[str, Any]:
    await _require_user(user_id)
    target = on_date or datetime.now(timezone.utc).date()
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT {RECOVERY_FIELDS}
        FROM {SCHEMA}.v_daily_metrics
        WHERE user_id = $1 AND date = $2
        """,
        user_id,
        target,
    )
    prior_start = target - timedelta(days=7)
    prior_rows = await pool.fetch(
        f"""
        SELECT date, hrv_last_night, sleep_score, resting_hr, training_readiness
        FROM {SCHEMA}.v_daily_metrics
        WHERE user_id = $1 AND date >= $2 AND date < $3
        ORDER BY date DESC
        """,
        user_id,
        prior_start,
        target,
    )
    return {
        "date": target.isoformat(),
        "today": row_to_dict(row) if row else None,
        "prior_7_days": [row_to_dict(r) for r in prior_rows],
    }


async def get_daily_metrics(
    user_id: int, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    await _require_user(user_id)
    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT {DAILY_METRICS_FIELDS}
        FROM {SCHEMA}.v_daily_metrics
        WHERE user_id = $1 AND date >= $2 AND date <= $3
        ORDER BY date DESC
        """,
        user_id,
        start_date,
        end_date,
    )
    return [row_to_dict(r) for r in rows]


async def get_recent_session_summaries(
    user_id: int, limit: int = 14, activity_type: str | None = None
) -> list[dict[str, Any]]:
    await _require_user(user_id)
    pool = await get_pool()
    if activity_type:
        rows = await pool.fetch(
            f"""
            SELECT
              date,
              time,
              activity_type,
              activity_id,
              name,
              duration_min,
              distance_km,
              calories,
              avg_hr,
              max_hr,
              elevation_m,
              training_load,
              training_stress_score,
              aerobic_te,
              anaerobic_te,
              total_sets,
              total_reps
            FROM {SCHEMA}.v_activities
            WHERE user_id = $1 AND activity_type = $2
            ORDER BY time DESC NULLS LAST, date DESC
            LIMIT $3
            """,
            user_id,
            activity_type,
            limit,
        )
    else:
        rows = await pool.fetch(
            f"""
            SELECT
              date,
              time,
              activity_type,
              activity_id,
              name,
              duration_min,
              distance_km,
              calories,
              avg_hr,
              max_hr,
              elevation_m,
              training_load,
              training_stress_score,
              aerobic_te,
              anaerobic_te,
              total_sets,
              total_reps
            FROM {SCHEMA}.v_activities
            WHERE user_id = $1
            ORDER BY time DESC NULLS LAST, date DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    return [row_to_dict(r) for r in rows]


async def get_activity(user_id: int, activity_id: str) -> dict[str, Any] | None:
    await _require_user(user_id)
    pool = await get_pool()
    base = await pool.fetchrow(
        f"""
        SELECT *
        FROM {SCHEMA}.v_activities
        WHERE user_id = $1 AND activity_id = $2
        """,
        user_id,
        activity_id,
    )
    if base is None:
        return None
    activity_type = base["activity_type"]
    detail: dict[str, Any] = {"summary": row_to_dict(base)}
    if activity_type in (
        "street_running",
        "trail_running",
        "treadmill_running",
        "virtual_run",
        "indoor_running",
        "track_running",
        "running",
    ):
        run = await pool.fetchrow(
            f"""
            SELECT *
            FROM {SCHEMA}.v_running
            WHERE user_id = $1 AND activity_id = $2
            """,
            user_id,
            activity_id,
        )
        if run:
            detail["running"] = row_to_dict(run)
    elif activity_type == "strength_training":
        strength = await pool.fetchrow(
            f"""
            SELECT *
            FROM {SCHEMA}.v_strength
            WHERE user_id = $1 AND activity_id = $2
            """,
            user_id,
            activity_id,
        )
        sets = await pool.fetch(
            f"""
            SELECT set_order, exercise_name, category, reps, weight_kg, duration_s, set_type
            FROM {SCHEMA}.v_strength_sets
            WHERE user_id = $1 AND activity_id = $2
            ORDER BY set_order NULLS LAST
            """,
            user_id,
            activity_id,
        )
        if strength:
            detail["strength"] = row_to_dict(strength)
        detail["sets"] = [row_to_dict(s) for s in sets]
    return detail


async def get_strength_progression(
    user_id: int, exercise_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    await _require_user(user_id)
    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT
          date,
          time,
          activity_id,
          activity_name,
          set_order,
          exercise_name,
          reps,
          weight_kg
        FROM {SCHEMA}.v_strength_sets
        WHERE user_id = $1
          AND exercise_name ILIKE $2
        ORDER BY time DESC NULLS LAST, set_order DESC
        LIMIT $3
        """,
        user_id,
        exercise_name,
        limit,
    )
    return [row_to_dict(r) for r in rows]


async def get_body_composition(
    user_id: int, limit: int = 30
) -> list[dict[str, Any]]:
    await _require_user(user_id)
    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT date, weight_kg, body_fat_pct, body_water_pct, muscle_mass_g
        FROM {SCHEMA}.v_body_composition
        WHERE user_id = $1
        ORDER BY date DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [row_to_dict(r) for r in rows]


# --- Coach state ---


async def list_goals(
    user_id: int, status: str | None = "active"
) -> list[dict[str, Any]]:
    await _require_user(user_id)
    pool = await get_pool()
    if status:
        rows = await pool.fetch(
            f"""
            SELECT id, title, description, target_date, status, metadata,
                   created_at, updated_at
            FROM {SCHEMA}.goals
            WHERE user_id = $1 AND status = $2
            ORDER BY target_date NULLS LAST, created_at
            """,
            user_id,
            status,
        )
    else:
        rows = await pool.fetch(
            f"""
            SELECT id, title, description, target_date, status, metadata,
                   created_at, updated_at
            FROM {SCHEMA}.goals
            WHERE user_id = $1
            ORDER BY status, target_date NULLS LAST, created_at
            """,
            user_id,
        )
    return [row_to_dict(r) for r in rows]


async def save_goal(
    user_id: int,
    title: str,
    *,
    goal_id: int | None = None,
    description: str | None = None,
    target_date: date | None = None,
    status: str = "active",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await _require_user(user_id)
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    meta = json.dumps(metadata or {})
    if goal_id is not None:
        row = await pool.fetchrow(
            f"""
            UPDATE {SCHEMA}.goals
            SET title = $3, description = $4, target_date = $5,
                status = $6, metadata = $7::jsonb, updated_at = $8
            WHERE id = $1 AND user_id = $2
            RETURNING id, title, description, target_date, status, metadata,
                      created_at, updated_at
            """,
            goal_id,
            user_id,
            title,
            description,
            target_date,
            status,
            meta,
            now,
        )
    else:
        row = await pool.fetchrow(
            f"""
            INSERT INTO {SCHEMA}.goals
              (user_id, title, description, target_date, status, metadata, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING id, title, description, target_date, status, metadata,
                      created_at, updated_at
            """,
            user_id,
            title,
            description,
            target_date,
            status,
            meta,
            now,
        )
    if row is None:
        raise ValueError("goal not found or not owned by user")
    return row_to_dict(row)


async def list_athlete_notes(
    user_id: int, category: str | None = None, include_inactive: bool = False
) -> list[dict[str, Any]]:
    await _require_user(user_id)
    pool = await get_pool()
    clauses = ["user_id = $1"]
    args: list[Any] = [user_id]
    if not include_inactive:
        clauses.append("active = true")
    if category:
        args.append(category)
        clauses.append(f"category = ${len(args)}")
    where = " AND ".join(clauses)
    rows = await pool.fetch(
        f"""
        SELECT id, category, content, supersedes_id, active, created_at
        FROM {SCHEMA}.athlete_notes
        WHERE {where}
        ORDER BY created_at DESC
        """,
        *args,
    )
    return [row_to_dict(r) for r in rows]


async def save_athlete_note(
    user_id: int,
    content: str,
    *,
    category: str = "general",
    supersedes_id: int | None = None,
) -> dict[str, Any]:
    await _require_user(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if supersedes_id is not None:
                await conn.execute(
                    f"""
                    UPDATE {SCHEMA}.athlete_notes
                    SET active = false
                    WHERE id = $1 AND user_id = $2
                    """,
                    supersedes_id,
                    user_id,
                )
            row = await conn.fetchrow(
                f"""
                INSERT INTO {SCHEMA}.athlete_notes
                  (user_id, category, content, supersedes_id)
                VALUES ($1, $2, $3, $4)
                RETURNING id, category, content, supersedes_id, active, created_at
                """,
                user_id,
                category,
                content,
                supersedes_id,
            )
    return row_to_dict(row)


async def get_planned_workout(
    user_id: int, planned_date: date
) -> dict[str, Any] | None:
    await _require_user(user_id)
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT id, planned_date, status, workout_type, prescription,
               linked_activity_id, notes, created_at, updated_at
        FROM {SCHEMA}.planned_workouts
        WHERE user_id = $1 AND planned_date = $2
        ORDER BY
          CASE status
            WHEN 'planned' THEN 0
            WHEN 'modified' THEN 1
            ELSE 2
          END,
          updated_at DESC
        LIMIT 1
        """,
        user_id,
        planned_date,
    )
    return row_to_dict(row) if row else None


async def list_planned_workouts(
    user_id: int, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    await _require_user(user_id)
    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT id, planned_date, status, workout_type, prescription,
               linked_activity_id, notes, created_at, updated_at
        FROM {SCHEMA}.planned_workouts
        WHERE user_id = $1 AND planned_date >= $2 AND planned_date <= $3
        ORDER BY planned_date
        """,
        user_id,
        start_date,
        end_date,
    )
    return [row_to_dict(r) for r in rows]


async def save_planned_workout(
    user_id: int,
    planned_date: date,
    prescription: str,
    *,
    workout_id: int | None = None,
    workout_type: str | None = None,
    status: str = "planned",
    linked_activity_id: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    await _require_user(user_id)
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    if workout_id is not None:
        row = await pool.fetchrow(
            f"""
            UPDATE {SCHEMA}.planned_workouts
            SET planned_date = $3, prescription = $4, workout_type = $5,
                status = $6, linked_activity_id = $7, notes = $8, updated_at = $9
            WHERE id = $1 AND user_id = $2
            RETURNING id, planned_date, status, workout_type, prescription,
                      linked_activity_id, notes, created_at, updated_at
            """,
            workout_id,
            user_id,
            planned_date,
            prescription,
            workout_type,
            status,
            linked_activity_id,
            notes,
            now,
        )
    else:
        row = await pool.fetchrow(
            f"""
            INSERT INTO {SCHEMA}.planned_workouts
              (user_id, planned_date, prescription, workout_type, status,
               linked_activity_id, notes, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, planned_date, status, workout_type, prescription,
                      linked_activity_id, notes, created_at, updated_at
            """,
            user_id,
            planned_date,
            prescription,
            workout_type,
            status,
            linked_activity_id,
            notes,
            now,
        )
    if row is None:
        raise ValueError("planned workout not found or not owned by user")
    return row_to_dict(row)


async def update_planned_workout_status(
    user_id: int,
    workout_id: int,
    status: str,
    *,
    linked_activity_id: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    await _require_user(user_id)
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    row = await pool.fetchrow(
        f"""
        UPDATE {SCHEMA}.planned_workouts
        SET status = $3,
            linked_activity_id = COALESCE($4, linked_activity_id),
            notes = COALESCE($5, notes),
            updated_at = $6
        WHERE id = $1 AND user_id = $2
        RETURNING id, planned_date, status, workout_type, prescription,
                  linked_activity_id, notes, created_at, updated_at
        """,
        workout_id,
        user_id,
        status,
        linked_activity_id,
        notes,
        now,
    )
    if row is None:
        raise ValueError("planned workout not found or not owned by user")
    return row_to_dict(row)
