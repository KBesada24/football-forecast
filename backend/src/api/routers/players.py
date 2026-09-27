from typing import Annotated, Literal

from fastapi import APIRouter, Query

from src.api import player_service as service
from src.api.dependencies import DatabaseSession
from src.api.schemas.players import (
    CurrentContext,
    DashboardResponse,
    HistoryResponse,
    OpponentResponse,
    PlayerSearchResponse,
    ProjectionResponse,
    RankingsResponse,
)

router = APIRouter(tags=["players"])
Season = Annotated[int, Query(ge=2009, le=2100)]
Week = Annotated[int, Query(ge=1, le=18)]


@router.get("/players/search", response_model=PlayerSearchResponse)
def search(session: DatabaseSession, q: Annotated[str, Query(min_length=2, max_length=100)]):
    return service.search(session, q)


@router.get("/meta/current-context", response_model=CurrentContext)
def context(session: DatabaseSession):
    return service.current_context(session)


@router.get("/rankings", response_model=RankingsResponse)
def rankings(
    session: DatabaseSession,
    season: Season,
    week: Week,
    position: Literal["RB", "WR", "TE"] | None = None,
):
    return service.rankings(session, season, week, position)


@router.get("/players/{player_id}/projection", response_model=ProjectionResponse)
def projection(player_id: str, session: DatabaseSession, season: Season, week: Week):
    return service.projection(session, player_id, season, week)


@router.get("/players/{player_id}/history", response_model=HistoryResponse)
def history(
    player_id: str,
    session: DatabaseSession,
    season: Season,
    week: Week,
    limit: Annotated[int, Query(ge=1, le=50)] = 8,
    include_selected_week: bool = False,
):
    return service.history(session, player_id, season, week, limit, include_selected_week)


@router.get("/players/{player_id}/vs-opponent", response_model=OpponentResponse)
def opponent(player_id: str, session: DatabaseSession, season: Season, week: Week):
    return service.versus_opponent(session, player_id, season, week)


@router.get("/players/{player_id}/dashboard", response_model=DashboardResponse)
def dashboard(
    player_id: str,
    session: DatabaseSession,
    season: Season,
    week: Week,
    include_selected_week: bool = False,
):
    return service.dashboard(session, player_id, season, week, include_selected_week)
