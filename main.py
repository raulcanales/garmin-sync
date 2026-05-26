import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, Query
from fastapi.responses import JSONResponse

import auth
import db
import garmin_client
import llm_router
import mcp_server
import migrations
from auth import BindTelegramBody, LoginUserBody, MfaCompleteBody, RegisterUserBody
from users import UserConfig

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


async def _find_user(nickname: str) -> UserConfig | None:
    return await db.get_user(nickname)


async def _find_user_by_telegram_id(telegram_id: int) -> UserConfig | None:
    return await db.get_user_by_telegram_id(telegram_id)


def _sync_log_key(user: UserConfig) -> str:
    if user.telegram_id is not None:
        return str(user.telegram_id)
    return user.nickname


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
    status = "failed"
    try:
        logger.info(
            "sync %s user=%s range %s..%s",
            log_id,
            user.nickname,
            start_date,
            end_date,
        )
        if not user.tokens:
            msg = f"{user.nickname} is not logged in — open /login first"
            logger.error("sync %s user=%s skipped: no tokens", log_id, user.nickname)
            await db.finish_sync_log(log_id, "failed", msg)
            return log_id
        try:
            logger.info(
                "sync %s user=%s connecting to Garmin", log_id, user.nickname
            )
            client = await asyncio.to_thread(garmin_client.garmin_login, user)
            logger.info(
                "sync %s user=%s Garmin connected, fetching %d data types",
                log_id,
                user.nickname,
                len(FETCHERS),
            )
        except Exception as e:
            logger.exception("garmin login failed for %s", user.nickname)
            await db.clear_user_tokens(user.user_id)
            await db.finish_sync_log(log_id, "failed", str(e))
            return log_id
        ok_types = 0
        for i, (table, func_name) in enumerate(FETCHERS, start=1):
            try:
                logger.info(
                    "sync %s user=%s [%d/%d] fetching %s",
                    log_id,
                    user.nickname,
                    i,
                    len(FETCHERS),
                    table,
                )
                fetcher = getattr(garmin_client, func_name)
                rows = await asyncio.to_thread(
                    fetcher, client, start_date, end_date
                )
                n = await db.upsert_batch(user.user_id, table, rows)
                if table == "activities" and rows:
                    detail_rows = await asyncio.to_thread(
                        garmin_client.fetch_activity_details, client, rows
                    )
                    await db.upsert_activity_details(user.user_id, detail_rows)
                ok_types += 1
                logger.info(
                    "sync %s user=%s %s: fetched %d, stored %d",
                    log_id,
                    user.nickname,
                    table,
                    len(rows),
                    n,
                )
            except Exception as e:
                msg = f"{table}: {e}"
                logger.exception(
                    "sync %s user=%s failed %s", log_id, user.nickname, table
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
            "sync %s user=%s finished status=%s%s",
            log_id,
            user.nickname,
            status,
            f" errors={err_text}" if err_text else "",
        )
        await db.finish_sync_log(log_id, status, err_text)
        try:
            tokens = garmin_client.extract_tokens(client)
            await db.save_user_tokens(user.user_id, tokens)
        except Exception:
            logger.exception("failed to persist refreshed tokens for %s", user.nickname)
    except Exception as e:
        logger.exception("sync %s user=%s aborted", log_id, user.nickname)
        if owned_log or log_id is not None:
            await db.finish_sync_log(log_id, "failed", str(e))
    return log_id


async def run_sync(
    telegram_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    log_ids: dict[str, int] | None = None,
) -> dict[str, int]:
    global _sync_running
    start, end = _resolve_sync_range(start_date, end_date)
    users = await db.list_users()
    if telegram_id is not None:
        user = await _find_user_by_telegram_id(telegram_id)
        if user is None:
            raise ValueError(f"unknown telegram_id: {telegram_id}")
        users = [user]

    if _sync_running:
        if log_ids:
            for _, lid in log_ids.items():
                await db.finish_sync_log(lid, "failed", "sync already running")
        return log_ids or {}
    async with sync_lock:
        if _sync_running:
            if log_ids:
                for _, lid in log_ids.items():
                    await db.finish_sync_log(
                        lid, "failed", "sync already running"
                    )
            return log_ids or {}
        _sync_running = True
        sync_keys = [_sync_log_key(u) for u in users]
        logger.info(
            "sync job started users=%s range %s..%s",
            sync_keys,
            start,
            end,
        )
        results: dict[str, int] = {}
        try:
            for user in users:
                key = _sync_log_key(user)
                lid = (log_ids or {}).get(key)
                results[key] = await _sync_user(user, start, end, lid)
        finally:
            _sync_running = False
            logger.info("sync job finished users=%s log_ids=%s", sync_keys, results)
        return results


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = datetime.now(timezone.utc)
    await migrations.run_migrations()
    stale = await db.fail_stale_sync_logs()
    if stale:
        logger.warning("marked %d stale sync_log row(s) as failed", stale)
    app.state.users = [u["nickname"] for u in await auth.list_users_public()]
    async with mcp_instance.session_manager.run():
        yield
    await db.close_pool()


app = FastAPI(lifespan=lifespan)
app.include_router(llm_router.router)
mcp_instance = mcp_server.setup_mcp(app)


