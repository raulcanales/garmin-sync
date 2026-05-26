import copy
import json
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from garminconnect import Garmin
from garminconnect.exceptions import GarminConnectAuthenticationError

from users import UserConfig

logger = logging.getLogger(__name__)

DATE_FMT = "%Y-%m-%d"
ACTIVITY_PAGE = 100
DAY_PAUSE_SEC = 0.2
EXERCISES_FILE = Path(__file__).resolve().parent / "exercises.json"
GARMIN_TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S.0"

_exercises_cache: list[dict[str, Any]] | None = None


class LoginStatus(str, Enum):
    SUCCESS = "success"
    MFA_REQUIRED = "mfa_required"
    FAILED = "failed"


@dataclass(frozen=True)
class LoginResult:
    status: LoginStatus
    tokens: str | None = None
    error: str | None = None


def date_range(since: date, until: date | None = None) -> list[date]:
    end = until or datetime.now().date()
    days: list[date] = []
    d = since
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def extract_tokens(client: Garmin) -> str:
    return client.client.dumps()


def _validate_tokens(raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise GarminConnectAuthenticationError("Invalid token JSON") from e
    if not isinstance(data, dict) or not data.get("di_token"):
        raise GarminConnectAuthenticationError("Token payload missing di_token")


def collect_tokens(client: Garmin, token_dir: str) -> str:
    """Read tokens written by garminconnect, falling back to in-memory dumps()."""
    token_path = Path(token_dir) / "garmin_tokens.json"
    if token_path.is_file():
        raw = token_path.read_text(encoding="utf-8").strip()
        if raw:
            _validate_tokens(raw)
            return raw
    raw = extract_tokens(client)
    _validate_tokens(raw)
    return raw


def _translate_auth_error(e: Exception) -> Exception:
    msg = str(e).lower()
    if "429" in str(e) or "rate limit" in msg:
        return GarminConnectAuthenticationError(
            "Garmin rate-limited this IP (429). Wait 30–60 minutes before "
            "retrying; avoid repeated login attempts."
        )
    return e


def garmin_login(user: UserConfig) -> Garmin:
    """Restore a Garmin session from tokens stored in the database."""
    if not user.tokens:
        raise GarminConnectAuthenticationError(
            f"No saved tokens for {user.nickname}. Log in at /login first."
        )
    _validate_tokens(user.tokens)
    token_dir = tempfile.mkdtemp(prefix="garmin-sync-")
    token_path = Path(token_dir) / "garmin_tokens.json"
    try:
        token_path.write_text(user.tokens, encoding="utf-8")
        client = Garmin(is_cn=False)
        mfa_status, _ = client.login(tokenstore=token_dir)
    except GarminConnectAuthenticationError as e:
        shutil.rmtree(token_dir, ignore_errors=True)
        raise _translate_auth_error(e) from e
    except Exception:
        shutil.rmtree(token_dir, ignore_errors=True)
        raise
    shutil.rmtree(token_dir, ignore_errors=True)
    if mfa_status:
        raise GarminConnectAuthenticationError(
            f"Garmin MFA required for {user.nickname}. Log in again at /login."
        )
    return client


def start_garmin_login(email: str, password: str) -> tuple[Garmin, str, LoginResult]:
    """Start credential login. Returns (client, token_dir, result).

    When MFA is required the client must be kept alive and completed via
    ``finish_garmin_login``.
    """
    token_dir = tempfile.mkdtemp(prefix="garmin-sync-")
    client = Garmin(email, password, is_cn=False, return_on_mfa=True)
    try:
        pending, _ = client.login(tokenstore=token_dir)
        if pending:
            return client, token_dir, LoginResult(status=LoginStatus.MFA_REQUIRED)
        tokens = collect_tokens(client, token_dir)
        shutil.rmtree(token_dir, ignore_errors=True)
        return client, token_dir, LoginResult(status=LoginStatus.SUCCESS, tokens=tokens)
    except GarminConnectAuthenticationError as e:
        shutil.rmtree(token_dir, ignore_errors=True)
        translated = _translate_auth_error(e)
        return client, token_dir, LoginResult(status=LoginStatus.FAILED, error=str(translated))
    except Exception as e:
        shutil.rmtree(token_dir, ignore_errors=True)
        return client, token_dir, LoginResult(status=LoginStatus.FAILED, error=str(e))


def finish_garmin_login(client: Garmin, token_dir: str, mfa_code: str) -> LoginResult:
    """Complete an in-progress MFA login started with ``start_garmin_login``."""
    try:
        client.resume_login(None, mfa_code.strip())
        tokens = collect_tokens(client, token_dir)
        return LoginResult(status=LoginStatus.SUCCESS, tokens=tokens)
    except Exception as e:
        return LoginResult(status=LoginStatus.FAILED, error=str(e))
    finally:
        shutil.rmtree(token_dir, ignore_errors=True)


def _activity_date(activity: dict[str, Any]) -> date | None:
    for key in ("startTimeLocal", "startTimeGMT", "beginTimestamp"):
        val = activity.get(key)
        if not val:
            continue
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val / 1000).date()
        s = str(val)[:10]
        try:
            return datetime.strptime(s, DATE_FMT).date()
        except ValueError:
            continue
    return None


