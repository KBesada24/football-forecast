from datetime import UTC, datetime, timedelta
from itertools import permutations
from random import Random

import pytest
from pydantic import ValidationError

from src.data.lineup_data import defense_inputs
from src.domain.completion import CompletionEvidence
from src.domain.espn import KICKING, OFFENSE, defense_points, player_points
from src.domain.lineup import ELIGIBILITY, LineupRequest, optimize
from src.features.lineup_features import FeatureIndex
from src.models.lineup_model import evaluate, fit, predict


def player(pid, pos, points):
    return {"id": pid, "position": pos, "projection": points, "unavailable_reason": None}


def test_espn_offense_two_point_return_and_zero():
    row = dict.fromkeys(OFFENSE, 0)
    row["position"] = "WR"
    assert player_points(row) == 0
    row.update(
        receptions=5,
        receiving_yards=100,
        receiving_tds=1,
        receiving_2pt_conversions=1,
        special_teams_tds=1,
        fumble_recovery_tds=1,
        fumbles_lost_total=1,
    )
    assert player_points(row) == 33
    row["receiving_yards"] = None
    with pytest.raises(ValueError):
        player_points(row)


def test_espn_kicker_distances_and_blocked_attempts():
    row = {
        **dict.fromkeys(OFFENSE, 0),
        **dict.fromkeys(KICKING, 0),
        "position": "K",
        "fg_att": 8,
        "fg_made": 6,
        "fg_made_0_19": 1,
        "fg_made_20_29": 1,
        "fg_made_30_39": 1,
        "fg_made_40_49": 1,
        "fg_made_50_59": 1,
        "fg_made_60_": 1,
        "pat_made": 2,
    }
    assert player_points(row) == 24


def defense(**values):
    return {
        "points_allowed": 0,
        "yards_allowed": 0,
        "sacks": 0,
        "interceptions": 0,
        "recoveries": 0,
        "blocked_kicks": 0,
        "safeties": 0,
        "touchdowns": 0,
        "conversion_returns": 0,
        "pat_safeties": 0,
        **values,
    }


@pytest.mark.parametrize(
    "yards,score",
    [
        (99, 5),
        (100, 3),
        (199, 3),
        (200, 2),
        (299, 2),
        (300, 0),
        (349, 0),
        (350, -1),
        (399, -1),
        (400, -3),
        (449, -3),
        (450, -5),
        (499, -5),
        (500, -6),
        (549, -6),
        (550, -7),
    ],
)
def test_defense_yard_tier_boundaries(yards, score):
    assert defense_points(defense(points_allowed=20, yards_allowed=yards)) == score


@pytest.mark.parametrize(
    "pa,score",
    [
        (0, 5),
        (1, 4),
        (6, 4),
        (7, 3),
        (13, 3),
        (14, 1),
        (17, 1),
        (18, 0),
        (27, 0),
        (28, -1),
        (34, -1),
        (35, -3),
        (45, -3),
        (46, -5),
    ],
)
def test_defense_points_tier_boundaries(pa, score):
    assert defense_points(defense(points_allowed=pa, yards_allowed=300)) == score


def test_defense_pbp_excludes_pick_six_but_keeps_pat_and_special_teams():
    game = {
        "home_team": "A",
        "away_team": "B",
        "home_score": 7,
        "away_score": 14,
        "game_id": "test",
    }
    team = {
        "team": "A",
        "def_sacks": 1,
        "def_interceptions": 0,
        "def_punt_blocks": 0,
        "def_pat_blocks": 0,
        "def_fg_blocks": 0,
    }
    opponent = {"team": "B", "passing_yards": 250, "rushing_yards": 50, "sack_yards_lost": -20}
    plays = [
        {
            "home_score": 7,
            "away_score": 14,
            "posteam": "A",
            "defteam": "B",
            "td_team": "B",
            "touchdown": 1,
        },
        {
            "home_score": 7,
            "away_score": 14,
            "posteam": "A",
            "defteam": "B",
            "td_team": "B",
            "touchdown": 1,
            "punt_attempt": 1,
        },
    ]
    result = defense_inputs(team, opponent, game, plays)
    assert result["points_allowed"] == 8  # TD on punt + both PATs count
    assert result["yards_allowed"] == 280
    assert result["touchdowns"] == 0
    # No recovered fumble is manufactured from opponents' fumbles-lost total.
    assert result["recoveries"] == 0


def test_optimizer_complete_flex_and_locks():
    players = [
        player("q", "QB", 20),
        player("r1", "RB", 17),
        player("r2", "RB", 14),
        player("r3", "RB", 13),
        player("w1", "WR", 21),
        player("w2", "WR", 12),
        player("w3", "WR", 11),
        player("t", "TE", 9),
        player("k", "K", 7),
        player("d", "DST", -2),
    ]
    req = LineupRequest(season=2026, week=3, roster=[p["id"] for p in players])
    result = optimize(req, players)
    assert result["complete"]
    assert result["total"] == 111
    assert result["starters"][6]["player"]["id"] == "r3"
    req.locks = {6: "w3"}
    result = optimize(req, players)
    assert result["starters"][6]["player"]["id"] == "w3"
    assert result["total"] == 109


