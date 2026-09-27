from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from test_schema_mapping import player_stats_fixture

from src.data.schema_validation import SourceSchemaError, load_schema_mapping
from src.data.source_adapter import normalize_dataset

AS_OF = datetime(2026, 9, 19, tzinfo=UTC)
MAPPING = load_schema_mapping(Path(__file__).parents[1] / "configs/source_schema_mapping.yaml")


def typed(dataset: str, values: dict) -> pl.DataFrame:
    schema = {
        spec["chosen_raw_field"]: getattr(pl, spec["raw_dtype"])
        for spec in MAPPING["datasets"][dataset]["fields"].values()
        if spec.get("chosen_raw_field")
    }
    return pl.DataFrame([{key: values.get(key) for key in schema}], schema=schema)


def build_source_frames() -> dict[str, pl.DataFrame]:
    return {
        "player_stats": player_stats_fixture(),
        "schedules": typed(
            "schedules",
            {
                "game_id": "2025_01_TEST",
                "season": 2025,
                "week": 1,
                "game_type": "REG",
                "gameday": "2025-09-07",
                "gametime": "13:00",
                "away_team": "BAL",
                "home_team": "BUF",
                "location": "Home",
                "home_score": 21,
                "away_score": 14,
            },
        ),
        "rosters": typed(
            "rosters",
            {
                "season": 2025,
                "week": 1,
                "game_type": "REG",
                "gsis_id": "00-TEST",
                "pfr_id": "TestPl00",
                "full_name": "Test Player",
                "team": "BUF",
                "position": "WR",
                "status": "ACT",
            },
        ),
        "players": typed(
            "players",
            {
                "gsis_id": "00-TEST",
                "pfr_id": "TestPl00",
                "display_name": "Test Player",
                "position": "WR",
            },
        ),
        "snap_counts": typed(
            "snap_counts",
            {
                "game_id": "2025_01_TEST",
                "season": 2025,
                "week": 1,
                "game_type": "REG",
                "pfr_player_id": "TestPl00",
                "player": "Test Player",
                "team": "BUF",
                "position": "WR",
                "offense_snaps": 25.0,
                "defense_snaps": 0.0,
                "st_snaps": 1.0,
            },
        ),
    }


@pytest.fixture
def source_frames():
    return build_source_frames()


def normalize(frames):
    return normalize_dataset(frames, MAPPING, AS_OF, "fixture")


def test_normalization_scoring_context_and_identity(source_frames):
    data = normalize(source_frames)
    assert data.stats[0]["fantasy_points_ppr"] == pytest.approx(19.9)
    assert data.stats[0]["opponent_team"] == "BAL"
    assert data.stats[0]["home_away"] == "home"
    assert data.games[0]["game_datetime"] == datetime(2025, 9, 7, 17, tzinfo=UTC)
    assert data.participation[0]["player_id"] == "00-TEST"
    assert data.participation[0]["has_stat_record"] is True
    assert data.players[0]["active_status"] == "ACT"


def test_neutral_site_takes_precedence(source_frames):
    source_frames["schedules"] = source_frames["schedules"].with_columns(
        pl.lit("Neutral").alias("location")
    )
    assert normalize(source_frames).stats[0]["home_away"] == "neutral"


def test_away_and_missing_id_fallback(source_frames):
    source_frames["player_stats"] = source_frames["player_stats"].with_columns(
        pl.lit(None, dtype=pl.String).alias("game_id"),
        pl.lit("BAL").alias("team"),
        pl.lit("BUF").alias("opponent_team"),
    )
    row = normalize(source_frames).stats[0]
    assert row["game_id"] == "2025_01_TEST"
    assert row["home_away"] == "away"


def test_unmatched_id_does_not_invent_context(source_frames):
    source_frames["player_stats"] = source_frames["player_stats"].with_columns(
        pl.lit("missing").alias("game_id")
    )
    data = normalize(source_frames)
    assert data.stats[0]["game_id"] is None
    assert data.stats[0]["opponent_team"] is None
    assert data.report["counts"]["unmatched_schedule"] == 1


