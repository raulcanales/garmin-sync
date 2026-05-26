"""REST endpoints for LLM / n8n tool consumption."""

from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import llm_db

router = APIRouter(prefix="/tools", tags=["llm-tools"])

NoteCategory = Literal[
    "injury", "preference", "schedule", "pr", "equipment", "general"
]
GoalStatus = Literal["active", "completed", "abandoned"]
PlannedStatus = Literal["planned", "completed", "skipped", "modified"]


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": message})


def _not_found(message: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": message})


def _handle_value_error(e: ValueError) -> JSONResponse:
    msg = str(e)
    if msg.startswith("unknown user_id") or msg.startswith("unknown telegram_id"):
        return _not_found(msg)
    return _bad_request(msg)


@router.get("/user-by-telegram")
async def get_user_by_telegram(
    telegram_id: int = Query(..., gt=0, description="Telegram user id from the trigger."),
):
    """Resolve internal user_id (and nickname) for a Telegram account.

    Call once per n8n execution, then pass user_id to all other /tools endpoints.
    """
    try:
        user = await llm_db.resolve_user_by_telegram_id(telegram_id)
        return user
    except ValueError as e:
        return _handle_value_error(e)


class SaveGoalBody(BaseModel):
    user_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=500)
    goal_id: int | None = Field(
        default=None, description="Set to update an existing goal."
    )
    description: str | None = None
    target_date: date | None = None
    status: GoalStatus = "active"
    metadata: dict[str, Any] | None = None


class SaveNoteBody(BaseModel):
    user_id: int = Field(..., gt=0)
    content: str = Field(..., min_length=1)
    category: NoteCategory = "general"
    supersedes_id: int | None = Field(
        default=None,
        description="Mark this note id inactive and replace it.",
    )


class SavePlannedWorkoutBody(BaseModel):
    user_id: int = Field(..., gt=0)
    planned_date: date
    prescription: str = Field(..., min_length=1)
    workout_id: int | None = Field(
        default=None, description="Set to update an existing planned workout."
    )
    workout_type: str | None = None
    status: PlannedStatus = "planned"
    linked_activity_id: str | None = None
    notes: str | None = None


class UpdatePlannedStatusBody(BaseModel):
    user_id: int = Field(..., gt=0)
    status: PlannedStatus
    linked_activity_id: str | None = None
    notes: str | None = None


@router.get("/recovery-snapshot")
async def get_recovery_snapshot(
    user_id: int = Query(..., gt=0, description="Internal user id (see GET /users)."),
    on_date: date | None = Query(
        default=None,
        alias="date",
        description="Day to summarize (YYYY-MM-DD). Defaults to today (UTC).",
    ),
):
    """Recovery and readiness for one day plus a 7-day HRV/sleep trend."""
    try:
        return await llm_db.get_recovery_snapshot(user_id, on_date)
    except ValueError as e:
        return _handle_value_error(e)


@router.get("/daily-metrics")
async def get_daily_metrics(
    user_id: int = Query(..., gt=0),
    start_date: date = Query(..., description="First day (YYYY-MM-DD)."),
    end_date: date | None = Query(
        default=None, description="Last day inclusive. Defaults to start_date."
    ),
):
    """Wellness time series: sleep, HRV, stress, body battery, training load."""
    end = end_date or start_date
    if start_date > end:
        return _bad_request("start_date cannot be after end_date")
    try:
        rows = await llm_db.get_daily_metrics(user_id, start_date, end)
        return {"user_id": user_id, "start_date": start_date.isoformat(), "end_date": end.isoformat(), "days": rows}
    except ValueError as e:
        return _handle_value_error(e)


@router.get("/session-summaries")
async def get_recent_session_summaries(
    user_id: int = Query(..., gt=0),
    limit: int = Query(default=14, ge=1, le=100),
    activity_type: str | None = Query(
        default=None,
        description="Filter by Garmin activity type, e.g. street_running or strength_training.",
    ),
):
    """Recent completed activities (compact summaries)."""
    try:
        sessions = await llm_db.get_recent_session_summaries(
            user_id, limit, activity_type
        )
        return {"user_id": user_id, "count": len(sessions), "sessions": sessions}
    except ValueError as e:
        return _handle_value_error(e)


@router.get("/activities/{activity_id}")
async def get_activity(
    activity_id: str,
    user_id: int = Query(..., gt=0),
):
    """Single activity with type-specific detail (splits, HR zones, strength sets)."""
    try:
        detail = await llm_db.get_activity(user_id, activity_id)
    except ValueError as e:
        return _handle_value_error(e)
    if detail is None:
        return _not_found(f"activity {activity_id} not found for user {user_id}")
    return {"user_id": user_id, "activity_id": activity_id, **detail}


