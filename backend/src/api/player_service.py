"""Read models for prepared data; no downloads or model execution on request paths."""

from datetime import UTC, datetime
from statistics import mean, median

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from src.api.schemas.players import (
    CurrentContext,
    DashboardResponse,
    Forecast,
    HistoryGame,
    HistoryResponse,
    Matchup,
    OpponentGame,
    OpponentResponse,
    OpponentSummary,
    PlayerInfo,
    PlayerSearchResponse,
    ProjectionResponse,
    RankingResult,
    RankingsResponse,
    SearchPlayer,
    TargetContext,
)
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
from src.domain.completion import CompletionEvidence, completion_at

POSITIONS = ("RB", "WR", "TE")


def player_or_404(session: Session, player_id: str) -> Player:
    player = session.get(Player, player_id)
    if player is None or player.position not in POSITIONS:
        raise HTTPException(
            404, detail={"code": "player_not_found", "message": "Player not found."}
        )
    return player


def player_info(player: Player, team: str | None) -> PlayerInfo:
    return PlayerInfo(
        player_id=player.player_id,
        display_name=player.player_name,
        position=player.position,
        team=team,
        headshot_url=player.headshot_url,
    )


def search(session: Session, query: str) -> PlayerSearchResponse:
    normalized = "".join(c for c in query.lower() if c.isalnum())
    if len(normalized) < 2:
        raise HTTPException(
            422, detail={"code": "short_query", "message": "Enter at least two letters or numbers."}
        )
    column = func.regexp_replace(func.lower(Player.player_name), "[^[:alnum:]]", "", "g")
    rows = session.scalars(
        select(Player)
        .where(Player.position.in_(POSITIONS), column.contains(normalized, autoescape=True))
        .order_by(
            (Player.active_status == "ACT").desc().nulls_last(),
            Player.context_season.desc(),
            Player.context_week.desc(),
            Player.player_name,
            Player.player_id,
        )
        .limit(20)
    ).all()
    return PlayerSearchResponse(
        results=[
            SearchPlayer(
                **player_info(p, p.current_team).model_dump(),
                active=None if p.active_status is None else p.active_status == "ACT",
            )
            for p in rows
        ]
    )


def matchup_for(
    session: Session, player_id: str, season: int, week: int
) -> tuple[Matchup, str | None, str | None]:
    # Schedule display does not require a target-week roster publication.
    # Use the newest same-season team context, preferring rosters over stats
    # within the same week. Never carry a future trade back into past weeks.
    contexts = []
    for model, priority in ((PlayerWeeklyRoster, 1), (PlayerGameStat, 0)):
        rows = session.execute(
            select(model.week, model.team).where(
                model.player_id == player_id,
                model.season == season,
                model.week <= week,
                model.game_type == "REG",
            )
        )
        contexts.extend((row.week, priority, row.team) for row in rows)
    latest = max(((w, priority) for w, priority, _ in contexts), default=None)
    teams = {team for w, priority, team in contexts if (w, priority) == latest}
    if len(teams) != 1:
        return Matchup(season=season, week=week), None, "unverified_roster"
    team = next(iter(teams))
    team_context_week = latest[0]
    games = session.scalars(
        select(Game).where(
            Game.season == season,
            Game.week == week,
            Game.game_type == "REG",
            or_(Game.home_team == team, Game.away_team == team),
        )
    ).all()
    if len(games) != 1:
        season_games = session.scalar(
            select(func.count())
            .select_from(Game)
            .where(Game.season == season, Game.game_type == "REG")
        )
        bye = len(games) == 0 and season_games == 272
        return (
            Matchup(
                season=season,
                week=week,
                status="bye" if bye else "unavailable",
                team_context_week=team_context_week,
            ),
            team,
            "bye" if bye else "unverified_schedule",
        )
    game = games[0]
    home = game.home_team == team
    status = game.game_status if game.game_status in ("upcoming", "completed") else "unavailable"
    return (
        Matchup(
            season=season,
            week=week,
            opponent=game.away_team if home else game.home_team,
            home_away=None
            if game.neutral_site is None
            else "neutral"
            if game.neutral_site
            else "home"
            if home
            else "away",
            game_id=game.game_id,
            game_date=game.game_date,
            game_date_time=game.game_datetime,
            status=status,
            team_context_week=team_context_week,
        ),
        team,
        None,
    )


def publication(session: Session, season: int, week: int) -> ForecastBatch | None:
    return session.scalar(
        select(ForecastBatch)
        .join(ForecastPublication, ForecastPublication.batch_id == ForecastBatch.batch_id)
        .where(
            ForecastPublication.season == season,
            ForecastPublication.week == week,
            ForecastBatch.status == "published",
        )
    )


