"""Transactional publication of canonical source records into PostgreSQL."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.data.schema_validation import SourceSchemaError
from src.data.source_adapter import CanonicalDataset
from src.db.models import (
    Game,
    Player,
    PlayerGameParticipation,
    PlayerGameStat,
    PlayerWeeklyRoster,
    Team,
)


def upsert(session: Session, model: Any, rows: list[dict], keys: list[str]) -> None:
    for start in range(0, len(rows), 500):
        statement = insert(model).values(rows[start : start + 500])
        values = {k: getattr(statement.excluded, k) for k in rows[start] if k not in keys}
        where = None
        if model is Player:
            ex = statement.excluded
            where = or_(
                ex.context_season > Player.context_season,
                and_(
                    ex.context_season == Player.context_season,
                    ex.context_week > Player.context_week,
                ),
                and_(
                    ex.context_season == Player.context_season,
                    ex.context_week == Player.context_week,
                    ex.context_is_roster >= Player.context_is_roster,
                    ex.source_retrieved_at >= Player.source_retrieved_at,
                ),
            )
        elif "source_retrieved_at" in rows[start]:
            where = statement.excluded.source_retrieved_at >= model.source_retrieved_at
        if values:
            statement = statement.on_conflict_do_update(
                index_elements=keys, set_=values, where=where
            )
        else:
            statement = statement.on_conflict_do_nothing(index_elements=keys)
        session.execute(statement)


def persist_dataset(session: Session, data: CanonicalDataset, as_of: datetime) -> None:
    """Caller owns transaction. No deletes: unexplained source removals block this import."""
    session.execute(text("SELECT pg_advisory_xact_lock(174202409)"))
    counts = data.report["counts"]
    if counts["unexplained_ppr_differences"]:
        raise SourceSchemaError("Unexplained source-PPR differences; see validation report")
    if counts.get("stats_for_uncompleted_game", 0):
        raise SourceSchemaError("Player stats reference uncompleted games; see validation report")
    if counts.get("completed_game_teams_without_supported_stats", 0):
        raise SourceSchemaError("Completed-game team coverage is incomplete; see validation report")
    # An import is not allowed to silently remove or regress an existing season's data.
    seasons = {g["season"] for g in data.games}
    incoming = {(r["player_id"], r["season"], r["week"], r["game_type"]) for r in data.stats}
    existing = session.execute(
        select(
            PlayerGameStat.player_id,
            PlayerGameStat.season,
            PlayerGameStat.week,
            PlayerGameStat.game_type,
            PlayerGameStat.source_retrieved_at,
        ).where(PlayerGameStat.season.in_(seasons))
    ).all()
    missing = [tuple(r[:4]) for r in existing if tuple(r[:4]) not in incoming and r[4] <= as_of]
    if missing:
        raise SourceSchemaError(
            f"Source snapshot omits {len(missing)} stored player games; "
            "reconciliation review required"
        )
    teams = {g[k] for g in data.games for k in ("away_team", "home_team")}
    teams |= {r["team"] for r in data.rosters + data.stats + data.participation}
    upsert(session, Team, [{"team_code": team} for team in sorted(teams)], ["team_code"])
    upsert(session, Player, data.players, ["player_id"])
    provenance = {"source_name": "nflreadpy", "source_retrieved_at": as_of}
    upsert(session, Game, [{**g, **provenance} for g in data.games], ["game_id"])
    upsert(session, PlayerGameStat, data.stats, ["player_id", "season", "week", "game_type"])
    upsert(session, PlayerWeeklyRoster, data.rosters, ["player_id", "season", "week", "team"])
    upsert(session, PlayerGameParticipation, data.participation, ["player_id", "game_id"])
