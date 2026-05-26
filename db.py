import json
import os
from datetime import date, datetime, timezone
from typing import Any

import asyncpg

from users import Gender, UserConfig

SCHEMA = "garmin"

TABLES: dict[str, str] = {
    "activities": "source_id",
    "sleep": "date",
    "daily_summary": "date",
    "body_battery": "date",
    "hrv": "date",
    "heart_rate": "date",
    "stress": "date",
    "body_composition": "body_composition",
    "floors": "date",
    "training_readiness": "date",
    "morning_training_readiness": "date",
    "training_status": "date",
    "max_metrics": "date",
}

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        url = os.environ["DATABASE_URL"]
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def upsert_batch(user_id: int, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    key = TABLES[table]
    pool = await get_pool()
    count = 0
    async with pool.acquire() as conn:
        for row in rows:
            d = row["date"]
            sid = row.get("source_id")
            data = row["data"]
            if isinstance(data, str):
                payload = data
            else:
                payload = json.dumps(data)
            if key == "source_id":
                if table == "activities":
                    await conn.execute(
                        f"""
                        INSERT INTO {SCHEMA}.{table}
                          (user_id, date, source_id, data, activity_type)
                        VALUES ($1, $2, $3, $4::jsonb, $5)
                        ON CONFLICT (user_id, source_id) WHERE source_id IS NOT NULL
                        DO UPDATE SET
                          data = EXCLUDED.data,
                          activity_type = EXCLUDED.activity_type,
                          synced_at = now()
                        """,
                        user_id,
                        d,
                        sid,
                        payload,
                        row.get("activity_type"),
                    )
                else:
                    await conn.execute(
                        f"""
                        INSERT INTO {SCHEMA}.{table} (user_id, date, source_id, data)
                        VALUES ($1, $2, $3, $4::jsonb)
                        ON CONFLICT (user_id, source_id) WHERE source_id IS NOT NULL
                        DO UPDATE SET data = EXCLUDED.data, synced_at = now()
                        """,
                        user_id,
                        d,
                        sid,
                        payload,
                    )
            elif key == "body_composition":
                if sid:
                    await conn.execute(
                        f"""
                        INSERT INTO {SCHEMA}.{table} (user_id, date, source_id, data)
                        VALUES ($1, $2, $3, $4::jsonb)
                        ON CONFLICT (user_id, source_id) WHERE source_id IS NOT NULL
                        DO UPDATE SET data = EXCLUDED.data, synced_at = now()
                        """,
                        user_id,
                        d,
                        sid,
                        payload,
                    )
                else:
                    await conn.execute(
                        f"""
                        INSERT INTO {SCHEMA}.{table} (user_id, date, source_id, data)
                        VALUES ($1, $2, NULL, $3::jsonb)
                        ON CONFLICT (user_id, date) WHERE source_id IS NULL
                        DO UPDATE SET data = EXCLUDED.data, synced_at = now()
                        """,
                        user_id,
                        d,
                        payload,
                    )
            else:
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.{table} (user_id, date, source_id, data)
                    VALUES ($1, $2, NULL, $3::jsonb)
                    ON CONFLICT (user_id, date) WHERE source_id IS NULL
                    DO UPDATE SET data = EXCLUDED.data, synced_at = now()
                    """,
                    user_id,
                    d,
                    payload,
                )
            count += 1
    return count


async def upsert_activity_details(
    user_id: int, rows: list[dict[str, Any]]
) -> int:
    if not rows:
        return 0
    pool = await get_pool()
    count = 0
    async with pool.acquire() as conn:
        for row in rows:
            data = row["data"]
            payload = data if isinstance(data, str) else json.dumps(data)
            await conn.execute(
                f"""
                INSERT INTO {SCHEMA}.activity_details
                  (user_id, date, source_id, activity_type, data)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (user_id, source_id)
                DO UPDATE SET
                  date = EXCLUDED.date,
                  activity_type = EXCLUDED.activity_type,
                  data = EXCLUDED.data,
                  synced_at = now()
                """,
                user_id,
                row["date"],
                row["source_id"],
                row.get("activity_type"),
                payload,
            )
            count += 1
    return count


_SYNC_COVERAGE_TABLES = (*TABLES.keys(), "activity_details")


async def get_user_sync_coverage(user_id: int) -> dict[str, str]:
    """Latest synced_at per data table for a user (ISO timestamps)."""
    pool = await get_pool()
    coverage: dict[str, str] = {}
    for table in _SYNC_COVERAGE_TABLES:
        row = await pool.fetchrow(
            f"""
            SELECT max(synced_at) AS latest
            FROM {SCHEMA}.{table}
            WHERE user_id = $1
            """,
            user_id,
        )
        latest = row["latest"] if row else None
        if latest is not None:
            coverage[table] = latest.isoformat()
    return coverage


async def start_sync_log(user_id: int) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        INSERT INTO {SCHEMA}.sync_log (user_id, started_at, status)
        VALUES ($1, $2, 'running')
        RETURNING id
        """,
        user_id,
        datetime.now(timezone.utc),
    )
    return int(row["id"])


