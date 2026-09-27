"""Prepare refreshable, explicitly preliminary rankings without publishing a forecast."""

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.api.player_service import POSITIONS, evidence_models, matchup_for, player_info
from src.api.ranking_service import target_games, week_started
from src.api.schemas.players import Forecast, RankingResult, RankingsResponse
from src.core.database import SessionLocal
from src.db.models import (
    Game,
    Player,
    PlayerGameCompletionEvidence,
    PlayerGameParticipation,
    PlayerGameStat,
    PlayerWeeklyRoster,
    RankingPreview,
)
from src.features.matchup_ranking import apply_rankings, opponent_context
from src.features.player_history import build_player_history
from src.jobs.generate_forecasts import record
from src.models.baseline import BASELINE_VERSION, predict_baseline


def prepare_rankings(session: Session, season: int, week: int) -> RankingsResponse:
    if not 2024 <= season <= 2100 or not 1 <= week <= 18:
        raise ValueError("Expected a supported season and regular-season week 1–18")
    session.execute(text("SELECT pg_advisory_xact_lock(174202409)"))
    now = datetime.now(UTC)
    target = target_games(session, season, week)
    if (
        not target
        or week_started(target, now)
        or any(g.game_datetime is None or g.game_status != "upcoming" for g in target)
    ):
        raise ValueError("Preliminary estimates require a fully upcoming scheduled week")
    prior = [
        g
        for g in session.scalars(
            select(Game).where(
                Game.game_type == "REG",
                Game.season >= 2024,
                Game.season <= season,
                Game.game_status == "completed",
                Game.game_datetime < now,
            )
        )
        if (g.season, g.week) < (season, week)
    ]
    by_game = {g.game_id: g for g in prior}
    stats = list(
        session.scalars(
            select(PlayerGameStat).where(
                PlayerGameStat.game_id.in_(by_game),
                PlayerGameStat.source_retrieved_at <= now,
            )
        )
    )
    snaps = list(
        session.scalars(
            select(PlayerGameParticipation).where(
                PlayerGameParticipation.game_id.in_(by_game),
                PlayerGameParticipation.source_retrieved_at <= now,
            )
        )
    )
    rosters = list(
        session.scalars(
            select(PlayerWeeklyRoster).where(
                PlayerWeeklyRoster.season == season,
                PlayerWeeklyRoster.week <= week,
                PlayerWeeklyRoster.game_type == "REG",
                PlayerWeeklyRoster.source_retrieved_at <= now,
            )
        )
    )
    latest_rosters = defaultdict(list)
    for roster in sorted(rosters, key=lambda r: r.week):
        previous = latest_rosters[roster.player_id]
        if previous and previous[0].week < roster.week:
            previous.clear()
        previous.append(roster)
    candidates = {
        pid: rows[0]
        for pid, rows in latest_rosters.items()
        if len(rows) == 1 and rows[0].roster_status == "ACT" and rows[0].position in POSITIONS
    }
    players = list(session.scalars(select(Player).where(Player.player_id.in_(candidates))))
    evidence = evidence_models(
        session.scalars(
            select(PlayerGameCompletionEvidence).where(
                PlayerGameCompletionEvidence.game_id.in_(by_game),
                PlayerGameCompletionEvidence.reviewed_at <= now,
            )
        ).all()
    )
    stat_records = [{**record(r), "game_datetime": by_game[r.game_id].game_datetime} for r in stats]
    snap_records = [
        {
            **record(r),
            "season": by_game[r.game_id].season,
            "week": by_game[r.game_id].week,
            "game_type": "REG",
            "game_datetime": by_game[r.game_id].game_datetime,
        }
        for r in snaps
    ]
    by_player_stats, by_player_snaps, by_player_evidence = (defaultdict(list) for _ in range(3))
    for row in stat_records:
        by_player_stats[row["player_id"]].append(row)
    for row in snap_records:
        by_player_snaps[row["player_id"]].append(row)
    for item in evidence:
        by_player_evidence[item.player_id].append(item)
    game_records = [record(g) for g in prior]
    opponent_cache = {}
    data_as_of = max(
        (r.source_retrieved_at for r in stats + rosters + snaps + target), default=None
    )
    results = []
    for player in players:
        roster = candidates[player.player_id]
        matchup, team, reason = matchup_for(session, player.player_id, season, week)
        if reason or matchup.status != "upcoming":
            continue
        features = build_player_history(
            player_id=player.player_id,
            position=roster.position,
            season=season,
            week=week,
            cutoff=now,
            stats=by_player_stats[player.player_id],
            participation=by_player_snaps[player.player_id],
            evidence=by_player_evidence[player.player_id],
        )
        points = predict_baseline(features)
        if points is None:
            continue
        key = (matchup.opponent, roster.position)
        if key not in opponent_cache:
            opponent_cache[key] = opponent_context(
                *key,
                game_records,
                stat_records,
                snap_records,
                allow_partial=True,
            )
        results.append(
            RankingResult(
                availability="available",
                player=player_info(player, team).model_copy(update={"position": roster.position}),
                matchup=matchup,
                forecast=Forecast(
                    projection_ppr=points,
                    baseline_projection_ppr=points,
                    recent_ppr_average4=points,
                    games_played_prior=features["games_played_prior"],
                    eligible_games_prior=features["eligible_games_prior"],
                    history_quality=features["history_quality"],
                    model_name="Preliminary trailing-four baseline",
                    model_version=BASELINE_VERSION,
                    generated_at=now,
                    cutoff=now,
                    data_as_of=data_as_of,
                ),
                ranking=opponent_cache[key].model_copy(deep=True),
                caveats=[
                    "Preliminary estimate, not a published forecast or trained ML model.",
                    f"Roster status is from Week {roster.week}; participation is not guaranteed.",
                ],
            )
        )
    apply_rankings(results)
    results = [r for r in results if r.ranking.position_rank is not None]
    results.sort(key=lambda r: (r.player.position, r.ranking.position_rank, r.player.player_id))
    response = RankingsResponse(
        season=season,
        week=week,
        status="preliminary",
        generated_at=now,
        data_as_of=data_as_of,
        total_games=len(target),
        results=results,
        candidate_count=len(players),
        excluded_count=len(players) - len(results),
        caveats=[
            "50% baseline-points percentile + 50% opponent-favorability percentile, "
            "within position.",
            "Baseline: up to four prior eligible appearances; reported DNFs excluded. "
            "Opponent: recorded PPR per positional appearance over up to four completed games. "
            "Partial opponent coverage is labeled; missing scores are not treated as zero.",
            "Latest known active rosters are used. Check injury news before kickoff. "
            "Incomplete prior-week data can change these estimates; no weekly retraining occurs.",
        ],
    )
    payload = response.model_dump(mode="json", by_alias=True)
    statement = insert(RankingPreview).values(season=season, week=week, payload=payload)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[RankingPreview.season, RankingPreview.week],
            set_={"payload": payload},
        )
    )
    session.flush()
    return response


def refresh_next_rankings(session: Session) -> RankingsResponse | None:
    """Refresh the next fully upcoming week after an import, in the same transaction."""
    now = datetime.now(UTC)
    upcoming = session.scalars(
        select(Game)
        .where(
            Game.game_type == "REG",
            Game.game_datetime > now,
            Game.game_status == "upcoming",
        )
        .order_by(Game.game_datetime)
    ).all()
    seen = set()
    for game in upcoming:
        key = (game.season, game.week)
        if key in seen:
            continue
        seen.add(key)
        targets = target_games(session, *key)
        if not week_started(targets, now) and all(
            g.game_datetime is not None and g.game_status == "upcoming" for g in targets
        ):
            return prepare_rankings(session, *key)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()
    with SessionLocal() as session, session.begin():
        result = prepare_rankings(session, args.season, args.week)
        print(
            json.dumps(
                {
                    "status": result.status,
                    "ranked": len(result.results),
                    "excluded": result.excluded_count,
                    "data_as_of": str(result.data_as_of),
                }
            )
        )


if __name__ == "__main__":
    main()
