import json
import os
from datetime import datetime, timezone
from typing import Any

import asyncpg

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


async def upsert_batch(user_id: str, table: str, rows: list[dict[str, Any]]) -> int:
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


async def start_sync_log(user_id: str) -> int:
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
    items_fetched: dict[str, int] | None,
    error: str | None,
) -> None:
    pool = await get_pool()
    await pool.execute(
        f"""
        UPDATE {SCHEMA}.sync_log
        SET finished_at = $2, status = $3, items_fetched = $4::jsonb, error = $5
        WHERE id = $1
        """,
        log_id,
        datetime.now(timezone.utc),
        status,
        json.dumps(items_fetched or {}),
        error,
    )


def _tokens_to_str(tokens: Any) -> str | None:
    if tokens is None:
        return None
    if isinstance(tokens, str):
        return tokens
    return json.dumps(tokens, separators=(",", ":"))


def _row_to_user(row: asyncpg.Record) -> "UserConfig":
    from users import UserConfig

    return UserConfig(
        user_id=row["user_id"],
        nickname=row["nickname"],
        email=row["email"],
        tokens=_tokens_to_str(row["tokens"]),
    )


async def list_users() -> list["UserConfig"]:
    from users import UserConfig

    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT user_id, nickname, email, tokens
        FROM {SCHEMA}.users
        ORDER BY nickname
        """
    )
    return [_row_to_user(row) for row in rows]


async def get_user(user_id: str) -> "UserConfig | None":
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT user_id, nickname, email, tokens
        FROM {SCHEMA}.users
        WHERE user_id = $1
        """,
        user_id,
    )
    if row is None:
        return None
    return _row_to_user(row)


async def create_user(user_id: str, nickname: str, email: str) -> "UserConfig":
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    row = await pool.fetchrow(
        f"""
        INSERT INTO {SCHEMA}.users (user_id, nickname, email, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $4)
        RETURNING user_id, nickname, email, tokens
        """,
        user_id,
        nickname,
        email.strip().lower(),
        now,
    )
    return _row_to_user(row)


async def update_user_profile(
    user_id: str, *, nickname: str | None = None, email: str | None = None
) -> "UserConfig | None":
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        UPDATE {SCHEMA}.users
        SET
          nickname = COALESCE($2, nickname),
          email = COALESCE($3, email),
          updated_at = $4
        WHERE user_id = $1
        RETURNING user_id, nickname, email, tokens
        """,
        user_id,
        nickname,
        email.strip().lower() if email else None,
        datetime.now(timezone.utc),
    )
    if row is None:
        return None
    return _row_to_user(row)


async def save_user_tokens(user_id: str, tokens: str) -> None:
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


async def clear_user_tokens(user_id: str) -> None:
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


async def delete_user(user_id: str) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        f"DELETE FROM {SCHEMA}.users WHERE user_id = $1",
        user_id,
    )
    return result.endswith("1")


