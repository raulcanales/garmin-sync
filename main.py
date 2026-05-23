import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import db
import garmin_client
import migrations
from users import UserConfig, load_users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

sync_lock = asyncio.Lock()
_sync_running = False

FETCHERS: list[tuple[str, str]] = [
    ("activities", "fetch_activities"),
    ("sleep", "fetch_sleep"),
    ("daily_summary", "fetch_daily_summary"),
    ("body_battery", "fetch_body_battery"),
    ("hrv", "fetch_hrv"),
    ("heart_rate", "fetch_heart_rate"),
    ("stress", "fetch_stress"),
    ("body_composition", "fetch_body_composition"),
    ("floors", "fetch_floors"),
    ("training_readiness", "fetch_training_readiness"),
    ("morning_training_readiness", "fetch_morning_training_readiness"),
    ("training_status", "fetch_training_status"),
    ("max_metrics", "fetch_max_metrics"),
]


def _find_user(user_id: str) -> UserConfig | None:
    for user in load_users():
        if user.user_id == user_id:
            return user
    return None


def _resolve_sync_range(
    start_date: date | None, end_date: date | None
) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    start = start_date or today
    end = end_date or start
    if start > end:
        raise ValueError("start_date cannot be after end_date")
    return start, end


async def _sync_user(
    user: UserConfig,
    start_date: date,
    end_date: date,
    log_id: int | None = None,
) -> int:
    owned_log = log_id is None
    if log_id is None:
        log_id = await db.start_sync_log(user.user_id)
    errors: list[str] = []
    items: dict[str, int] = {}
    status = "failed"
    try:
        logger.info(
            "sync %s user=%s range %s..%s",
            log_id,
            user.user_id,
            start_date,
            end_date,
        )
        try:
            logger.info(
                "sync %s user=%s connecting to Garmin", log_id, user.user_id
            )
            client = await asyncio.to_thread(garmin_client.garmin_login, user)
            logger.info(
                "sync %s user=%s Garmin connected, fetching %d data types",
                log_id,
                user.user_id,
                len(FETCHERS),
            )
        except Exception as e:
            logger.exception("garmin login failed for %s", user.user_id)
            await db.finish_sync_log(log_id, "failed", items, str(e))
            return log_id
        ok_types = 0
        for i, (table, func_name) in enumerate(FETCHERS, start=1):
            try:
                logger.info(
                    "sync %s user=%s [%d/%d] fetching %s",
                    log_id,
                    user.user_id,
                    i,
                    len(FETCHERS),
                    table,
                )
                fetcher = getattr(garmin_client, func_name)
                rows = await asyncio.to_thread(
                    fetcher, client, start_date, end_date
                )
                n = await db.upsert_batch(user.user_id, table, rows)
                items[table] = n
                ok_types += 1
                logger.info(
                    "sync %s user=%s %s: fetched %d, stored %d",
                    log_id,
                    user.user_id,
                    table,
                    len(rows),
                    n,
                )
            except Exception as e:
                msg = f"{table}: {e}"
                logger.exception(
                    "sync %s user=%s failed %s", log_id, user.user_id, table
                )
                errors.append(msg)
        if ok_types == 0:
            status = "failed"
        elif errors:
            status = "partial"
        else:
            status = "success"
        err_text = "; ".join(errors) if errors else None
        logger.info(
            "sync %s user=%s finished status=%s stored=%s%s",
            log_id,
            user.user_id,
            status,
            items,
            f" errors={err_text}" if err_text else "",
        )
        await db.finish_sync_log(log_id, status, items, err_text)
    except Exception as e:
        logger.exception("sync %s user=%s aborted", log_id, user.user_id)
        if owned_log or log_id is not None:
            await db.finish_sync_log(log_id, "failed", items, str(e))
    return log_id


async def run_sync(
    user_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    log_ids: dict[str, int] | None = None,
) -> dict[str, int]:
    global _sync_running
    start, end = _resolve_sync_range(start_date, end_date)
    users = load_users()
    if user_id is not None:
        user = _find_user(user_id)
        if user is None:
            raise ValueError(f"unknown user_id: {user_id}")
        users = [user]

    if _sync_running:
        if log_ids:
            for uid, lid in log_ids.items():
                await db.finish_sync_log(lid, "failed", {}, "sync already running")
        return log_ids or {}
    async with sync_lock:
        if _sync_running:
            if log_ids:
                for uid, lid in log_ids.items():
                    await db.finish_sync_log(
                        lid, "failed", {}, "sync already running"
                    )
            return log_ids or {}
        _sync_running = True
        user_ids = [u.user_id for u in users]
        logger.info(
            "sync job started users=%s range %s..%s",
            user_ids,
            start,
            end,
        )
        results: dict[str, int] = {}
        try:
            for user in users:
                lid = (log_ids or {}).get(user.user_id)
                results[user.user_id] = await _sync_user(user, start, end, lid)
        finally:
            _sync_running = False
            logger.info("sync job finished users=%s log_ids=%s", user_ids, results)
        return results


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = datetime.now(timezone.utc)
    app.state.users = [u.user_id for u in load_users()]
    await migrations.run_migrations()
    yield
    await db.close_pool()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    started: datetime = app.state.started_at
    uptime = (datetime.now(timezone.utc) - started).total_seconds()
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "users": app.state.users,
    }


@app.post("/sync")
async def trigger_sync(
    user_id: str | None = Query(
        default=None,
        description="Sync one user (user1, user2). Omit to sync all configured users.",
    ),
    start_date: date | None = Query(
        default=None,
        description="First day to sync (YYYY-MM-DD). Defaults to today.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Last day to sync (YYYY-MM-DD). Defaults to start_date.",
    ),
):
    try:
        start, end = _resolve_sync_range(start_date, end_date)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"status": "invalid_range", "error": str(e)})
    if _sync_running or sync_lock.locked():
        return JSONResponse(
            status_code=409,
            content={"status": "already_running"},
        )
    if user_id is not None and _find_user(user_id) is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "unknown_user",
                "user_id": user_id,
                "configured_users": app.state.users,
            },
        )
    users = load_users() if user_id is None else [_find_user(user_id)]
    log_ids = {
        user.user_id: await db.start_sync_log(user.user_id) for user in users if user
    }
    asyncio.create_task(run_sync(user_id, start_date, end_date, log_ids))
    payload: dict[str, object] = {
        "status": "started",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    if len(log_ids) == 1:
        uid, lid = next(iter(log_ids.items()))
        payload["user_id"] = uid
        payload["sync_log_id"] = lid
    else:
        payload["sync_log_ids"] = log_ids
    return payload
