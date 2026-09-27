"""Build an atomic, immutable weekly baseline publication. Never trains a model."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from src.api.player_service import POSITIONS, evidence_models, matchup_for, player_info, publication
from src.api.schemas.players import Forecast, ProjectionResponse
from src.core.config import get_settings
from src.db.models import (
    ForecastBatch,
    ForecastBatchPlayer,
    ForecastPublication,
    Game,
    Player,
    PlayerGameCompletionEvidence,
    PlayerGameParticipation,
    PlayerGameStat,
    PlayerWeeklyRoster,
)
from src.features.matchup_ranking import RANKING_VERSION, apply_rankings, opponent_context
from src.features.player_history import FEATURE_VERSION, build_player_history
from src.models.baseline import BASELINE_VERSION, predict_baseline


def record(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def generate_forecasts(session: Session, season: int, week: int, cutoff: datetime) -> ForecastBatch:
    """Caller owns the transaction. Blocked attempts are stored, never published."""
    if not 2024 <= season <= 2100 or not 1 <= week <= 18:
        raise ValueError("Expected a supported season and regular-season week 1–18")
    if cutoff.tzinfo is None or cutoff > datetime.now(UTC):
        raise ValueError("Cutoff must be timezone-aware and cannot be in the future")
    # Same lock as canonical imports and reviewed evidence, so all inputs stay coherent.
    session.execute(text("SELECT pg_advisory_xact_lock(174202409)"))
    existing = publication(session, season, week)
    if existing:
        return existing

    games = session.scalars(
        select(Game)
        .where(Game.game_type == "REG", Game.season >= 2024, Game.season <= season)
        .order_by(Game.game_id)
    ).all()
    prior = [g for g in games if (g.season, g.week) < (season, week)]
    target = [g for g in games if (g.season, g.week) == (season, week)]
    stats = session.scalars(
        select(PlayerGameStat)
        .where(
            PlayerGameStat.season >= 2024,
            PlayerGameStat.season <= season,
            PlayerGameStat.game_type == "REG",
        )
        .order_by(PlayerGameStat.id)
    ).all()
    stats = [s for s in stats if (s.season, s.week) < (season, week)]
    prior_ids = {g.game_id for g in prior}
    participation = session.scalars(
        select(PlayerGameParticipation)
        .where(PlayerGameParticipation.game_id.in_(prior_ids))
        .order_by(PlayerGameParticipation.id)
    ).all()
    rosters = session.scalars(
        select(PlayerWeeklyRoster)
        .where(
            PlayerWeeklyRoster.season == season,
            PlayerWeeklyRoster.week == week,
            PlayerWeeklyRoster.game_type == "REG",
            PlayerWeeklyRoster.position.in_(POSITIONS),
        )
        .order_by(PlayerWeeklyRoster.id)
    ).all()
    players = session.scalars(
        select(Player)
        .where(Player.player_id.in_({r.player_id for r in rosters}))
        .order_by(Player.player_id)
    ).all()
    evidence = session.scalars(
        select(PlayerGameCompletionEvidence)
        .where(
            PlayerGameCompletionEvidence.reviewed_at <= cutoff,
            PlayerGameCompletionEvidence.game_id.in_(prior_ids),
        )
        .order_by(PlayerGameCompletionEvidence.evidence_id)
    ).all()
    source_rows = prior + target + stats + participation + rosters + players
    gates = []
    if not target or any(
        g.game_datetime is None or g.game_datetime <= cutoff or g.game_status != "upcoming"
        for g in target
    ):
        gates.append("target_week_not_fully_upcoming")
    # A historical cutoff can precede kickoff while the real clock is already past it.
    if any(g.game_datetime is not None and g.game_datetime <= datetime.now(UTC) for g in target):
        gates.append("target_week_started")
    if any(
        g.game_status != "completed" or g.game_datetime is None or g.game_datetime >= cutoff
        for g in prior
    ):
        gates.append("prior_games_not_complete")
    if any(r.source_retrieved_at > cutoff for r in source_rows):
        gates.append("inputs_newer_than_cutoff")
    roster_teams = {r.team for r in rosters}
    target_teams = {t for g in target for t in (g.home_team, g.away_team)}
    if not players or not target_teams <= roster_teams:
        gates.append("incomplete_target_rosters")
    coverage = {(s.game_id, s.team) for s in stats}
    if any((g.game_id, t) not in coverage for g in prior for t in (g.home_team, g.away_team)):
        gates.append("incomplete_prior_team_stats")

    inputs = jsonable_encoder(
        {
            "season": season,
            "week": week,
            "cutoff": cutoff,
            "model_version": BASELINE_VERSION,
            "feature_version": FEATURE_VERSION,
            "ranking_version": RANKING_VERSION,
            "games": [record(g) for g in prior + target],
            "stats": [record(s) for s in stats],
            "participation": [record(p) for p in participation],
            "rosters": [record(r) for r in rosters],
            "players": [record(p) for p in players],
            "evidence": [record(e) for e in evidence],
        }
    )
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    existing_attempt = session.scalar(
        select(ForecastBatch).where(
            ForecastBatch.season == season,
            ForecastBatch.week == week,
            ForecastBatch.input_hash == digest,
        )
    )
    if existing_attempt:
        return existing_attempt
    generated_at = datetime.now(UTC)
    batch_id = uuid4().hex
    data_as_of = max((r.source_retrieved_at for r in source_rows), default=None)
    by_game = {g.game_id: g for g in prior}
    stat_records = [
        {
            **record(s),
            "game_datetime": by_game[s.game_id].game_datetime if s.game_id in by_game else None,
        }
        for s in stats
    ]
    snap_records = [
        {
            **record(p),
            "season": by_game[p.game_id].season,
            "week": by_game[p.game_id].week,
            "game_type": "REG",
            "game_datetime": by_game[p.game_id].game_datetime,
        }
        for p in participation
    ]
    stats_by_player, snaps_by_player, evidence_by_player = (defaultdict(list) for _ in range(3))
    for row in stat_records:
        stats_by_player[row["player_id"]].append(row)
    for row in snap_records:
        snaps_by_player[row["player_id"]].append(row)
    for item in evidence_models(evidence):
        evidence_by_player[item.player_id].append(item)
    projections, features = [], {}
    if not gates:
        for player in players:
            player_rosters = [r for r in rosters if r.player_id == player.player_id]
            position = player_rosters[0].position
            feature = build_player_history(
                player_id=player.player_id,
                position=position,
                season=season,
                week=week,
                cutoff=cutoff,
                stats=stats_by_player[player.player_id],
                participation=snaps_by_player[player.player_id],
                evidence=evidence_by_player[player.player_id],
            )
            features[player.player_id] = feature
            matchup, team, context_reason = matchup_for(session, player.player_id, season, week)
            reason = context_reason or feature["unavailable_reason"]
            if any(r.roster_status != "ACT" for r in player_rosters):
                reason = "inactive_or_unverified_roster_status"
            if len({r.position for r in player_rosters}) != 1:
                reason = "conflicting_roster_position"
            points = predict_baseline(feature) if reason is None else None
            info = player_info(player, team).model_copy(update={"position": position})
            result = ProjectionResponse(
                availability="available"
                if points is not None
                else "insufficient_history"
                if reason == "insufficient_history"
                else "unavailable",
                player=info,
                matchup=matchup,
                forecast=Forecast(
                    projection_ppr=points,
                    baseline_projection_ppr=points,
                    recent_ppr_average4=feature["ppr_points_avg_4"],
                    games_played_prior=feature["games_played_prior"],
                    eligible_games_prior=feature["eligible_games_prior"],
                    history_quality=feature["history_quality"],
                    model_name="Trailing-four baseline",
                    model_version=BASELINE_VERSION,
                    generated_at=generated_at,
                    data_as_of=data_as_of,
                    cutoff=cutoff,
                    batch_id=batch_id,
                    unavailable_reason=reason,
                ),
                ranking=opponent_context(
                    matchup.opponent,
                    position,
                    [record(g) for g in prior],
                    stat_records,
                    snap_records,
                ),
                caveats=[
                    "Baseline estimate, not a trained machine-learning forecast.",
                    "Assumes participation; check injury news before kickoff. No live monitoring.",
                    "Player averages exclude reported DNF games. Recorded appearances without "
                    "completion reports are included; unreported early exits may remain.",
                    "Rank is 50% projected-points percentile and "
                    "50% opponent percentile within position.",
                    "Opponent context uses actual PPR per appearance, including early exits, "
                    "over up to four games; it is descriptive, not causal.",
                ],
            )
            if reason:
                result.ranking.unavailable_reason = reason
            if 0 < result.ranking.opponent_games < 4:
                result.caveats.append(
                    f"Limited opponent history: {result.ranking.opponent_games} completed games."
                )
            projections.append(result)
        apply_rankings(projections)
    available = sum(p.availability == "available" for p in projections)
    if not available and not gates:
        gates.append("no_available_projections")
    batch = ForecastBatch(
        batch_id=batch_id,
        season=season,
        week=week,
        model_version=BASELINE_VERSION,
        input_hash=digest,
        cutoff=cutoff,
        generated_at=generated_at,
        data_as_of=data_as_of,
        status="blocked" if gates else "published",
        inputs=inputs,
        report={
            "gates": gates,
            "candidate_count": len(players),
            "available_count": available,
            "ranked_count": sum(p.ranking.position_rank is not None for p in projections),
            "unavailable_reasons": dict(
                Counter(
                    p.forecast.unavailable_reason
                    for p in projections
                    if p.forecast.unavailable_reason
                )
            ),
        },
    )
    session.add(batch)
    session.flush()
    session.add_all(
        [
            ForecastBatchPlayer(
                batch_id=batch_id,
                player_id=p.player.player_id,
                projection=p.model_dump(mode="json", by_alias=True),
                features=jsonable_encoder(features[p.player.player_id]),
            )
            for p in projections
        ]
    )
    session.flush()
    if batch.status == "published":
        session.add(ForecastPublication(season=season, week=week, batch_id=batch_id))
    session.flush()
    return batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--cutoff", type=datetime.fromisoformat, default=None)
    args = parser.parse_args()
    engine = create_engine(get_settings().database_url)
    try:
        with Session(engine) as session, session.begin():
            batch = generate_forecasts(
                session, args.season, args.week, args.cutoff or datetime.now(UTC)
            )
            report = {"batch_id": batch.batch_id, "status": batch.status, **batch.report}
        print(json.dumps(report, indent=2))
        if report["status"] != "published":
            raise SystemExit(2)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
