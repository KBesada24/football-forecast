"""Read-only lineup recommendations from prepared, versioned weekly projections."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from src.api.dependencies import DatabaseSession
from src.db.models import Game, LineupSnapshot
from src.domain.lineup import DEFAULT_SLOTS, LineupRequest, optimize

router = APIRouter(prefix="/lineups", tags=["lineups"])


def current_snapshot(session, season, week):
    return session.scalar(
        select(LineupSnapshot)
        .where(LineupSnapshot.season == season, LineupSnapshot.week == week)
        .order_by(LineupSnapshot.generated_at.desc(), LineupSnapshot.snapshot_id.desc())
        .limit(1)
    )


def locked(session, payload):
    now = datetime.now(UTC)
    if now >= datetime.fromisoformat(payload["first_kickoff"]):
        return True
    games = session.scalars(
        select(Game).where(
            Game.season == payload["season"], Game.week == payload["week"], Game.game_type == "REG"
        )
    )
    return any(
        not g.game_datetime or g.game_datetime <= now or g.game_status != "upcoming" for g in games
    )


@router.get("/week")
def week_data(
    session: DatabaseSession, season: int = Query(ge=2024, le=2100), week: int = Query(ge=1, le=18)
):
    snapshot = current_snapshot(session, season, week)
    latest = session.scalar(
        select(LineupSnapshot).order_by(LineupSnapshot.generated_at.desc()).limit(1)
    )
    suggested = {"season": latest.season, "week": latest.week} if latest else None
    if snapshot is None:
        return {
            "status": "unavailable",
            "season": season,
            "week": week,
            "suggested_week": suggested,
            "players": [],
            "default_slots": DEFAULT_SLOTS,
        }
    return {
        **snapshot.payload,
        "status": "locked" if locked(session, snapshot.payload) else "ready",
        "suggested_week": suggested,
        "default_slots": DEFAULT_SLOTS,
    }


@router.post("/optimize")
def recommend(request: LineupRequest, session: DatabaseSession):
    snapshot = current_snapshot(session, request.season, request.week)
    if snapshot is None:
        raise HTTPException(
            409, "No prepared projections for this week. Choose the next upcoming week."
        )
    if request.snapshot_id and request.snapshot_id != snapshot.snapshot_id:
        raise HTTPException(
            409, "Weekly data changed. Refresh the page before recommending a lineup."
        )
    if locked(session, snapshot.payload):
        raise HTTPException(
            409,
            "This week has started. Saved recommendations remain viewable; "
            "new recommendations are disabled.",
        )
    try:
        result = optimize(request, snapshot.payload["players"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        **result,
        "season": request.season,
        "week": request.week,
        "snapshot_id": snapshot.snapshot_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_as_of": snapshot.payload["data_as_of"],
        "first_kickoff": snapshot.payload["first_kickoff"],
        "scoring_version": snapshot.payload["scoring_version"],
        "notice": snapshot.payload["notice"],
    }