@app.get("/health")
async def health():
    started: datetime = app.state.started_at
    uptime = (datetime.now(timezone.utc) - started).total_seconds()
    users = await auth.list_users_public()
    app.state.users = [u["nickname"] for u in users]
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "users": users,
        "mcp": "/mcp",
    }


@app.get("/login")
async def login_page():
    return auth.login_page()


@app.get("/users")
async def list_users():
    return {"users": await auth.list_users_public()}


@app.post("/users")
async def register_user(body: RegisterUserBody):
    return await auth.register_and_login(body)


@app.post("/users/{nickname}/login")
async def login_user(nickname: str, body: LoginUserBody):
    return await auth.login_existing_user(nickname, body)


@app.post("/users/login/mfa")
async def complete_mfa(body: MfaCompleteBody):
    return await auth.complete_mfa(body.login_id, body.mfa_code)


@app.patch("/users/{nickname}/telegram")
async def bind_user_telegram(nickname: str, body: BindTelegramBody):
    """Bind or update the Telegram user id for a registered account."""
    return await auth.bind_telegram(nickname, body)


@app.delete("/users/{nickname}")
async def remove_user(nickname: str):
    return await auth.delete_user(nickname)


@app.post("/sync")
async def trigger_sync(
    telegram_id: int | None = Query(
        default=None,
        description="Sync one user by Telegram id. Omit to sync all registered users.",
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
    if telegram_id is not None and await _find_user_by_telegram_id(telegram_id) is None:
        configured = [
            u["telegram_id"]
            for u in await auth.list_users_public()
            if u.get("telegram_id") is not None
        ]
        return JSONResponse(
            status_code=400,
            content={
                "status": "unknown_user",
                "telegram_id": telegram_id,
                "configured_telegram_ids": configured,
            },
        )
    users = (
        await db.list_users()
        if telegram_id is None
        else [await _find_user_by_telegram_id(telegram_id)]
    )
    log_ids = {
        _sync_log_key(user): await db.start_sync_log(user.user_id)
        for user in users
        if user
    }
    asyncio.create_task(run_sync(telegram_id, start_date, end_date, log_ids))
    payload: dict[str, object] = {
        "status": "started",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    if len(log_ids) == 1:
        user = users[0]
        payload["sync_log_id"] = next(iter(log_ids.values()))
        if user.telegram_id is not None:
            payload["telegram_id"] = user.telegram_id
        else:
            payload["nickname"] = user.nickname
    else:
        payload["sync_log_ids"] = log_ids
    return payload


@app.get("/exercises")
async def list_exercises(
    q: str | None = Query(
        default=None,
        description="Filter by substring in category or exerciseName (case-insensitive).",
    ),
    category: str | None = Query(
        default=None,
        description="Exact category key, e.g. SQUAT or BENCH_PRESS.",
    ),
    limit: int = Query(
        default=0,
        ge=0,
        le=10000,
        description="Max rows to return (0 = no limit).",
    ),
):
    """Garmin strength exercise catalog for building workout JSON.

    Each row has category and exerciseName — use both on strength workout steps.
    """
    try:
        rows = await asyncio.to_thread(garmin_client.load_exercise_catalog)
        filtered = garmin_client.filter_exercise_catalog(
            rows, q=q, category=category, limit=limit
        )
        return {
            "source": str(garmin_client.EXERCISES_FILE.name),
            "count": len(filtered),
            "total": len(rows),
            "exercises": filtered,
        }
    except Exception as e:
        logger.exception("list exercises failed")
        return JSONResponse(
            status_code=502,
            content={"status": "error", "error": str(e)},
        )


@app.post("/workouts")
async def create_workout(
    nickname: str = Query(
        ...,
        description="Registered user nickname slug (see GET /users).",
    ),
    schedule_date: date | None = Query(
        default=None,
        description="Optional calendar date (YYYY-MM-DD) to schedule the workout.",
    ),
    workout: dict[str, Any] = Body(
        ...,
        description="Garmin workout-service JSON (workoutName, sportType, workoutSegments, …).",
    ),
):
    """Upload a structured workout to Garmin Connect.

    Pass the workout body Garmin expects (see GET /exercises for valid exercise names).
    Optionally schedule it on a calendar date for the given user.
    """
    user = await _find_user(nickname)
    if user is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "unknown_user",
                "nickname": nickname,
                "configured_users": app.state.users,
            },
        )
    if not user.tokens:
        return JSONResponse(
            status_code=401,
            content={
                "status": "not_logged_in",
                "nickname": nickname,
                "message": "Open /login to connect this Garmin account first.",
            },
        )
    try:
        garmin_client.validate_workout_payload(workout)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "invalid_workout", "error": str(e)},
        )
    try:
        client = await asyncio.to_thread(garmin_client.garmin_login, user)
        result = await asyncio.to_thread(
            garmin_client.create_workout, client, workout, schedule_date
        )
        tokens = garmin_client.extract_tokens(client)
        await db.save_user_tokens(user.user_id, tokens)
        return {"status": "created", "nickname": nickname, **result}
    except Exception as e:
        logger.exception("create workout failed for %s", nickname)
        return JSONResponse(
            status_code=502,
            content={"status": "error", "error": str(e)},
        )
