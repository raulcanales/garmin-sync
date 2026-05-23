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