@router.get("/strength-progression")
async def get_strength_progression(
    user_id: int = Query(..., gt=0),
    exercise_name: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
):
    """Recent sets for one exercise (weight/reps over time)."""
    try:
        sets = await llm_db.get_strength_progression(user_id, exercise_name, limit)
        return {
            "user_id": user_id,
            "exercise_name": exercise_name,
            "count": len(sets),
            "sets": sets,
        }
    except ValueError as e:
        return _handle_value_error(e)


@router.get("/body-composition")
async def get_body_composition(
    user_id: int = Query(..., gt=0),
    limit: int = Query(default=30, ge=1, le=365),
):
    """Recent weight and body composition measurements."""
    try:
        rows = await llm_db.get_body_composition(user_id, limit)
        return {"user_id": user_id, "count": len(rows), "measurements": rows}
    except ValueError as e:
        return _handle_value_error(e)


@router.get("/goals")
async def get_goals(
    user_id: int = Query(..., gt=0),
    status: str | None = Query(
        default="active",
        description="Filter by status, or omit (pass empty) for all.",
    ),
):
    """Training goals for the athlete."""
    try:
        filter_status = status if status else None
        goals = await llm_db.list_goals(user_id, filter_status)
        return {"user_id": user_id, "count": len(goals), "goals": goals}
    except ValueError as e:
        return _handle_value_error(e)


@router.post("/goals")
async def save_goal(body: SaveGoalBody):
    """Create or update a training goal."""
    try:
        goal = await llm_db.save_goal(
            body.user_id,
            body.title,
            goal_id=body.goal_id,
            description=body.description,
            target_date=body.target_date,
            status=body.status,
            metadata=body.metadata,
        )
        return {"goal": goal}
    except ValueError as e:
        return _handle_value_error(e)


@router.get("/notes")
async def get_athlete_notes(
    user_id: int = Query(..., gt=0),
    category: NoteCategory | None = Query(default=None),
    include_inactive: bool = Query(default=False),
):
    """Persistent coach notes (injuries, preferences, schedule, PRs)."""
    try:
        notes = await llm_db.list_athlete_notes(
            user_id, category, include_inactive
        )
        return {"user_id": user_id, "count": len(notes), "notes": notes}
    except ValueError as e:
        return _handle_value_error(e)


@router.post("/notes")
async def save_athlete_note(body: SaveNoteBody):
    """Save a coach note; optionally supersede a previous note."""
    try:
        note = await llm_db.save_athlete_note(
            body.user_id,
            body.content,
            category=body.category,
            supersedes_id=body.supersedes_id,
        )
        return {"note": note}
    except ValueError as e:
        return _handle_value_error(e)


@router.get("/planned-workouts")
async def get_planned_workout(
    user_id: int = Query(..., gt=0),
    on_date: date | None = Query(
        default=None,
        alias="date",
        description="Single day lookup (YYYY-MM-DD).",
    ),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Planned workout for one day, or a date range."""
    try:
        if on_date is not None:
            workout = await llm_db.get_planned_workout(user_id, on_date)
            return {
                "user_id": user_id,
                "date": on_date.isoformat(),
                "workout": workout,
            }
        if start_date is None:
            start_date = datetime.now(timezone.utc).date()
        end = end_date or start_date
        if start_date > end:
            return _bad_request("start_date cannot be after end_date")
        workouts = await llm_db.list_planned_workouts(user_id, start_date, end)
        return {
            "user_id": user_id,
            "start_date": start_date.isoformat(),
            "end_date": end.isoformat(),
            "count": len(workouts),
            "workouts": workouts,
        }
    except ValueError as e:
        return _handle_value_error(e)


@router.post("/planned-workouts")
async def save_planned_workout(body: SavePlannedWorkoutBody):
    """Save or update a planned workout prescription."""
    try:
        workout = await llm_db.save_planned_workout(
            body.user_id,
            body.planned_date,
            body.prescription,
            workout_id=body.workout_id,
            workout_type=body.workout_type,
            status=body.status,
            linked_activity_id=body.linked_activity_id,
            notes=body.notes,
        )
        return {"workout": workout}
    except ValueError as e:
        return _handle_value_error(e)


@router.patch("/planned-workouts/{workout_id}")
async def update_planned_workout_status(
    workout_id: int,
    body: UpdatePlannedStatusBody,
):
    """Mark a planned workout completed, skipped, or modified."""
    try:
        workout = await llm_db.update_planned_workout_status(
            body.user_id,
            workout_id,
            body.status,
            linked_activity_id=body.linked_activity_id,
            notes=body.notes,
        )
        return {"workout": workout}
    except ValueError as e:
        return _handle_value_error(e)
