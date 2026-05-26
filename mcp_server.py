"""MCP tools for garmin-sync (calls llm_db directly).

Embedded in the main FastAPI app at ``/mcp`` (same port as REST).

Standalone stdio (Cursor only):
  python mcp_server.py --transport stdio
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from collections.abc import Awaitable
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

import llm_db
import migrations
from db import close_pool

logger = logging.getLogger(__name__)

NoteCategory = Literal[
    "injury", "preference", "schedule", "pr", "equipment", "general"
]
GoalStatus = Literal["active", "completed", "abandoned"]
PlannedStatus = Literal["planned", "completed", "skipped", "modified"]


def _parse_date(value: str | None, *, field: str = "date") -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"{field} must be YYYY-MM-DD") from e


async def _run(coro: Awaitable[Any]) -> Any:
    try:
        return await coro
    except ValueError as e:
        return {"error": str(e)}


@asynccontextmanager
async def _stdio_lifespan(_app: FastMCP):
    await migrations.run_migrations()
    try:
        yield
    finally:
        await close_pool()


def create_mcp(*, stdio: bool = False) -> FastMCP:
    return FastMCP(
        "garmin-sync",
        instructions=(
            "Garmin training data and coach state for one athlete. "
            "Resolve user_id via get_user_by_telegram (Telegram flows) or pass user_id "
            "from GET /users. All tools except get_user_by_telegram require user_id."
        ),
        streamable_http_path="/mcp",
        stateless_http=True,
        lifespan=_stdio_lifespan if stdio else None,
        # Same trust model as REST /tools: LAN/VPN, no auth. Default MCP settings
        # only allow localhost Host headers and reject 10.x / hostname access.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )


def setup_mcp(app) -> FastMCP:
    """Register MCP tools and attach POST /mcp on the main FastAPI app."""
    mcp = create_mcp()
    register_tools(mcp)
    for route in mcp.streamable_http_app().routes:
        app.router.routes.insert(0, route)

    logger.info("MCP ready at POST /mcp")
    return mcp


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_user_by_telegram(telegram_id: int) -> dict[str, Any]:
        """Map a Telegram user id to internal user_id, nickname, and login status."""
        user = await _run(llm_db.resolve_user_by_telegram_id(telegram_id))
        return user if isinstance(user, dict) else {"user": user}

    @mcp.tool()
    async def get_recovery_snapshot(
        user_id: int,
        date: str | None = None,
    ) -> dict[str, Any]:
        """Recovery and readiness for one day plus a 7-day trend (omit date for today UTC)."""
        try:
            on_date = _parse_date(date)
        except ValueError as e:
            return {"error": str(e)}
        result = await _run(llm_db.get_recovery_snapshot(user_id, on_date))
        return result if isinstance(result, dict) else {"data": result}

    @mcp.tool()
    async def get_daily_metrics(
        user_id: int,
        start_date: str,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Wellness time series between start_date and end_date (inclusive)."""
        try:
            start = _parse_date(start_date, field="start_date")
            if start is None:
                return {"error": "start_date is required"}
            end = _parse_date(end_date or start_date, field="end_date")
            if end is None:
                return {"error": "end_date is required"}
        except ValueError as e:
            return {"error": str(e)}
        if start > end:
            return {"error": "start_date cannot be after end_date"}
        rows = await _run(llm_db.get_daily_metrics(user_id, start, end))
        if isinstance(rows, dict) and "error" in rows:
            return rows
        return {
            "user_id": user_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": rows,
        }

    @mcp.tool()
    async def get_recent_session_summaries(
        user_id: int,
        limit: int = 14,
        activity_type: str | None = None,
    ) -> dict[str, Any]:
        """Recent completed activities (compact summaries)."""
        if limit < 1 or limit > 100:
            return {"error": "limit must be between 1 and 100"}
        sessions = await _run(
            llm_db.get_recent_session_summaries(user_id, limit, activity_type)
        )
        if isinstance(sessions, dict) and "error" in sessions:
            return sessions
        return {"user_id": user_id, "count": len(sessions), "sessions": sessions}

    @mcp.tool()
    async def get_activity(user_id: int, activity_id: str) -> dict[str, Any]:
        """One activity in depth (running splits/zones or strength sets)."""
        detail = await _run(llm_db.get_activity(user_id, activity_id))
        if isinstance(detail, dict) and "error" in detail:
            return detail
        if detail is None:
            return {
                "error": f"activity {activity_id} not found for user {user_id}",
            }
        return {"user_id": user_id, "activity_id": activity_id, **detail}

    @mcp.tool()
    async def get_strength_progression(
        user_id: int,
        exercise_name: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Recent sets for one exercise (weight/reps over time)."""
        if limit < 1 or limit > 200:
            return {"error": "limit must be between 1 and 200"}
        sets = await _run(
            llm_db.get_strength_progression(user_id, exercise_name, limit)
        )
        if isinstance(sets, dict) and "error" in sets:
            return sets
        return {
            "user_id": user_id,
            "exercise_name": exercise_name,
            "count": len(sets),
            "sets": sets,
        }

    @mcp.tool()
    async def get_body_composition(
        user_id: int,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Recent weight and body composition measurements."""
        if limit < 1 or limit > 365:
            return {"error": "limit must be between 1 and 365"}
        measurements = await _run(llm_db.get_body_composition(user_id, limit))
        if isinstance(measurements, dict) and "error" in measurements:
            return measurements
        return {
            "user_id": user_id,
            "count": len(measurements),
            "measurements": measurements,
        }

    @mcp.tool()
    async def get_goals(
        user_id: int,
        status: str = "active",
    ) -> dict[str, Any]:
        """Training goals (pass status='' for all statuses)."""
        filter_status = status if status else None
        goals = await _run(llm_db.list_goals(user_id, filter_status))
        if isinstance(goals, dict) and "error" in goals:
            return goals
        return {"user_id": user_id, "count": len(goals), "goals": goals}

    @mcp.tool()
    async def save_goal(
        user_id: int,
        title: str,
        goal_id: int | None = None,
        description: str | None = None,
        target_date: str | None = None,
        status: GoalStatus = "active",
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a training goal (metadata_json is a JSON object string)."""
        meta: dict[str, Any] | None = None
        if metadata_json:
            try:
                meta = json.loads(metadata_json)
                if not isinstance(meta, dict):
                    return {"error": "metadata_json must be a JSON object"}
            except json.JSONDecodeError:
                return {"error": "metadata_json is not valid JSON"}
        try:
            td = _parse_date(target_date, field="target_date")
        except ValueError as e:
            return {"error": str(e)}
        goal = await _run(
            llm_db.save_goal(
                user_id,
                title,
                goal_id=goal_id,
                description=description,
                target_date=td,
                status=status,
                metadata=meta,
            )
        )
        if isinstance(goal, dict) and "error" in goal:
            return goal
        return {"goal": goal}

    @mcp.tool()
    async def get_athlete_notes(
        user_id: int,
        category: NoteCategory | None = None,
        include_inactive: bool = False,
    ) -> dict[str, Any]:
        """Persistent coach notes (injuries, preferences, schedule, PRs)."""
        notes = await _run(
            llm_db.list_athlete_notes(user_id, category, include_inactive)
        )
        if isinstance(notes, dict) and "error" in notes:
            return notes
        return {"user_id": user_id, "count": len(notes), "notes": notes}

    @mcp.tool()
    async def save_athlete_note(
        user_id: int,
        content: str,
        category: NoteCategory = "general",
        supersedes_id: int | None = None,
    ) -> dict[str, Any]:
        """Save a coach note; optionally supersede a previous note."""
        note = await _run(
            llm_db.save_athlete_note(
                user_id,
                content,
                category=category,
                supersedes_id=supersedes_id,
            )
        )
        if isinstance(note, dict) and "error" in note:
            return note
        return {"note": note}

    @mcp.tool()
    async def get_planned_workout(
        user_id: int,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Planned workout for one day (date) or a date range (start_date/end_date)."""
        try:
            on_date = _parse_date(date)
        except ValueError as e:
            return {"error": str(e)}
        if on_date is not None:
            workout = await _run(llm_db.get_planned_workout(user_id, on_date))
            if isinstance(workout, dict) and "error" in workout:
                return workout
            return {
                "user_id": user_id,
                "date": on_date.isoformat(),
                "workout": workout,
            }
        try:
            start = _parse_date(start_date) or datetime.now(timezone.utc).date()
            end = _parse_date(end_date or start.isoformat()) or start
        except ValueError as e:
            return {"error": str(e)}
        if start > end:
            return {"error": "start_date cannot be after end_date"}
        workouts = await _run(llm_db.list_planned_workouts(user_id, start, end))
        if isinstance(workouts, dict) and "error" in workouts:
            return workouts
        return {
            "user_id": user_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "count": len(workouts),
            "workouts": workouts,
        }

    @mcp.tool()
    async def save_planned_workout(
        user_id: int,
        planned_date: str,
        prescription: str,
        workout_id: int | None = None,
        workout_type: str | None = None,
        status: PlannedStatus = "planned",
        linked_activity_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Save or update a planned workout prescription."""
        try:
            pd = _parse_date(planned_date, field="planned_date")
            if pd is None:
                return {"error": "planned_date is required"}
        except ValueError as e:
            return {"error": str(e)}
        workout = await _run(
            llm_db.save_planned_workout(
                user_id,
                pd,
                prescription,
                workout_id=workout_id,
                workout_type=workout_type,
                status=status,
                linked_activity_id=linked_activity_id,
                notes=notes,
            )
        )
        if isinstance(workout, dict) and "error" in workout:
            return workout
        return {"workout": workout}

    @mcp.tool()
    async def update_planned_workout_status(
        user_id: int,
        workout_id: int,
        status: PlannedStatus,
        linked_activity_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Mark a planned workout completed, skipped, or modified."""
        workout = await _run(
            llm_db.update_planned_workout_status(
                user_id,
                workout_id,
                status,
                linked_activity_id=linked_activity_id,
                notes=notes,
            )
        )
        if isinstance(workout, dict) and "error" in workout:
            return workout
        return {"workout": workout}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="garmin-sync MCP (stdio). HTTP MCP is served by main:app at /mcp."
    )
    parser.add_argument(
        "--transport",
        choices=("stdio",),
        default="stdio",
        help="Only stdio is supported here; use uvicorn main:app for HTTP /mcp",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if "DATABASE_URL" not in os.environ:
        parser.error("DATABASE_URL is required")

    mcp = create_mcp(stdio=True)
    register_tools(mcp)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
