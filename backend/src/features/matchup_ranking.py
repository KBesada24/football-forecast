"""Descriptive opponent context and a versioned within-position blended rank."""

from statistics import mean

from src.api.schemas.players import ProjectionResponse, Ranking

RANKING_VERSION = "position_percentile_50_50_v1"


def opponent_context(
    opponent, position, games, stats, participation, *, allow_partial=False
) -> Ranking:
    recent = sorted(
        [g for g in games if opponent in (g["home_team"], g["away_team"])],
        key=lambda g: (g["season"], g["week"], g["game_id"]),
    )[-4:]
    ids = {g["game_id"] for g in recent}
    rows = [r for r in stats if r["game_id"] in ids and r["team"] != opponent]
    appearances = [r for r in rows if r["position"] == position]
    stat_keys = {(r["game_id"], r["player_id"]) for r in rows}
    snaps = [r for r in participation if r["game_id"] in ids and r["team"] != opponent]
    snap_keys = {(r["game_id"], r["player_id"]) for r in snaps}
    # Unknown position on a missing-stat appearance is conservatively a coverage gap.
    complete = (
        bool(recent)
        and bool(appearances)
        and {r["game_id"] for r in rows} == ids
        and {r["game_id"] for r in snaps} == ids
        and snap_keys <= stat_keys
        and all((r["game_id"], r["player_id"]) in snap_keys for r in appearances)
    )
    return Ranking(
        opponent_missing_stat_appearances=len(snap_keys - stat_keys),
        opponent_games=len(recent),
        opponent_appearances=len(appearances),
        opponent_ppr_per_appearance=mean(r["fantasy_points_ppr"] for r in appearances)
        if complete or (allow_partial and appearances)
        else None,
        unavailable_reason=None
        if complete
        else "partial_opponent_coverage"
        if allow_partial and appearances
        else "incomplete_opponent_coverage",
    )


def percentile(value: float, population: list[float]) -> float:
    if len(population) == 1:
        return 50.0
    below = sum(v < value for v in population)
    tied = sum(v == value for v in population)
    return 100 * (below + (tied - 1) / 2) / (len(population) - 1)


def apply_rankings(projections: list[ProjectionResponse]) -> None:
    for position in ("RB", "WR", "TE"):
        eligible = [
            p
            for p in projections
            if p.player.position == position
            and p.availability == "available"
            and p.ranking.opponent_ppr_per_appearance is not None
        ]
        points = [p.forecast.projection_ppr for p in eligible]
        favorable = [p.ranking.opponent_ppr_per_appearance for p in eligible]
        for p in eligible:
            p.ranking.projection_percentile = percentile(p.forecast.projection_ppr, points)
            p.ranking.favorability_percentile = percentile(
                p.ranking.opponent_ppr_per_appearance, favorable
            )
            p.ranking.combined_score = (
                p.ranking.projection_percentile + p.ranking.favorability_percentile
            ) / 2
        for p in eligible:
            p.ranking.position_rank = 1 + sum(
                other.ranking.combined_score > p.ranking.combined_score for other in eligible
            )
