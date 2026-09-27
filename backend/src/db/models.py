from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class LineupSnapshot(Base):
    """Append-only ESPN projections. Rosters remain in the user's browser."""

    __tablename__ = "lineup_snapshots"
    snapshot_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class RankingPreview(Base):
    """Refreshable preliminary read model, separate from immutable publications."""

    __tablename__ = "ranking_previews"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Team(Base):
    __tablename__ = "teams"

    team_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(128))


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    player_name: Mapped[str] = mapped_column(String(160), index=True)
    position: Mapped[str] = mapped_column(String(16), index=True)
    current_team: Mapped[str | None] = mapped_column(String(8), index=True)
    active_status: Mapped[str | None] = mapped_column(String(32))
    headshot_url: Mapped[str | None] = mapped_column(Text)
    context_season: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    context_week: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    context_is_roster: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source_name: Mapped[str] = mapped_column(String(64))
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint(
            "season",
            "week",
            "game_type",
            "away_team",
            "home_team",
            name="game_context",
        ),
    )

    game_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    game_type: Mapped[str | None] = mapped_column(String(16))
    game_date: Mapped[date | None] = mapped_column(Date)
    game_time: Mapped[time | None] = mapped_column(Time)
    game_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    away_team: Mapped[str] = mapped_column(ForeignKey("teams.team_code"), index=True)
    home_team: Mapped[str] = mapped_column(ForeignKey("teams.team_code"), index=True)
    location: Mapped[str | None] = mapped_column(String(160))
    neutral_site: Mapped[bool | None] = mapped_column(Boolean)
    game_status: Mapped[str | None] = mapped_column(String(32))
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    source_name: Mapped[str] = mapped_column(String(64))
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGameStat(Base):
    __tablename__ = "player_game_stats"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "season",
            "week",
            "game_type",
            name="player_week_game_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    game_type: Mapped[str] = mapped_column(String(16))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    player_name: Mapped[str] = mapped_column(String(160))
    position: Mapped[str] = mapped_column(String(16), index=True)
    team: Mapped[str] = mapped_column(String(8), index=True)
    opponent_team: Mapped[str | None] = mapped_column(String(8), index=True)
    home_away: Mapped[str | None] = mapped_column(String(8))
    game_id: Mapped[str | None] = mapped_column(ForeignKey("games.game_id"), index=True)
    game_date: Mapped[date | None] = mapped_column(Date)

    passing_yards: Mapped[float] = mapped_column(Float, server_default=text("0"))
    passing_tds: Mapped[float] = mapped_column(Float, server_default=text("0"))
    interceptions: Mapped[float] = mapped_column(Float, server_default=text("0"))
    carries: Mapped[float] = mapped_column(Float, server_default=text("0"))
    rushing_yards: Mapped[float] = mapped_column(Float, server_default=text("0"))
    rushing_tds: Mapped[float] = mapped_column(Float, server_default=text("0"))
    rushing_fumbles_lost: Mapped[float] = mapped_column(Float, server_default=text("0"))
    targets: Mapped[float] = mapped_column(Float, server_default=text("0"))
    receptions: Mapped[float] = mapped_column(Float, server_default=text("0"))
    receiving_yards: Mapped[float] = mapped_column(Float, server_default=text("0"))
    receiving_tds: Mapped[float] = mapped_column(Float, server_default=text("0"))
    receiving_fumbles_lost: Mapped[float] = mapped_column(Float, server_default=text("0"))
    sack_fumbles_lost: Mapped[float] = mapped_column(Float, server_default=text("0"))
    fumbles_lost_total: Mapped[float] = mapped_column(Float, server_default=text("0"))
    fantasy_points_ppr: Mapped[float] = mapped_column(Float)
    fantasy_points_ppr_source: Mapped[float | None] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(64))
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mapping_version: Mapped[str] = mapped_column(String(32))
    scoring_version: Mapped[str] = mapped_column(String(32), server_default="full_ppr_v1")
    data_artifact_id: Mapped[str] = mapped_column(String(128), server_default="legacy")


