from pathlib import Path

import polars as pl
import pytest

from src.data.schema_validation import (
    SourceSchemaError,
    load_schema_mapping,
    validate_source_schema,
)

MAPPING_PATH = Path(__file__).parents[1] / "configs" / "source_schema_mapping.yaml"


def player_stats_fixture() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": pl.Series([2025], dtype=pl.Int32),
            "week": pl.Series([1], dtype=pl.Int32),
            "season_type": ["REG"],
            "game_id": ["2025_01_TEST"],
            "player_id": ["00-TEST"],
            "player_display_name": ["Test Player"],
            "position": ["WR"],
            "team": ["BUF"],
            "opponent_team": ["BAL"],
            "headshot_url": pl.Series([None], dtype=pl.String),
            "passing_yards": pl.Series([0], dtype=pl.Int32),
            "passing_tds": pl.Series([0], dtype=pl.Int32),
            "passing_interceptions": pl.Series([0], dtype=pl.Int32),
            "carries": pl.Series([1], dtype=pl.Int32),
            "rushing_yards": pl.Series([4], dtype=pl.Int32),
            "rushing_tds": pl.Series([0], dtype=pl.Int32),
            "rushing_fumbles_lost": pl.Series([0], dtype=pl.Int32),
            "targets": pl.Series([8], dtype=pl.Int32),
            "receptions": pl.Series([6], dtype=pl.Int32),
            "receiving_yards": pl.Series([75], dtype=pl.Int32),
            "receiving_tds": pl.Series([1], dtype=pl.Int32),
            "receiving_fumbles_lost": pl.Series([0], dtype=pl.Int32),
            "sack_fumbles_lost": pl.Series([0], dtype=pl.Int32),
            "fumbles_lost_total": pl.Series([0], dtype=pl.Int32),
            "fantasy_points_ppr": [19.9],
        }
    )


def test_verified_player_stats_mapping_matches_fixture() -> None:
    mapping = load_schema_mapping(MAPPING_PATH)

    validate_source_schema(player_stats_fixture(), mapping, "player_stats")


def test_missing_scoring_field_fails_with_actionable_error() -> None:
    mapping = load_schema_mapping(MAPPING_PATH)
    frame = player_stats_fixture().drop("receptions")

    with pytest.raises(SourceSchemaError, match="receptions <- receptions"):
        validate_source_schema(frame, mapping, "player_stats")
