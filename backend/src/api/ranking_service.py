"""Actual-results read model and stored preliminary-ranking reads; no inference."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas.players import (
    Forecast,
    Matchup,
    Ranking,
    RankingResult,
    RankingsResponse,
)
from src.db.models import (
    Game,
    Player,
    PlayerGameCompletionEvidence,
    PlayerGameStat,
    RankingPreview,
)
from src.domain.completion import completion_at


def target_games(session: Session, season: int, week: int) -> list[Game]:
    return list(
        session.scalars(
            select(Game).where(Game.season == season, Game.week == week, Game.game_type == "REG")
        )
    )


def week_started(games: list[Game], now: datetime) -> bool:
    return any(
        g.game_status == "completed" or (g.game_datetime and g.game_datetime <= now) for g in games
    )


def actual_rankings(
    session: Session, season: int, week: int, position: str | None, games: list[Game]
) -> RankingsResponse:
    from src.api.player_service import POSITIONS, evidence_models, player_info

    completed = {g.game_id: g for g in games if g.game_status == "completed"}
    rows = session.execute(
        select(PlayerGameStat, Player)
        .join(Player, Player.player_id == PlayerGameStat.player_id)
        .where(
            PlayerGameStat.game_id.in_(completed),
            PlayerGameStat.position.in_([position] if position else POSITIONS),
        )
    ).all()
    evidence = evidence_models(
        session.scalars(
            select(PlayerGameCompletionEvidence).where(
                PlayerGameCompletionEvidence.game_id.in_(completed)
            )
        ).all()
    )
    now = datetime.now(UTC)
    rows.sort(
        key=lambda row: (
            row[0].position,
            -row[0].fantasy_points_ppr,
            row[1].player_name,
            row[1].player_id,
        )
    )
    results = []
    counts, last_score, ranks = {}, {}, {}
    for stat, player in rows:
        pos = stat.position
        counts[pos] = counts.get(pos, 0) + 1
        if last_score.get(pos) != stat.fantasy_points_ppr:
            ranks[pos] = counts[pos]
        last_score[pos] = stat.fantasy_points_ppr
        game = completed[stat.game_id]
        results.append(
            RankingResult(
                availability="unavailable",
                player=player_info(player, stat.team).model_copy(update={"position": pos}),
                matchup=Matchup(
                    season=season,
                    week=week,
                    opponent=stat.opponent_team,
                    home_away=stat.home_away,
                    game_id=game.game_id,
                    game_date=game.game_date,
                    game_date_time=game.game_datetime,
                    status="completed",
                    team_context_week=week,
                ),
                forecast=Forecast(unavailable_reason="actual_results_not_forecast"),
                ranking=Ranking(position_rank=ranks[pos]),
                actual_ppr=stat.fantasy_points_ppr,
                completion_status=completion_at(evidence, player.player_id, game.game_id, now),
            )
        )
    return RankingsResponse(
        season=season,
        week=week,
        status="actual",
        results=results[:100],
        data_as_of=max((stat.source_retrieved_at for stat, _ in rows), default=None),
        total_games=len(games),
        completed_games=len(completed),
        candidate_count=len(rows),
        caveats=[
            "Ranked by actual full-PPR points within position, not pregame predictions.",
            "Only imported completed-game results are included. DNF scores remain actual results.",
        ],
    )


def preliminary_rankings(
    session: Session, season: int, week: int, position: str | None
) -> RankingsResponse:
    preview = session.get(RankingPreview, (season, week))
    if preview is None:
        return RankingsResponse(season=season, week=week, status="pending")
    response = RankingsResponse.model_validate(preview.payload)
    response.results = [
        row for row in response.results if position is None or row.player.position == position
    ][:100]
    return response