def projection(session: Session, player_id: str, season: int, week: int) -> ProjectionResponse:
    player = player_or_404(session, player_id)
    batch = publication(session, season, week)
    if batch:
        row = session.get(ForecastBatchPlayer, (batch.batch_id, player_id))
        if row:
            return ProjectionResponse.model_validate(row.projection)
    matchup, team, reason = matchup_for(session, player_id, season, week)
    latest = session.scalar(select(func.max(PlayerGameStat.source_retrieved_at)))
    return ProjectionResponse(
        availability="unavailable",
        player=player_info(player, team),
        matchup=matchup,
        forecast=Forecast(data_as_of=latest, unavailable_reason=reason or "forecast_not_published"),
        caveats=[
            "No published forecast is available for this player and selected week.",
            "Forecasts assume participation. No live injury monitoring is provided.",
        ]
        + (
            [
                "Scheduled matchup uses the latest known team from Week "
                f"{matchup.team_context_week} of {season}; "
                "this is not confirmation of participation."
            ]
            if matchup.team_context_week is not None and matchup.team_context_week < week
            else []
        ),
    )


def evidence_models(rows) -> list[CompletionEvidence]:
    return [
        CompletionEvidence(**{name: getattr(row, name) for name in CompletionEvidence.model_fields})
        for row in rows
    ]