def _activity_id(activity: dict[str, Any]) -> str | None:
    for key in ("activityId", "activity_id", "id"):
        val = activity.get(key)
        if val is not None:
            return str(val)
    return None


def _activity_type(activity: dict[str, Any]) -> str | None:
    at = activity.get("activityType")
    if isinstance(at, dict):
        key = at.get("typeKey")
        if key is not None:
            return str(key)
    return None


def _row_date(d: date, payload: Any, source_id: str | None = None) -> dict[str, Any]:
    return {"date": d, "source_id": source_id, "data": payload}


def _is_empty_payload(payload: Any) -> bool:
    if payload is None:
        return True
    if isinstance(payload, dict):
        return not payload
    if isinstance(payload, list):
        return not payload
    return False


def fetch_activities(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    end = until or datetime.now().date()
    logger.info("fetch_activities: range %s..%s", since, end)
    try:
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = client.get_activities(start, ACTIVITY_PAGE)
            if not batch:
                break
            if isinstance(batch, dict):
                items = batch.get("activities") or batch.get("activityList") or []
            else:
                items = batch
            if not items:
                break
            stop = False
            for activity in items:
                if not isinstance(activity, dict):
                    continue
                ad = _activity_date(activity)
                if ad is not None and ad < since:
                    stop = True
                    continue
                if ad is not None and ad > end:
                    continue
                aid = _activity_id(activity)
                if ad is None:
                    ad = since
                row = _row_date(ad, activity, aid)
                row["activity_type"] = _activity_type(activity)
                rows.append(row)
            if stop or len(items) < ACTIVITY_PAGE:
                break
            start += ACTIVITY_PAGE
            time.sleep(DAY_PAUSE_SEC)
        logger.info("fetch_activities: %d in range", len(rows))
        return rows
    except Exception as e:
        logger.exception("fetch activities: %s", e)
        return []


def _fetch_per_day(
    client: Garmin,
    since: date,
    fetcher: Any,
    until: date | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    days = date_range(since, until)
    name = getattr(fetcher, "__name__", repr(fetcher))
    if not days:
        logger.info("%s: no days in range", name)
        return rows
    logger.info("%s: %d days (%s..%s)", name, len(days), days[0], days[-1])
    try:
        for i, d in enumerate(days, start=1):
            ds = d.isoformat()
            try:
                payload = fetcher(ds)
            except Exception as e:
                logger.warning("fetch %s %s: %s", name, ds, e)
                payload = None
            if _is_empty_payload(payload):
                time.sleep(DAY_PAUSE_SEC)
                continue
            rows.append(_row_date(d, payload))
            time.sleep(DAY_PAUSE_SEC)
            if len(days) > 1 and (i == 1 or i == len(days) or i % 7 == 0):
                logger.info("%s: day %d/%s (%s)", name, i, len(days), ds)
    except Exception as e:
        logger.exception("fetch per day: %s", e)
    logger.info("%s: %d/%d days with data", name, len(rows), len(days))
    return rows


def fetch_sleep(client: Garmin, since: date, until: date | None = None) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_sleep_data, until)


def fetch_daily_summary(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_stats_and_body, until)


def fetch_body_battery(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_body_battery, until)


def fetch_hrv(client: Garmin, since: date, until: date | None = None) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_hrv_data, until)


def fetch_heart_rate(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_heart_rates, until)


def fetch_stress(client: Garmin, since: date, until: date | None = None) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_stress_data, until)


def fetch_floors(client: Garmin, since: date, until: date | None = None) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_floors, until)


def fetch_training_readiness(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_training_readiness, until)


def fetch_morning_training_readiness(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_morning_training_readiness, until)


def fetch_training_status(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_training_status, until)


