import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Any

from garminconnect import Garmin
from garminconnect.exceptions import GarminConnectAuthenticationError

from users import UserConfig

logger = logging.getLogger(__name__)

DATE_FMT = "%Y-%m-%d"
ACTIVITY_PAGE = 100
DAY_PAUSE_SEC = 0.2


def date_range(since: date, until: date | None = None) -> list[date]:
    end = until or datetime.now().date()
    days: list[date] = []
    d = since
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _prompt_mfa() -> str:
    return input("Enter MFA code: ").strip()


def garmin_login(user: UserConfig) -> Garmin:
    os.makedirs(user.token_path, exist_ok=True)
    client = Garmin(user.email, user.password, is_cn=False, prompt_mfa=_prompt_mfa)
    try:
        mfa_status, _ = client.login(tokenstore=user.token_path)
    except GarminConnectAuthenticationError as e:
        msg = str(e).lower()
        if "429" in str(e) or "rate limit" in msg:
            raise GarminConnectAuthenticationError(
                "Garmin rate-limited this IP (429). Wait 30–60 minutes before "
                "retrying; avoid repeated login attempts."
            ) from e
        raise
    if mfa_status:
        client.resume_login(mfa_status, _prompt_mfa())
    return client


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