def prior_rows(
    session: Session,
    player_id: str,
    season: int,
    week: int,
    limit: int | None = None,
    include_selected_week: bool = False,
):
    statement = (
        select(PlayerGameStat)
        .join(Game, Game.game_id == PlayerGameStat.game_id)
        .where(
            PlayerGameStat.player_id == player_id,
            PlayerGameStat.game_type == "REG",
            or_(
                PlayerGameStat.season < season,
                and_(
                    PlayerGameStat.season == season,
                    PlayerGameStat.week <= week
                    if include_selected_week
                    else PlayerGameStat.week < week,
                ),
            ),
            Game.game_status == "completed",
        )
        .order_by(PlayerGameStat.season.desc(), PlayerGameStat.week.desc(), PlayerGameStat.game_id)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return session.scalars(statement).all()


def history_games(session: Session, player_id: str, rows) -> list[HistoryGame]:
    ids = [r.game_id for r in rows]
    evidence = (
        evidence_models(
            session.scalars(
                select(PlayerGameCompletionEvidence).where(
                    PlayerGameCompletionEvidence.player_id == player_id,
                    PlayerGameCompletionEvidence.game_id.in_(ids),
                )
            ).all()
        )
        if ids
        else []
    )
    now = datetime.now(UTC)
    return [
        HistoryGame(
            **{
                name: getattr(r, name)
                for name in (
                    "season",
                    "week",
                    "game_id",
                    "game_date",
                    "team",
                    "home_away",
                    "fantasy_points_ppr",
                    "carries",
                    "targets",
                    "receptions",
                    "rushing_yards",
                    "receiving_yards",
                    "rushing_tds",
                    "receiving_tds",
                )
            },
            opponent=r.opponent_team,
            touchdowns=r.rushing_tds + r.receiving_tds,
            completion_status=completion_at(evidence, player_id, r.game_id, now),
        )
        for r in rows
    ]


def history(
    session: Session,
    player_id: str,
    season: int,
    week: int,
    limit: int = 8,
    include_selected_week: bool = False,
) -> HistoryResponse:
    player_or_404(session, player_id)
    rows = prior_rows(session, player_id, season, week, limit, include_selected_week)
    return HistoryResponse(
        player_id=player_id,
        target_context=TargetContext(season=season, week=week),
        includes_selected_week=include_selected_week,
        data_as_of=max((r.source_retrieved_at for r in rows), default=None),
        games=history_games(session, player_id, rows),
    )


def versus_opponent(
    session: Session, player_id: str, season: int, week: int, resolved: Matchup | None = None
) -> OpponentResponse:
    player_or_404(session, player_id)
    matchup = resolved or projection(session, player_id, season, week).matchup
    opponent = matchup.opponent
    rows = [
        r
        for r in prior_rows(session, player_id, season, week)
        if opponent and r.opponent_team == opponent
    ]
    games = history_games(session, player_id, rows)
    eligible = [g for g in games if g.completion_status not in ("dnf", "dnp")]
    summary = OpponentSummary()
    missing_stats = (
        session.scalar(
            select(func.count())
            .select_from(PlayerGameParticipation)
            .join(Game, Game.game_id == PlayerGameParticipation.game_id)
            .outerjoin(
                PlayerGameStat,
                and_(
                    PlayerGameStat.player_id == PlayerGameParticipation.player_id,
                    PlayerGameStat.game_id == PlayerGameParticipation.game_id,
                ),
            )
            .where(
                PlayerGameParticipation.player_id == player_id,
                PlayerGameParticipation.team != opponent,
                or_(Game.home_team == opponent, Game.away_team == opponent),
                Game.game_type == "REG",
                Game.game_status == "completed",
                or_(Game.season < season, and_(Game.season == season, Game.week < week)),
                PlayerGameStat.id.is_(None),
            )
        )
        if opponent
        else 0
    )
    if eligible and not missing_stats:
        scores = [g.fantasy_points_ppr for g in eligible]
        summary = OpponentSummary(
            average_ppr=mean(scores),
            median_ppr=median(scores),
            minimum_ppr=min(scores),
            maximum_ppr=max(scores),
            average_targets=mean(g.targets for g in eligible),
            average_carries=mean(g.carries for g in eligible),
            average_receptions=mean(g.receptions for g in eligible),
        )
    if not opponent:
        caveat = "Opponent is unavailable until the selected week's team and schedule are verified."
    elif missing_stats:
        caveat = (
            f"Stat coverage is incomplete for {missing_stats} recorded appearances. "
            "Averages are unavailable; missing scores are not treated as zero."
        )
    elif not games:
        caveat = f"No prior recorded matchups against {opponent} are available in this dataset."
    elif len(eligible) == 1:
        caveat = "One eligible prior matchup is not enough to establish a reliable trend."
    elif len(eligible) < 4:
        caveat = (
            f"Small sample: {len(eligible)} eligible prior matchups. Player roles may have changed."
        )
    else:
        caveat = (
            "Historical context only. Earlier matchups may involve different teams, "
            "coaches, roles, and defensive personnel."
        )
    if eligible:
        caveat += " Averages exclude reported DNFs; unreported early exits may remain."
    return OpponentResponse(
        player_id=player_id,
        opponent=opponent,
        games_count=len(games),
        eligible_games_count=len(eligible),
        missing_stat_games=missing_stats,
        summary=summary,
        caveat=caveat,
        data_as_of=max((r.source_retrieved_at for r in rows), default=None),
        games=[OpponentGame(**g.model_dump(), player_team=g.team) for g in games],
    )


def dashboard(
    session: Session, player_id: str, season: int, week: int, include_selected_week: bool = False
) -> DashboardResponse:
    overview = projection(session, player_id, season, week)
    return DashboardResponse(
        projection=overview,
        recent_history=history(
            session, player_id, season, week, include_selected_week=include_selected_week
        ),
        versus_opponent=versus_opponent(session, player_id, season, week, overview.matchup),
    )


def current_context(session: Session) -> CurrentContext:
    contexts = session.execute(
        select(Game.season, Game.week)
        .where(Game.game_type == "REG")
        .distinct()
        .order_by(Game.season, Game.week)
    ).all()
    weeks: dict[str, list[int]] = {}
    for season, week in contexts:
        weeks.setdefault(str(season), []).append(week)
    next_game = session.scalar(
        select(Game)
        .where(Game.game_type == "REG", Game.game_datetime > datetime.now(UTC))
        .order_by(Game.game_datetime)
        .limit(1)
    )
    default = (
        (next_game.season, next_game.week)
        if next_game
        else (contexts[-1] if contexts else (None, None))
    )
    batch = publication(session, *default) if default[0] else None
    latest_data = session.scalar(select(func.max(PlayerGameStat.source_retrieved_at)))
    return CurrentContext(
        available_seasons=[int(s) for s in weeks],
        available_weeks_by_season=weeks,
        default_season=default[0],
        default_week=default[1],
        latest_data_as_of=latest_data,
        latest_model_version=batch.model_version if batch else None,
        latest_forecast_generation_time=batch.generated_at if batch else None,
        publication_status="published" if batch else "pending",
    )


def rankings(session: Session, season: int, week: int, position: str | None) -> RankingsResponse:
    from src.api.ranking_service import (
        actual_rankings,
        preliminary_rankings,
        target_games,
        week_started,
    )

    games = target_games(session, season, week)
    if week_started(games, datetime.now(UTC)):
        return actual_rankings(session, season, week, position, games)
    batch = publication(session, season, week)
    if batch is None:
        return preliminary_rankings(session, season, week, position)
    rows = session.scalars(
        select(ForecastBatchPlayer).where(ForecastBatchPlayer.batch_id == batch.batch_id)
    ).all()
    projections = [RankingResult.model_validate(r.projection) for r in rows]
    projections = [
        p
        for p in projections
        if p.ranking.position_rank is not None
        and (position is None or p.player.position == position)
    ]
    projections.sort(key=lambda p: (p.player.position, p.ranking.position_rank, p.player.player_id))
    return RankingsResponse(
        season=season,
        week=week,
        batch_id=batch.batch_id,
        generated_at=batch.generated_at,
        data_as_of=batch.data_as_of,
        status="published",
        results=projections[:100],
    )
