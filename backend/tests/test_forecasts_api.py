from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from test_ingestion_persistence import source_frames, transaction  # noqa: F401
from test_source_adapter import AS_OF, normalize

from src.api import player_service
from src.core.database import get_db_session
from src.data.persistence import persist_dataset
from src.db.models import (
    ForecastBatch,
    ForecastBatchPlayer,
    ForecastPublication,
    Game,
    Player,
    PlayerGameCompletionEvidence,
    PlayerGameStat,
    PlayerWeeklyRoster,
)
from src.jobs.generate_forecasts import generate_forecasts
from src.main import create_app

pytestmark = pytest.mark.usefixtures("migrate_test_database")
CUTOFF = AS_OF + timedelta(hours=1)
# Relative to the real clock: code under test rejects weeks that have already started.
KICKOFF = max(AS_OF, datetime.now(UTC)) + timedelta(days=8)


@pytest.fixture
def prepared(transaction, source_frames):  # noqa: F811
    persist_dataset(transaction, normalize(source_frames), AS_OF)
    transaction.add(
        Game(
            game_id="2026_03_TEST",
            season=2026,
            week=3,
            game_type="REG",
            game_datetime=KICKOFF,
            game_date=KICKOFF.date(),
            home_team="BUF",
            away_team="BAL",
            game_status="upcoming",
            neutral_site=False,
            source_name="fixture",
            source_retrieved_at=AS_OF,
        )
    )
    for player_id, team in (("00-TEST", "BUF"), ("00-AWAY", "BAL")):
        transaction.add(
            PlayerWeeklyRoster(
                player_id=player_id,
                team=team,
                season=2026,
                week=3,
                game_type="REG",
                position="WR",
                roster_status="ACT",
                data_artifact_id="test",
                source_name="fixture",
                source_retrieved_at=AS_OF,
            )
        )
    transaction.flush()
    return transaction


def finish(session, player_id="00-TEST", status="finished"):
    session.add(
        PlayerGameCompletionEvidence(
            evidence_id=player_id + status,
            player_id=player_id,
            game_id="2025_01_TEST",
            status=status,
            source_url="https://www.nfl.com/news/synthetic-fixture",
            source_published_at=AS_OF - timedelta(days=1),
            retrieved_at=AS_OF,
            reviewed_at=AS_OF,
            reviewer="test",
            evidence_note="Synthetic fixture, not real evidence.",
        )
    )
    session.flush()


@pytest.fixture
def client(prepared):
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: prepared
    with TestClient(app) as client:
        yield client


def test_missing_completion_reports_do_not_block_and_retry_is_idempotent(prepared):
    batch = generate_forecasts(prepared, 2026, 3, CUTOFF)
    assert batch.status == "published"
    assert batch.report["available_count"] == 2
    assert batch.report["unavailable_reasons"] == {}
    assert prepared.scalar(select(func.count()).select_from(ForecastPublication)) == 1
    again = generate_forecasts(prepared, 2026, 3, CUTOFF)
    assert again.batch_id == batch.batch_id


def test_include_selected_week_changes_actuals_only(prepared, client):
    path = "/api/v1/players/00-TEST/dashboard?season=2025&week=1"
    before = client.get(path).json()
    actuals = client.get(path + "&include_selected_week=true").json()
    assert before["recentHistory"]["games"] == []
    assert len(actuals["recentHistory"]["games"]) == 1
    assert actuals["recentHistory"]["games"][0]["week"] == 1
    assert actuals["recentHistory"]["includesSelectedWeek"] is True
    assert actuals["projection"] == before["projection"]
    assert actuals["versusOpponent"] == before["versusOpponent"]
    game = prepared.get(Game, "2025_01_TEST")
    game.game_status = "upcoming"
    prepared.flush()
    assert client.get(path + "&include_selected_week=true").json()["recentHistory"]["games"] == []


def test_schedule_uses_latest_prior_roster_without_publishing_forecast(prepared, client):
    prepared.execute(
        update(PlayerWeeklyRoster).where(PlayerWeeklyRoster.season == 2026).values(week=2)
    )
    prepared.flush()
    result = client.get("/api/v1/players/00-TEST/dashboard?season=2026&week=3").json()
    projection = result["projection"]
    assert projection["player"]["team"] == "BUF"
    assert projection["matchup"]["opponent"] == "BAL"
    assert projection["matchup"]["homeAway"] == "home"
    assert projection["matchup"]["gameDateTime"] is not None
    assert projection["matchup"]["teamContextWeek"] == 2
    assert projection["forecast"]["projectionPpr"] is None
    assert "not confirmation of participation" in projection["caveats"][-1]
    assert result["versusOpponent"]["opponent"] == "BAL"
    # Display fallback must not weaken the separate forecast publication gates.
    assert (
        "incomplete_target_rosters" in generate_forecasts(prepared, 2026, 3, CUTOFF).report["gates"]
    )


