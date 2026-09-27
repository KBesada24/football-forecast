import pytest
from sqlalchemy import inspect

from src.core.database import engine

pytestmark = pytest.mark.usefixtures("migrate_test_database")


def test_initial_migration_creates_required_tables() -> None:
    expected_tables = {
        "alembic_version",
        "data_ingestion_runs",
        "forecast_generation_runs",
        "games",
        "model_versions",
        "player_game_stats",
        "player_week_features",
        "player_week_predictions",
        "players",
        "teams",
        "player_weekly_rosters",
        "player_game_participation",
        "player_game_completion_evidence",
        "forecast_batches",
        "forecast_batch_players",
        "forecast_publications",
        "ranking_previews",
    }

    assert expected_tables <= set(inspect(engine).get_table_names())
