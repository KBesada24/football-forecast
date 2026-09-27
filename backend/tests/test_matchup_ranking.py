import pytest

from src.api.schemas.players import Forecast, Matchup, PlayerInfo, ProjectionResponse, Ranking
from src.features.matchup_ranking import apply_rankings, opponent_context, percentile


def candidate(player_id, points, allowance, position="WR"):
    return ProjectionResponse(
        availability="available",
        player=PlayerInfo(
            player_id=player_id,
            display_name=player_id,
            position=position,
        ),
        matchup=Matchup(season=2026, week=3),
        forecast=Forecast(projection_ppr=points),
        ranking=Ranking(opponent_ppr_per_appearance=allowance),
    )


def test_combined_rank_weights_both_components_and_keeps_positions_separate():
    high_points = candidate("p1", 30, 10)
    favorable = candidate("p2", 10, 30)
    both = candidate("p3", 20, 20)
    running_back = candidate("rb", 100, 100, "RB")
    missing = candidate("missing", 99, None)
    apply_rankings([high_points, favorable, both, running_back, missing])
    for p in (high_points, favorable, both, running_back):
        assert p.ranking.combined_score == 50
        assert p.ranking.position_rank == 1
    assert high_points.ranking.projection_percentile == 100
    assert high_points.ranking.favorability_percentile == 0
    assert missing.ranking.position_rank is None


def test_percentile_ties_and_competition_ranks():
    assert percentile(10, [0, 10, 10, 30]) == 50
    rows = [candidate("a", 10, 10), candidate("b", 10, 10), candidate("c", 0, 0)]
    apply_rankings(rows)
    assert [p.ranking.position_rank for p in rows] == [1, 1, 3]


def test_opponent_uses_last_four_games_actual_scores_and_sample_sizes():
    games = [
        {"game_id": str(i), "season": 2026, "week": i, "home_team": "BUF", "away_team": "BAL"}
        for i in range(1, 6)
    ]
    stats = [
        {
            "game_id": str(i),
            "player_id": "p",
            "team": "BUF",
            "position": "WR",
            "fantasy_points_ppr": i * 10,
        }
        for i in range(1, 6)
    ]
    snaps = [{"game_id": str(i), "player_id": "p", "team": "BUF"} for i in range(1, 6)]
    context = opponent_context("BAL", "WR", games, stats, snaps)
    assert context.opponent_games == 4
    assert context.opponent_appearances == 4
    assert context.opponent_ppr_per_appearance == pytest.approx(35)
    stats.pop()
    assert opponent_context("BAL", "WR", games, stats, snaps).opponent_ppr_per_appearance is None
    partial = opponent_context("BAL", "WR", games, stats, snaps, allow_partial=True)
    assert partial.opponent_ppr_per_appearance == pytest.approx(30)
    assert partial.opponent_missing_stat_appearances == 1
    assert partial.opponent_appearances == 3
    assert partial.unavailable_reason == "partial_opponent_coverage"


def test_no_opponent_or_unverified_appearances_never_get_neutral_score():
    assert opponent_context(None, "WR", [], [], []).opponent_ppr_per_appearance is None
    game = {"game_id": "1", "season": 2026, "week": 1, "home_team": "BUF", "away_team": "BAL"}
    stat = {
        "game_id": "1",
        "player_id": "p",
        "team": "BUF",
        "position": "WR",
        "fantasy_points_ppr": 20,
    }
    assert opponent_context("BAL", "WR", [game], [stat], []).unavailable_reason