def test_optimizer_matches_brute_force():
    rng = Random(813)
    for _ in range(20):
        players = [
            player(str(i), rng.choice(["RB", "WR", "TE"]), rng.uniform(-3, 25)) for i in range(7)
        ]
        slots = ["RB", "WR", "FLEX"]
        req = LineupRequest(season=2026, week=3, roster=[p["id"] for p in players], slots=slots)
        feasible = [
            sum(p["projection"] for p in combo)
            for combo in permutations(players, 3)
            if all(p["position"] in ELIGIBILITY[s] for p, s in zip(combo, slots, strict=True))
        ]
        result = optimize(req, players)
        if feasible:
            assert result["total"] == round(max(feasible), 2)
            assert result["complete"]
        assert len({s["player"]["id"] for s in result["starters"] if s["player"]}) == sum(
            s["player"] is not None for s in result["starters"]
        )


def test_optimizer_incomplete_excluded_and_invalid_inputs():
    players = [player("r", "RB", 10), player("q", "QB", None)]
    req = LineupRequest(season=2026, week=3, roster=["r", "q"])
    assert not optimize(req, players)["complete"]
    req.excluded = ["r"]
    assert optimize(req, players)["total"] == 0
    req.locks = {0: "r"}
    with pytest.raises(ValueError):
        optimize(req, players)
    with pytest.raises(ValidationError):
        LineupRequest(season=2026, week=3, roster=["r", "r"])
    with pytest.raises(ValidationError):
        LineupRequest(season=2026, week=3, roster=["r"], slots=["SUPERFLEX"])


def history_row(week, score, season=2025):
    return {
        "id": "p",
        "position": "WR",
        "team": "A",
        "opponent": "B",
        "game_id": f"{season}:{week}",
        "season": season,
        "week": week,
        "kickoff": datetime(season, 1, 1, tzinfo=UTC) + timedelta(weeks=week),
        "points": score,
        "missing": score is None,
        "targets": 5,
        "carries": 0,
        "attempts": 0,
    }


def test_latest_five_cross_season_zero_old_hole_and_no_target_leak():
    rows = [history_row(w, None if w == 1 else 0 if w == 2 else w) for w in range(1, 7)]
    rows += [history_row(1, 999, season=2026)]
    f = FeatureIndex(rows).build("p", "WR", "B", 2026, 1, datetime(2026, 9, 1, tzinfo=UTC))
    assert f["average5"] == 3.6
    assert f["sample"] == 5
    assert not f["unavailable_reason"]
    rows.append(history_row(7, None))
    assert FeatureIndex(rows).build("p", "WR", "B", 2026, 1, datetime(2026, 9, 1, tzinfo=UTC))[
        "unavailable_reason"
    ]


def test_reported_dnf_excluded_but_unknown_completion_counts():
    rows = [history_row(w, w) for w in range(1, 7)]
    stamp = datetime(2025, 4, 1, tzinfo=UTC)
    evidence = CompletionEvidence(
        player_id="p",
        game_id="2025:6",
        status="dnf",
        source_url="https://example.com/report",
        source_published_at=stamp,
        retrieved_at=stamp,
        reviewed_at=stamp,
        evidence_note="Synthetic injury report fixture",
        reviewer="test",
    )
    f = FeatureIndex(rows, [evidence]).build(
        "p", "WR", "C", 2026, 1, datetime(2026, 9, 1, tzinfo=UTC)
    )
    assert f["average5"] == 3
    assert f["head_to_head"]["sample"] == 0
    assert f["defense"]["relative"] == 0
    assert f["sample"] == 5


def test_defense_uses_position_totals_not_averages_per_player():
    a = history_row(1, 10)
    b = {**a, "id": "second", "points": 20}
    f = FeatureIndex([a, b]).build("p", "WR", "B", 2026, 1, datetime(2026, 9, 1, tzinfo=UTC))
    assert f["defense"]["average"] == 30
    assert f["defense"]["sample"] == 1


def test_ridge_fits_offline_and_frozen_coefficients_are_reusable():
    samples = [
        {
            "features": {
                "vector": [i, i / 2],
                "average5": i,
                "weighted5": i,
                "unavailable_reason": None,
            },
            "actual": i * 2,
            "season": 2024,
            "week": 1,
        }
        for i in range(20)
    ]
    model = fit(samples, 1)
    assert abs(predict(model, samples[10]["features"]) - 20) < 0.1
    assert evaluate(model, samples)["mae"] < evaluate({"kind": "mean5"}, samples)["mae"]
