from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from test_forecasts_api import CUTOFF, client, finish, prepared  # noqa: F401
from test_ingestion_persistence import source_frames, transaction  # noqa: F401

from src.db.models import (
    ForecastPublication,
    Game,
    PlayerGameStat,
    PlayerWeeklyRoster,
    RankingPreview,
)
from src.jobs.generate_forecasts import generate_forecasts, record
from src.jobs.prepare_rankings import prepare_rankings, refresh_next_rankings

pytestmark = pytest.mark.usefixtures("migrate_test_database")


def test_previews_are_separate_refreshable_and_position_filtered(prepared, client):  # noqa: F811
    prepared.execute(
        update(PlayerWeeklyRoster)
        .where(
            PlayerWeeklyRoster.season == 2026,
        )
        .values(week=2)
    )
    response = prepare_rankings(prepared, 2026, 3)
    assert response.status == "preliminary"
    assert len(response.results) == 2
    assert response.results[0].forecast.projection_ppr == pytest.approx(19.9)
    assert response.results[0].forecast.batch_id is None
    assert response.results[0].matchup.team_context_week == 2
    assert response.results[0].ranking.position_rank == 1
    assert prepared.scalar(select(func.count()).select_from(ForecastPublication)) == 0
    path = "/api/v1/rankings?season=2026&week=3&position="
    assert len(client.get(path + "WR").json()["results"]) == 2
    assert client.get(path + "RB").json()["results"] == []
    assert client.get(path + "TE").json()["results"] == []
    prepared.execute(update(PlayerGameStat).values(fantasy_points_ppr=30))
    prepare_rankings(prepared, 2026, 3)
    assert prepared.scalar(select(func.count()).select_from(RankingPreview)) == 1
    assert client.get(path + "WR").json()["results"][0]["forecast"]["projectionPpr"] == 30


def test_previews_exclude_reported_dnf_and_inactive_players(prepared):  # noqa: F811
    finish(prepared, status="dnf")
    response = prepare_rankings(prepared, 2026, 3)
    assert [r.player.player_id for r in response.results] == ["00-AWAY"]
    prepared.execute(
        update(PlayerWeeklyRoster)
        .where(
            PlayerWeeklyRoster.player_id == "00-AWAY",
            PlayerWeeklyRoster.season == 2026,
        )
        .values(roster_status="RES")
    )
    assert prepare_rankings(prepared, 2026, 3).results == []


def test_previews_cannot_be_backdated_and_actuals_replace_stored_preview(prepared, client):  # noqa: F811
    prepare_rankings(prepared, 2026, 3)
    target = prepared.get(Game, "2026_03_TEST")
    target.game_datetime = datetime.now(UTC) - timedelta(minutes=1)
    prepared.flush()
    with pytest.raises(ValueError, match="fully upcoming"):
        prepare_rankings(prepared, 2026, 3)
    response = client.get("/api/v1/rankings?season=2026&week=3&position=WR").json()
    assert response["status"] == "actual"
    assert response["results"] == []
    assert response["completedGames"] == 0


def test_published_forecast_supersedes_preliminary_without_mutating_it(prepared, client):  # noqa: F811
    prepare_rankings(prepared, 2026, 3)
    batch = generate_forecasts(prepared, 2026, 3, CUTOFF)
    response = client.get("/api/v1/rankings?season=2026&week=3&position=WR").json()
    assert response["status"] == "published"
    assert response["batchId"] == batch.batch_id
    # Strict publication retains its original coverage gate: only one fixture
    # player has complete opponent snap/stat coverage.
    assert [r["player"]["playerId"] for r in response["results"]] == ["00-TEST"]


def test_actual_results_include_zero_and_dnf_without_inventing_forecasts(prepared, client):  # noqa: F811
    finish(prepared, status="dnf")
    prepared.execute(
        update(PlayerGameStat)
        .where(
            PlayerGameStat.player_id == "00-AWAY",
        )
        .values(fantasy_points_ppr=0)
    )
    response = client.get("/api/v1/rankings?season=2025&week=1&position=WR").json()
    assert response["status"] == "actual"
    assert response["completedGames"] == response["totalGames"] == 1
    assert [r["actualPpr"] for r in response["results"]] == [19.9, 0]
    assert response["results"][0]["completionStatus"] == "dnf"
    assert all(r["forecast"]["projectionPpr"] is None for r in response["results"])
    assert all(r["ranking"]["combinedScore"] is None for r in response["results"])
    assert client.get("/api/v1/rankings?season=2025&week=1&position=TE").json()["results"] == []


def test_actual_ranks_preserve_ties(prepared, client):  # noqa: F811
    response = client.get("/api/v1/rankings?season=2025&week=1&position=WR").json()
    assert [r["ranking"]["positionRank"] for r in response["results"]] == [1, 1]


def test_preliminary_inputs_exclude_target_week_even_if_a_stat_row_exists(prepared):  # noqa: F811
    original = prepared.scalar(select(PlayerGameStat).where(PlayerGameStat.player_id == "00-TEST"))
    values = record(original)
    values.pop("id")
    values.update(season=2026, week=3, game_id="2026_03_TEST", fantasy_points_ppr=999)
    prepared.add(PlayerGameStat(**values))
    prepared.flush()
    result = prepare_rankings(prepared, 2026, 3)
    player = next(row for row in result.results if row.player.player_id == "00-TEST")
    assert player.forecast.projection_ppr == pytest.approx(19.9)


def test_partial_actual_week_reports_coverage(prepared, client):  # noqa: F811
    values = record(prepared.get(Game, "2025_01_TEST"))
    values.update(game_id="2025_01_OTHER", home_team="BAL", away_team="BUF", game_status="upcoming")
    prepared.add(Game(**values))
    prepared.flush()
    response = client.get("/api/v1/rankings?season=2025&week=1&position=WR").json()
    assert response["completedGames"] == 1
    assert response["totalGames"] == 2
    assert len(response["results"]) == 2


def test_next_week_refresh_and_read_path_never_run_models(prepared, client, monkeypatch):  # noqa: F811
    result = refresh_next_rankings(prepared)
    assert result.week == 3
    import src.jobs.prepare_rankings as job

    def forbidden(*args, **kwargs):
        raise AssertionError("API invoked a model")

    monkeypatch.setattr(job, "predict_baseline", forbidden)
    assert client.get("/api/v1/rankings?season=2026&week=3").status_code == 200
    assert client.get("/api/v1/rankings?season=2025&week=1").status_code == 200
