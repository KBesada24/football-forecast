from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PlayerInfo(DTO):
    player_id: str
    display_name: str
    position: str
    team: str | None = None
    headshot_url: str | None = None


class SearchPlayer(PlayerInfo):
    active: bool | None = None


class PlayerSearchResponse(DTO):
    results: list[SearchPlayer]


class TargetContext(DTO):
    season: int
    week: int


class Matchup(TargetContext):
    team_context_week: int | None = None
    opponent: str | None = None
    home_away: Literal["home", "away", "neutral"] | None = None
    game_id: str | None = None
    game_date: date | None = None
    game_date_time: datetime | None = None
    status: Literal["upcoming", "completed", "bye", "unavailable"] = "unavailable"


class Forecast(DTO):
    scoring_format: Literal["full_ppr"] = "full_ppr"
    scoring_version: str = "full_ppr_v1"
    projection_ppr: float | None = None
    baseline_projection_ppr: float | None = None
    recent_ppr_average4: float | None = Field(default=None, alias="recentPprAverage4")
    games_played_prior: int = 0
    eligible_games_prior: int = 0
    history_quality: Literal["none", "limited", "adequate"] = "none"
    model_name: str | None = None
    model_version: str | None = None
    training_data_end: TargetContext | None = None
    generated_at: datetime | None = None
    data_as_of: datetime | None = None
    cutoff: datetime | None = None
    batch_id: str | None = None
    unavailable_reason: str | None = None


class Ranking(DTO):
    opponent_missing_stat_appearances: int = 0
    position_rank: int | None = None
    combined_score: float | None = None
    opponent_ppr_per_appearance: float | None = None
    opponent_games: int = 0
    opponent_appearances: int = 0
    projection_percentile: float | None = None
    favorability_percentile: float | None = None
    unavailable_reason: str | None = None


class ProjectionResponse(DTO):
    availability: Literal["available", "unavailable", "insufficient_history"]
    player: PlayerInfo
    matchup: Matchup
    forecast: Forecast
    ranking: Ranking = Field(default_factory=Ranking)
    caveats: list[str] = Field(default_factory=list)


class HistoryGame(TargetContext):
    game_id: str | None = None
    game_date: date | None = None
    team: str | None = None
    opponent: str | None = None
    home_away: Literal["home", "away", "neutral"] | None = None
    fantasy_points_ppr: float
    carries: float
    targets: float
    receptions: float
    rushing_yards: float
    receiving_yards: float
    rushing_tds: float
    receiving_tds: float
    touchdowns: float
    completion_status: Literal["finished", "dnf", "dnp", "unknown"] = "unknown"


class HistoryResponse(DTO):
    player_id: str
    scoring_format: Literal["full_ppr"] = "full_ppr"
    target_context: TargetContext
    includes_selected_week: bool = False
    data_as_of: datetime | None = None
    games: list[HistoryGame]


class OpponentSummary(DTO):
    average_ppr: float | None = None
    median_ppr: float | None = None
    minimum_ppr: float | None = None
    maximum_ppr: float | None = None
    average_targets: float | None = None
    average_carries: float | None = None
    average_receptions: float | None = None


class OpponentGame(HistoryGame):
    player_team: str | None = None


class OpponentResponse(DTO):
    player_id: str
    opponent: str | None = None
    games_count: int = 0
    eligible_games_count: int = 0
    missing_stat_games: int = 0
    summary: OpponentSummary = Field(default_factory=OpponentSummary)
    caveat: str
    data_as_of: datetime | None = None
    games: list[OpponentGame] = Field(default_factory=list)


class DashboardResponse(DTO):
    projection: ProjectionResponse
    recent_history: HistoryResponse
    versus_opponent: OpponentResponse


class CurrentContext(BaseModel):
    supported_positions: list[str] = ["RB", "WR", "TE"]
    scoring_format: str = "full_ppr"
    scoring_version: str = "full_ppr_v1"
    available_seasons: list[int]
    available_weeks_by_season: dict[str, list[int]]
    default_season: int | None = None
    default_week: int | None = None
    latest_data_as_of: datetime | None = None
    latest_model_version: str | None = None
    latest_forecast_generation_time: datetime | None = None
    refresh_schedule: str = "Tuesday 08:00 America/New_York"
    publication_status: str = "pending"


class RankingResult(ProjectionResponse):
    actual_ppr: float | None = None
    completion_status: Literal["finished", "dnf", "dnp", "unknown"] | None = None


class RankingsResponse(DTO):
    season: int
    week: int
    batch_id: str | None = None
    generated_at: datetime | None = None
    status: Literal["published", "pending", "preliminary", "actual"]
    data_as_of: datetime | None = None
    completed_games: int = 0
    total_games: int = 0
    candidate_count: int = 0
    excluded_count: int = 0
    caveats: list[str] = Field(default_factory=list)
    results: list[RankingResult] = Field(default_factory=list)