def test_schedule_never_uses_future_or_previous_season_roster(prepared):
    prepared.execute(
        update(PlayerWeeklyRoster).where(PlayerWeeklyRoster.season == 2026).values(week=4)
    )
    prepared.flush()
    matchup, team, reason = player_service.matchup_for(prepared, "00-TEST", 2026, 3)
    assert team is None  # Neither Week 4 nor the 2025 stat row is applicable.
    assert matchup.opponent is None
    assert reason == "unverified_roster"


def test_target_week_roster_takes_precedence_over_prior_team(prepared):
    prepared.add(
        PlayerWeeklyRoster(
            player_id="00-TEST",
            team="BAL",
            season=2026,
            week=2,
            game_type="REG",
            position="WR",
            roster_status="ACT",
            data_artifact_id="test",
            source_name="fixture",
            source_retrieved_at=AS_OF,
        )
    )
    prepared.flush()
    matchup, team, reason = player_service.matchup_for(prepared, "00-TEST", 2026, 3)
    assert team == "BUF"
    assert matchup.opponent == "BAL"
    assert matchup.team_context_week == 3
    assert reason is None


def test_conflicting_latest_rosters_do_not_guess_a_team(prepared):
    prepared.add(
        PlayerWeeklyRoster(
            player_id="00-TEST",
            team="BAL",
            season=2026,
            week=3,
            game_type="REG",
            position="WR",
            roster_status="ACT",
            data_artifact_id="test",
            source_name="fixture",
            source_retrieved_at=AS_OF,
        )
    )
    prepared.flush()
    matchup, team, reason = player_service.matchup_for(prepared, "00-TEST", 2026, 3)
    assert team is None
    assert matchup.opponent is None
    assert reason == "unverified_roster"


def test_publication_frozen_and_no_cross_week_fallback(prepared, client):
    finish(prepared)
    batch = generate_forecasts(prepared, 2026, 3, CUTOFF)
    assert batch.status == "published"
    payload = client.get("/api/v1/players/00-TEST/projection?season=2026&week=3").json()
    assert payload["forecast"]["projectionPpr"] == pytest.approx(19.9)
    assert payload["forecast"]["modelName"] == "Trailing-four baseline"
    assert payload["forecast"]["eligibleGamesPrior"] == 1
    assert payload["forecast"]["batchId"] == batch.batch_id
    ranks = client.get("/api/v1/rankings?season=2026&week=3&position=WR").json()
    assert ranks["results"][0]["player"]["playerId"] == "00-TEST"
    assert ranks["results"][0]["ranking"]["combinedScore"] == 50
    prepared.execute(update(PlayerGameStat).values(fantasy_points_ppr=100))
    prepared.execute(update(Player).values(player_name="Corrected name"))
    prepared.flush()
    assert generate_forecasts(prepared, 2026, 3, CUTOFF).batch_id == batch.batch_id
    assert client.get("/api/v1/players/00-TEST/projection?season=2026&week=3").json() == payload
    other = client.get("/api/v1/players/00-TEST/projection?season=2026&week=4").json()
    assert other["forecast"]["projectionPpr"] is None
    assert other["forecast"]["batchId"] is None
    assert client.get("/api/v1/rankings?season=2026&week=4").json()["status"] == "pending"
    saved = prepared.get(ForecastBatchPlayer, (batch.batch_id, "00-TEST"))
    assert saved.features["ppr_points_avg_4"] == pytest.approx(19.9)
    assert batch.inputs["stats"][0]["fantasy_points_ppr"] == pytest.approx(19.9)


def test_dnf_actuals_remain_visible_but_are_excluded(prepared, client):
    finish(prepared, status="dnf")
    response = client.get("/api/v1/players/00-TEST/dashboard?season=2026&week=3")
    assert response.status_code == 200
    data = response.json()
    assert data["recentHistory"]["games"][0]["completionStatus"] == "dnf"
    assert data["recentHistory"]["games"][0]["fantasyPointsPpr"] == pytest.approx(19.9)
    assert data["versusOpponent"]["eligibleGamesCount"] == 0
    assert data["versusOpponent"]["summary"]["averagePpr"] is None
    batch = generate_forecasts(prepared, 2026, 3, CUTOFF)
    assert batch.report["unavailable_reasons"]["insufficient_history"] == 1


def test_opponent_summary_reports_missing_stat_appearances(prepared, client):
    finish(prepared)
    prepared.query(PlayerGameStat).filter_by(player_id="00-TEST").delete()
    prepared.flush()
    response = client.get("/api/v1/players/00-TEST/vs-opponent?season=2026&week=3")
    assert response.status_code == 200
    data = response.json()
    assert data["missingStatGames"] == 1
    assert data["summary"]["averagePpr"] is None
    assert "missing scores are not treated as zero" in data["caveat"]


def test_http_search_and_validation(client):
    found = client.get("/api/v1/players/search?q=Te-st").json()
    assert found["results"][0]["playerId"] == "00-TEST"
    assert client.get("/api/v1/players/search?q=_%").status_code == 422
    assert client.get("/api/v1/players/absent/history?season=2026&week=3").status_code == 404
    assert client.get("/api/v1/players/00-TEST/history?season=2026&week=19").status_code == 422
    assert (
        client.get("/api/v1/players/00-TEST/history?season=2026&week=3&limit=500").status_code
        == 422
    )
    assert client.get("/api/v1/rankings?season=2026&week=3&position=QB").status_code == 422
    context = client.get("/api/v1/meta/current-context").json()
    assert context["latest_data_as_of"] == AS_OF.isoformat().replace("+00:00", "Z")
    assert context["scoring_format"] == "full_ppr"