@pytest.mark.parametrize("field,value", [("team", "NYJ"), ("opponent_team", "NYJ")])
def test_contradictory_schedule_context_rejected(source_frames, field, value):
    source_frames["player_stats"] = source_frames["player_stats"].with_columns(
        pl.lit(value).alias(field)
    )
    with pytest.raises(SourceSchemaError):
        normalize(source_frames)


def test_missing_schedule_game_type_is_reported_not_skipped(source_frames):
    source_frames["schedules"] = source_frames["schedules"].with_columns(
        pl.lit(None, dtype=pl.String).alias("game_type")
    )
    with pytest.raises(SourceSchemaError, match="game_type"):
        normalize(source_frames)


def test_conflicting_duplicates_rejected_identical_collapsed(source_frames):
    original = source_frames["player_stats"]
    source_frames["player_stats"] = pl.concat([original, original])
    assert len(normalize(source_frames).stats) == 1
    source_frames["player_stats"] = pl.concat(
        [original, original.with_columns(pl.lit(1, dtype=pl.Int32).alias("receptions"))]
    )
    with pytest.raises(SourceSchemaError, match="Conflicting duplicate"):
        normalize(source_frames)


@pytest.mark.parametrize("value", [None, -1])
def test_invalid_scoring_values_not_zero_filled(source_frames, value):
    source_frames["player_stats"] = source_frames["player_stats"].with_columns(
        pl.lit(value, dtype=pl.Int32).alias("receptions")
    )
    with pytest.raises(SourceSchemaError):
        normalize(source_frames)


def test_scoring_difference_explained_by_two_points_and_fumbles(source_frames):
    source_frames["player_stats"] = source_frames["player_stats"].with_columns(
        pl.lit(1, dtype=pl.Int32).alias("fumbles_lost_total"),
        pl.lit(1, dtype=pl.Int32).alias("receiving_2pt_conversions"),
        pl.lit(0, dtype=pl.Int32).alias("passing_2pt_conversions"),
        pl.lit(0, dtype=pl.Int32).alias("rushing_2pt_conversions"),
        pl.lit(0, dtype=pl.Int32).alias("special_teams_tds"),
        pl.lit(21.9).alias("fantasy_points_ppr"),
    )
    data = normalize(source_frames)
    assert data.stats[0]["fantasy_points_ppr"] == pytest.approx(17.9)
    diff = data.report["ppr_differences"][0]
    assert diff["explained"]
    assert diff["expected_difference"] == 4


def test_unexplained_difference_remains_visible(source_frames):
    source_frames["player_stats"] = source_frames["player_stats"].with_columns(
        pl.lit(100.0).alias("fantasy_points_ppr")
    )
    assert normalize(source_frames).report["counts"]["unexplained_ppr_differences"] == 1


def test_participation_without_stats_is_not_fabricated_zero(source_frames):
    source_frames["player_stats"] = source_frames["player_stats"].head(0)
    data = normalize(source_frames)
    assert data.stats == []
    assert data.participation[0]["has_stat_record"] is False
    assert data.report["counts"]["participation_without_stats"] == 1


def test_ambiguous_external_ids_not_matched_by_name(source_frames):
    other = source_frames["players"].with_columns(pl.lit("00-OTHER").alias("gsis_id"))
    source_frames["players"] = pl.concat([source_frames["players"], other])
    data = normalize(source_frames)
    assert data.participation == []
    assert data.report["counts"]["unmapped_snap_player"] == 1


def test_future_schedule_is_retained_without_outcomes(source_frames):
    future = deepcopy(source_frames)
    future["schedules"] = future["schedules"].with_columns(
        pl.lit("2026-12-01").alias("gameday"),
        pl.lit(None, dtype=pl.Int32).alias("home_score"),
        pl.lit(None, dtype=pl.Int32).alias("away_score"),
    )
    future["player_stats"] = future["player_stats"].head(0)
    data = normalize(future)
    assert data.games[0]["game_status"] == "upcoming"
    assert data.stats == []


def test_future_final_score_rejected(source_frames):
    source_frames["schedules"] = source_frames["schedules"].with_columns(
        pl.lit("2026-12-01").alias("gameday")
    )
    with pytest.raises(SourceSchemaError, match="future game"):
        normalize(source_frames)