class PlayerWeeklyRoster(Base):
    __tablename__ = "player_weekly_rosters"
    __table_args__ = (UniqueConstraint("player_id", "season", "week", "team"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    season: Mapped[int] = mapped_column(Integer)
    week: Mapped[int] = mapped_column(Integer)
    game_type: Mapped[str] = mapped_column(String(16))
    team: Mapped[str] = mapped_column(ForeignKey("teams.team_code"))
    position: Mapped[str] = mapped_column(String(16))
    roster_status: Mapped[str | None] = mapped_column(String(32))
    data_artifact_id: Mapped[str] = mapped_column(String(128))
    source_name: Mapped[str] = mapped_column(String(64))
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGameParticipation(Base):
    __tablename__ = "player_game_participation"
    __table_args__ = (UniqueConstraint("player_id", "game_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), index=True)
    team: Mapped[str] = mapped_column(ForeignKey("teams.team_code"))
    offense_snaps: Mapped[int] = mapped_column(Integer)
    defense_snaps: Mapped[int] = mapped_column(Integer)
    special_teams_snaps: Mapped[int] = mapped_column(Integer)
    has_stat_record: Mapped[bool] = mapped_column(Boolean)
    data_artifact_id: Mapped[str] = mapped_column(String(128))
    source_name: Mapped[str] = mapped_column(String(64))
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGameCompletionEvidence(Base):
    __tablename__ = "player_game_completion_evidence"
    __table_args__ = (
        CheckConstraint("status IN ('finished', 'dnf', 'dnp')", name="completion_status"),
    )

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    source_url: Mapped[str] = mapped_column(Text)
    source_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_note: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(128))


class PlayerWeekFeature(Base):
    __tablename__ = "player_week_features"
    __table_args__ = (UniqueConstraint("player_id", "season", "week", name="player_week"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    position: Mapped[str] = mapped_column(String(16))
    games_played_prior: Mapped[int] = mapped_column(Integer)
    ppr_points_prev: Mapped[float | None] = mapped_column(Float)
    ppr_points_avg_3: Mapped[float | None] = mapped_column(Float)
    ppr_points_avg_4: Mapped[float | None] = mapped_column(Float)
    ppr_points_avg_8: Mapped[float | None] = mapped_column(Float)
    ppr_points_std_4: Mapped[float | None] = mapped_column(Float)
    targets_prev: Mapped[float | None] = mapped_column(Float)
    targets_avg_3: Mapped[float | None] = mapped_column(Float)
    targets_avg_4: Mapped[float | None] = mapped_column(Float)
    targets_avg_8: Mapped[float | None] = mapped_column(Float)
    receptions_prev: Mapped[float | None] = mapped_column(Float)
    receptions_avg_4: Mapped[float | None] = mapped_column(Float)
    carries_prev: Mapped[float | None] = mapped_column(Float)
    carries_avg_3: Mapped[float | None] = mapped_column(Float)
    carries_avg_4: Mapped[float | None] = mapped_column(Float)
    rushing_yards_prev: Mapped[float | None] = mapped_column(Float)
    rushing_yards_avg_4: Mapped[float | None] = mapped_column(Float)
    receiving_yards_prev: Mapped[float | None] = mapped_column(Float)
    receiving_yards_avg_4: Mapped[float | None] = mapped_column(Float)
    rushing_tds_avg_8: Mapped[float | None] = mapped_column(Float)
    receiving_tds_avg_8: Mapped[float | None] = mapped_column(Float)
    data_artifact_id: Mapped[str] = mapped_column(String(128))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelVersion(Base):
    __tablename__ = "model_versions"

    model_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(128))
    feature_list: Mapped[list[str]] = mapped_column(JSONB)
    model_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    train_start_season: Mapped[int] = mapped_column(Integer)
    train_start_week: Mapped[int] = mapped_column(Integer)
    train_end_season: Mapped[int] = mapped_column(Integer)
    train_end_week: Mapped[int] = mapped_column(Integer)
    data_artifact_id: Mapped[str] = mapped_column(String(128))
    artifact_uri: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlayerWeekPrediction(Base):
    __tablename__ = "player_week_predictions"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "season",
            "week",
            "model_version",
            name="player_week_model",
        ),
        CheckConstraint(
            "history_quality IN ('none', 'limited', 'adequate')",
            name="history_quality",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    model_version: Mapped[str] = mapped_column(ForeignKey("model_versions.model_version"))
    projection_ppr: Mapped[float | None] = mapped_column(Float)
    baseline_projection_ppr: Mapped[float | None] = mapped_column(Float)
    recent_ppr_average_4: Mapped[float | None] = mapped_column(Float)
    games_played_prior: Mapped[int] = mapped_column(Integer)
    history_quality: Mapped[str] = mapped_column(String(16))
    data_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DataIngestionRun(Base):
    __tablename__ = "data_ingestion_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64))
    seasons: Mapped[list[int]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), index=True)
    row_counts: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    data_artifact_id: Mapped[str | None] = mapped_column(String(128))


class ForecastGenerationRun(Base):
    __tablename__ = "forecast_generation_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_version: Mapped[str] = mapped_column(ForeignKey("model_versions.model_version"))
    season: Mapped[int] = mapped_column(Integer)
    week: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    predictions_generated: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class ForecastBatch(Base):
    __tablename__ = "forecast_batches"
    __table_args__ = (
        CheckConstraint("status IN ('published', 'blocked')", name="batch_status"),
        UniqueConstraint("season", "week", "input_hash", name="batch_input"),
    )
    batch_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ForecastBatchPlayer(Base):
    __tablename__ = "forecast_batch_players"
    batch_id: Mapped[str] = mapped_column(ForeignKey("forecast_batches.batch_id"), primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    projection: Mapped[dict[str, Any]] = mapped_column(JSONB)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ForecastPublication(Base):
    __tablename__ = "forecast_publications"
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("forecast_batches.batch_id"), unique=True)