def fetch_max_metrics(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    return _fetch_per_day(client, since, client.get_max_metrics, until)


def _body_comp_row(item: dict[str, Any], fallback: date) -> dict[str, Any]:
    d = fallback
    for key in ("date", "calendarDate", "measurementTime", "timestamp"):
        val = item.get(key)
        if not val:
            continue
        s = str(val)[:10]
        try:
            d = datetime.strptime(s, DATE_FMT).date()
            break
        except ValueError:
            continue
    sid = None
    for key in ("samplePk", "id", "weightId", "measurementId"):
        val = item.get(key)
        if val is not None:
            sid = str(val)
            break
    return _row_date(d, item, sid)


def fetch_body_composition(
    client: Garmin, since: date, until: date | None = None
) -> list[dict[str, Any]]:
    try:
        end = until or datetime.now().date()
        logger.info("fetch_body_composition: range %s..%s", since, end)
        raw = client.get_body_composition(since.isoformat(), end.isoformat())
        rows: list[dict[str, Any]] = []
        if raw is None:
            pass
        elif isinstance(raw, list):
            rows = [_body_comp_row(x, since) for x in raw if isinstance(x, dict)]
        elif isinstance(raw, dict):
            for key in ("dateWeightList", "weightRangeDTOS", "items", "data"):
                chunk = raw.get(key)
                if isinstance(chunk, list):
                    rows = [
                        _body_comp_row(x, since) for x in chunk if isinstance(x, dict)
                    ]
                    break
            else:
                rows = [_body_comp_row(raw, since)]
        logger.info("fetch_body_composition: %d records", len(rows))
        return rows
    except Exception as e:
        logger.exception("fetch body composition: %s", e)
        return []


def _flatten_exercise_catalog(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    categories = raw.get("categories")
    if not isinstance(categories, dict):
        return rows
    for category, cat_data in categories.items():
        if not isinstance(cat_data, dict):
            continue
        exercises = cat_data.get("exercises")
        if not isinstance(exercises, dict):
            continue
        for exercise_name, details in exercises.items():
            row: dict[str, Any] = {
                "category": category,
                "exerciseName": exercise_name,
            }
            if isinstance(details, dict):
                if details.get("primaryMuscles"):
                    row["primaryMuscles"] = details["primaryMuscles"]
                if details.get("secondaryMuscles"):
                    row["secondaryMuscles"] = details["secondaryMuscles"]
            rows.append(row)
    rows.sort(key=lambda r: (r["category"], r["exerciseName"]))
    return rows


def load_exercise_catalog() -> list[dict[str, Any]]:
    """Load strength exercise catalog from bundled exercises.json."""
    global _exercises_cache
    if _exercises_cache is not None:
        return _exercises_cache

    if not EXERCISES_FILE.is_file():
        raise FileNotFoundError(f"exercise catalog not found: {EXERCISES_FILE}")

    logger.info("load_exercise_catalog: reading %s", EXERCISES_FILE)
    with EXERCISES_FILE.open(encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("unexpected exercise catalog format")
    rows = _flatten_exercise_catalog(raw)
    logger.info("load_exercise_catalog: %d exercises", len(rows))
    _exercises_cache = rows
    return rows


def filter_exercise_catalog(
    rows: list[dict[str, Any]],
    *,
    q: str | None = None,
    category: str | None = None,
    limit: int = 0,
) -> list[dict[str, Any]]:
    filtered = rows
    if category is not None:
        cat = category.strip().upper()
        filtered = [r for r in filtered if r["category"] == cat]
    if q is not None:
        needle = q.strip().lower()
        if needle:
            filtered = [
                r
                for r in filtered
                if needle in r["category"].lower()
                or needle in r["exerciseName"].lower()
            ]
    if limit > 0:
        filtered = filtered[:limit]
    return filtered


def _clean_workout_step_ids(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _clean_workout_step_ids(item)
    elif isinstance(node, dict):
        node.pop("stepId", None)
        for value in node.values():
            if isinstance(value, list | dict):
                _clean_workout_step_ids(value)


def prepare_workout_for_upload(workout: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of workout JSON suitable for Garmin upload."""
    payload = copy.deepcopy(workout)
    for field in ("workoutId", "ownerId", "updatedDate", "createdDate"):
        payload.pop(field, None)
    timestamp = datetime.now().strftime(GARMIN_TIMESTAMP_FMT)
    payload["createdDate"] = timestamp
    payload["updatedDate"] = timestamp
    if "workoutSegments" in payload:
        _clean_workout_step_ids(payload["workoutSegments"])
    return payload


def validate_workout_payload(workout: dict[str, Any]) -> None:
    if not workout.get("workoutName"):
        raise ValueError("workoutName is required")
    if not workout.get("workoutSegments"):
        raise ValueError("workoutSegments is required")
    if not isinstance(workout["workoutSegments"], list):
        raise ValueError("workoutSegments must be a list")


def create_workout(
    client: Garmin,
    workout: dict[str, Any],
    schedule_date: date | None = None,
) -> dict[str, Any]:
    validate_workout_payload(workout)
    payload = prepare_workout_for_upload(workout)
    result = client.upload_workout(payload)
    if not isinstance(result, dict):
        raise ValueError("unexpected upload_workout response")
    workout_id = result.get("workoutId")
    out: dict[str, Any] = {"workout": result, "workoutId": workout_id}
    if schedule_date is not None:
        if workout_id is None:
            raise ValueError("upload succeeded but workoutId missing; cannot schedule")
        scheduled = client.schedule_workout(workout_id, schedule_date.isoformat())
        out["scheduled"] = scheduled
        out["scheduleDate"] = schedule_date.isoformat()
    return out