async def finish_sync_log(
    log_id: int,
    status: str,
    error: str | None,
) -> None:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"SELECT user_id FROM {SCHEMA}.sync_log WHERE id = $1",
        log_id,
    )
    if row is None:
        return
    coverage = await get_user_sync_coverage(int(row["user_id"]))
    await pool.execute(
        f"""
        UPDATE {SCHEMA}.sync_log
        SET finished_at = $2, status = $3, items_fetched = $4::jsonb, error = $5
        WHERE id = $1
        """,
        log_id,
        datetime.now(timezone.utc),
        status,
        json.dumps(coverage),
        error,
    )


async def fail_stale_sync_logs(
    reason: str = "interrupted: service restarted",
) -> int:
    """Mark orphaned running sync_log rows as failed (e.g. after a crash)."""
    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT id, user_id
        FROM {SCHEMA}.sync_log
        WHERE status = 'running' AND finished_at IS NULL
        """
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        coverage = await get_user_sync_coverage(int(row["user_id"]))
        await pool.execute(
            f"""
            UPDATE {SCHEMA}.sync_log
            SET finished_at = $2, status = 'failed', items_fetched = $3::jsonb, error = $4
            WHERE id = $1
            """,
            row["id"],
            now,
            json.dumps(coverage),
            reason,
        )
    return len(rows)


def _tokens_to_str(tokens: Any) -> str | None:
    if tokens is None:
        return None
    if isinstance(tokens, str):
        return tokens
    return json.dumps(tokens, separators=(",", ":"))


def _row_to_user(row: asyncpg.Record) -> UserConfig:
    return UserConfig(
        user_id=int(row["user_id"]),
        nickname=row["nickname"],
        name=row["name"],
        email=row["email"],
        date_of_birth=row["date_of_birth"],
        gender=row["gender"],
        telegram_id=row["telegram_id"],
        tokens=_tokens_to_str(row["tokens"]),
    )


_USER_COLUMNS = """
  user_id, nickname, name, email, date_of_birth, gender, telegram_id, tokens
"""


async def list_users() -> list[UserConfig]:
    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT {_USER_COLUMNS}
        FROM {SCHEMA}.users
        ORDER BY nickname
        """
    )
    return [_row_to_user(row) for row in rows]


async def get_user_by_id(user_id: int) -> UserConfig | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT {_USER_COLUMNS}
        FROM {SCHEMA}.users
        WHERE user_id = $1
        """,
        user_id,
    )
    if row is None:
        return None
    return _row_to_user(row)


async def get_user(nickname: str) -> UserConfig | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT {_USER_COLUMNS}
        FROM {SCHEMA}.users
        WHERE nickname = $1
        """,
        nickname,
    )
    if row is None:
        return None
    return _row_to_user(row)


async def get_user_by_telegram_id(telegram_id: int) -> UserConfig | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT {_USER_COLUMNS}
        FROM {SCHEMA}.users
        WHERE telegram_id = $1
        """,
        telegram_id,
    )
    if row is None:
        return None
    return _row_to_user(row)


async def create_user(
    nickname: str,
    name: str,
    email: str,
    date_of_birth: date,
    gender: Gender,
    telegram_id: int | None = None,
) -> UserConfig:
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    row = await pool.fetchrow(
        f"""
        INSERT INTO {SCHEMA}.users (
          nickname, name, email, date_of_birth, gender, telegram_id,
          created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
        RETURNING {_USER_COLUMNS}
        """,
        nickname,
        name,
        email.strip().lower(),
        date_of_birth,
        gender,
        telegram_id,
        now,
    )
    return _row_to_user(row)


async def update_user_telegram_id(
    user_id: int, telegram_id: int | None
) -> UserConfig | None:
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    row = await pool.fetchrow(
        f"""
        UPDATE {SCHEMA}.users
        SET telegram_id = $2, updated_at = $3
        WHERE user_id = $1
        RETURNING {_USER_COLUMNS}
        """,
        user_id,
        telegram_id,
        now,
    )
    if row is None:
        return None
    return _row_to_user(row)


async def save_user_tokens(user_id: int, tokens: str) -> None:
    payload = json.loads(tokens)
    if not isinstance(payload, dict) or not payload.get("di_token"):
        raise ValueError("Refusing to save invalid Garmin token payload")

    pool = await get_pool()
    now = datetime.now(timezone.utc)
    result = await pool.execute(
        f"""
        UPDATE {SCHEMA}.users
        SET tokens = $2::jsonb, updated_at = $3, last_login_at = $3
        WHERE user_id = $1
        """,
        user_id,
        json.dumps(payload, separators=(",", ":")),
        now,
    )
    if result.split()[-1] != "1":
        raise RuntimeError(f"Failed to save tokens for user_id={user_id}")


async def clear_user_tokens(user_id: int) -> None:
    pool = await get_pool()
    await pool.execute(
        f"""
        UPDATE {SCHEMA}.users
        SET tokens = NULL, updated_at = $2
        WHERE user_id = $1
        """,
        user_id,
        datetime.now(timezone.utc),
    )


async def delete_user(nickname: str) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        f"DELETE FROM {SCHEMA}.users WHERE nickname = $1",
        nickname,
    )
    return result.endswith("1")