def test_future_inputs_and_unfinished_previous_game_block(prepared):
    finish(prepared)
    old = prepared.get(Game, "2025_01_TEST")
    old.game_status = "upcoming"
    prepared.flush()
    batch = generate_forecasts(prepared, 2026, 3, AS_OF - timedelta(hours=1))
    assert set(batch.report["gates"]) >= {"prior_games_not_complete", "inputs_newer_than_cutoff"}
    assert batch.status == "blocked"


def test_missing_rosters_and_started_target_block(prepared):
    target = prepared.get(Game, "2026_03_TEST")
    target.game_datetime = AS_OF
    prepared.query(PlayerWeeklyRoster).filter_by(season=2026, team="BAL").delete()
    prepared.flush()
    batch = generate_forecasts(prepared, 2026, 3, CUTOFF)
    assert set(batch.report["gates"]) >= {
        "incomplete_target_rosters",
        "target_week_not_fully_upcoming",
    }


def test_kickoff_before_now_blocks_even_with_stale_upcoming_status(prepared):
    finish(prepared)
    target = prepared.get(Game, "2026_03_TEST")
    target.game_datetime = datetime.now(UTC) - timedelta(minutes=1)
    assert target.game_datetime > CUTOFF and target.game_status == "upcoming"
    prepared.flush()
    batch = generate_forecasts(prepared, 2026, 3, CUTOFF)
    assert batch.status == "blocked"
    assert batch.report["gates"] == ["target_week_started"]
    assert prepared.scalar(select(func.count()).select_from(ForecastPublication)) == 0


def test_database_rejects_snapshot_mutation(prepared):
    finish(prepared)
    generate_forecasts(prepared, 2026, 3, CUTOFF)
    for table in (ForecastBatch, ForecastBatchPlayer, ForecastPublication):
        with pytest.raises(DBAPIError, match="immutable"), prepared.begin_nested():
            prepared.execute(table.__table__.delete())
    with pytest.raises(DBAPIError, match="immutable"), prepared.begin_nested():
        prepared.execute(update(ForecastBatch).values(status="blocked"))


def test_generation_rollback_never_exposes_partial_batch(prepared):
    finish(prepared)
    with pytest.raises(RuntimeError), prepared.begin_nested():
        generate_forecasts(prepared, 2026, 3, CUTOFF)
        raise RuntimeError("Simulated failed transaction")
    assert prepared.scalar(select(func.count()).select_from(ForecastPublication)) == 0
    assert prepared.scalar(select(func.count()).select_from(ForecastBatch)) == 0


def test_inactive_player_is_unavailable_despite_finished_history(prepared):
    finish(prepared)
    prepared.execute(
        update(PlayerWeeklyRoster)
        .where(PlayerWeeklyRoster.season == 2026, PlayerWeeklyRoster.player_id == "00-TEST")
        .values(roster_status="RES")
    )
    batch = generate_forecasts(prepared, 2026, 3, CUTOFF)
    assert batch.report["unavailable_reasons"]["inactive_or_unverified_roster_status"] == 1


def test_http_database_errors_are_redacted():
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("secret database DSN", {}, Exception("password"))

    app = create_app()
    app.dependency_overrides[get_db_session] = unavailable
    with TestClient(app) as client:
        response = client.get("/api/v1/players/search?q=test")
    assert response.status_code == 503
    assert "password" not in response.text
    assert "DSN" not in response.text


def test_empty_database_creates_blocked_report(transaction):  # noqa: F811
    batch = generate_forecasts(transaction, 2026, 3, CUTOFF)
    assert batch.status == "blocked"
    assert batch.data_as_of is None


def test_bad_cutoff_rejected(prepared):
    with pytest.raises(ValueError, match="timezone"):
        generate_forecasts(prepared, 2026, 3, datetime(2026, 9, 19))
    with pytest.raises(ValueError, match="future"):
        generate_forecasts(prepared, 2026, 3, datetime.now(UTC) + timedelta(days=1))


def test_api_transactions_are_read_only_and_repeatable():
    dependency = get_db_session()
    session = next(dependency)
    try:
        assert session.scalar(text("SHOW transaction_read_only")) == "on"
        assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
    finally:
        dependency.close()


def test_api_does_not_execute_models(client, monkeypatch):
    import src.models.baseline

    def forbidden(*args, **kwargs):
        raise AssertionError("Request path invoked a model")

    monkeypatch.setattr(src.models.baseline, "predict_baseline", forbidden)
    assert client.get("/api/v1/players/00-TEST/dashboard?season=2026&week=3").status_code == 200
    assert player_service.POSITIONS == ("RB", "WR", "TE")
