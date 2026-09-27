import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.body_limit import MAX_LINEUP_BYTES, LineupBodyLimit
from src.domain.espn import POSITIONS
from src.jobs import prepare_lineups, weekly_refresh
from src.jobs.publication_checks import (
    CoverageError,
    NoPublicationWindow,
    coverage_report,
    target_week,
)
from src.main import create_app

NOW = datetime(2026, 9, 22, 12, tzinfo=UTC)


def game(week, kickoff, status="upcoming"):
    return {
        "game_id": f"2026-{week}-A-B",
        "season": 2026,
        "week": week,
        "home_team": "A",
        "away_team": "B",
        "game_datetime": kickoff,
        "game_status": status,
    }


@pytest.fixture
def inputs():
    previous = game(2, NOW - timedelta(days=2), "completed")
    return {
        "games": [previous, game(3, NOW + timedelta(days=2))],
        "rows": [
            {
                "game_id": previous["game_id"],
                "team": team,
                "position": position,
                "points": 0,
                "missing": False,
            }
            for team in ("A", "B")
            for position in POSITIONS
        ],
    }


@pytest.fixture
def payload():
    return {
        "snapshot_id": "a" * 32,
        "season": 2026,
        "week": 3,
        "first_kickoff": (NOW + timedelta(days=2)).isoformat(),
        "players": [
            {"position": pos, "projection": 0, "unavailable_reason": None} for pos in POSITIONS
        ],
    }


def test_intended_week_and_no_skipping(inputs):
    assert target_week(inputs["games"], 2026, NOW) == 3
    inputs["games"][1]["game_datetime"] = NOW - timedelta(hours=1)
    inputs["games"][1]["game_status"] = "completed"
    inputs["games"].append(game(4, NOW + timedelta(days=9)))
    assert target_week(inputs["games"], 2026, NOW) == 3  # preparation must reject, not select 4
    inputs["games"].pop(1)
    with pytest.raises(ValueError, match="missing"):
        target_week(inputs["games"], 2026, NOW)


def test_january_and_dst_use_explicit_nfl_season():
    now = datetime(2027, 1, 5, 13, tzinfo=UTC)
    assert target_week([game(18, now + timedelta(days=5))], 2026, now) == 18
    # Tuesday midnight Eastern is still Monday in no other timezone we use.
    now = datetime(2026, 11, 3, 5, tzinfo=UTC)
    assert target_week([game(9, now + timedelta(days=2))], 2026, now) == 9


def test_offseason_missing_and_ambiguous_schedule(inputs):
    with pytest.raises(NoPublicationWindow):
        target_week(inputs["games"], 2026, NOW - timedelta(days=30))
    with pytest.raises(ValueError, match="absent"):
        target_week([], 2026, NOW)
    inputs["games"].append(game(4, NOW + timedelta(days=3)))
    with pytest.raises(ValueError, match="Ambiguous"):
        target_week(inputs["games"], 2026, NOW)


def test_good_coverage_zero_scores_and_individual_exclusion(inputs, payload):
    payload["players"].append(
        {"position": "WR", "projection": None, "unavailable_reason": "Insufficient history"}
    )
    report = coverage_report(inputs, payload, NOW)
    assert report["status"] == "passed"
    assert report["excluded_players"] == {"Insufficient history": 1}


@pytest.mark.parametrize("position", POSITIONS)
def test_empty_supported_position_blocks(inputs, payload, position):
    payload["players"] = [p for p in payload["players"] if p["position"] != position]
    assert (
        f"No usable projections for {position}" in coverage_report(inputs, payload, NOW)["errors"]
    )


@pytest.mark.parametrize("missing", ["DST", "K", "offense"])
def test_previous_week_source_gaps_block(inputs, payload, missing):
    drop = {"QB", "RB", "WR", "TE"} if missing == "offense" else {missing}
    inputs["rows"] = [r for r in inputs["rows"] if r["position"] not in drop]
    assert coverage_report(inputs, payload, NOW)["status"] == "blocked"


def test_unfinished_previous_week_blocks(inputs, payload):
    inputs["games"][0]["game_status"] = "unavailable"
    assert coverage_report(inputs, payload, NOW)["status"] == "blocked"


def test_week_one_uses_history_not_week_zero(inputs, payload):
    payload["week"] = 1
    inputs["games"] = []
    inputs["rows"] = []
    report = coverage_report(inputs, payload, NOW)
    assert report["status"] == "passed"
    assert report["week_one_history_only"]


def test_no_db_insert_when_coverage_fails(inputs, payload, tmp_path, monkeypatch):
    class Clock:
        @staticmethod
        def now(_tz):
            return NOW

    class EvidenceSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalars(self, _query):
            return SimpleNamespace(all=lambda: [])

    sessions = []

    def session():
        sessions.append(1)
        assert len(sessions) == 1, "Publication must not open a write session"
        return EvidenceSession()

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "lineup-model-v1.json").write_text("{}")
    monkeypatch.setattr(
        prepare_lineups,
        "get_settings",
        lambda: SimpleNamespace(data_dir=tmp_path, model_dir=model_dir),
    )
    monkeypatch.setattr(prepare_lineups, "datetime", Clock)
    monkeypatch.setattr(prepare_lineups, "supplement", lambda *_: None)
    monkeypatch.setattr(prepare_lineups, "load_inputs", lambda *_: inputs)
    monkeypatch.setattr(prepare_lineups, "SessionLocal", session)
    payload["players"] = []
    monkeypatch.setattr(prepare_lineups, "prepare", lambda *_: payload)
    with pytest.raises(CoverageError):
        prepare_lineups.run(tmp_path, 2026, 3, False)
    assert json.loads((tmp_path / "lineups" / ("a" * 32) / "coverage-report.json").read_text())[
        "errors"
    ]


def test_preparation_rejects_started_week(inputs):
    inputs["games"][1]["game_datetime"] = NOW
    from src.domain.espn import SCORING_VERSION
    from src.features.lineup_features import FEATURE_VERSION

    model = {"feature_version": FEATURE_VERSION, "scoring_version": SCORING_VERSION}
    with pytest.raises(ValueError, match="fully upcoming"):
        prepare_lineups.prepare(inputs, model, [], 2026, 3, NOW)


def test_weekly_explicit_season_and_partial_progress(tmp_path, monkeypatch):
    seasons = []
    monkeypatch.setattr(weekly_refresh, "verify_model", lambda: None)

    def ingest(requested, *_):
        seasons.extend(requested)
        return {"snapshot": str(tmp_path)}

    monkeypatch.setattr(weekly_refresh, "ingest", ingest)

    def fail(*_):
        raise ValueError("secret-looking error should not enter result file")

    monkeypatch.setattr(weekly_refresh, "prepare_lineups", fail)
    result = tmp_path / "result.json"
    with pytest.raises(ValueError):
        weekly_refresh.run(2026, result)
    assert seasons == [2024, 2025, 2026]
    recorded = json.loads(result.read_text())
    assert recorded["stage"] == "lineup_preparation"
    assert recorded["ingestion"]
    assert "secret-looking" not in result.read_text()


def test_model_checksum_before_ingestion(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly_refresh, "get_settings", lambda: SimpleNamespace(model_dir=tmp_path))
    path = tmp_path / "lineup-model-v1.json"
    path.write_text("{}")
    path.with_suffix(".json.sha256").write_text("0" * 64)
    with pytest.raises(ValueError, match="checksum"):
        weekly_refresh.verify_model()


@pytest.mark.parametrize("claimed_length", [None, b"1", b"999999"])
@pytest.mark.parametrize("size,expected", [(MAX_LINEUP_BYTES, 200), (MAX_LINEUP_BYTES + 1, 413)])
def test_stream_body_bound_before_app(claimed_length, size, expected):
    called = []
    messages = [
        {"type": "http.request", "body": b"x" * 8000, "more_body": True},
        {"type": "http.request", "body": b"x" * (size - 8000), "more_body": False},
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def app(_scope, recv, send):
        called.append(True)
        assert len((await recv())["body"]) == size
        await send({"type": "http.response.start", "status": 200, "headers": []})

    headers = [] if claimed_length is None else [(b"content-length", claimed_length)]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/lineups/optimize",
        "headers": headers,
    }
    asyncio.run(LineupBodyLimit(app)(scope, receive, send))
    assert sent[0]["status"] == expected
    assert bool(called) == (expected == 200)


def test_direct_backend_limit_and_read_only_filesystem(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("API startup must not create source directories")

    monkeypatch.setattr(Path, "mkdir", forbidden)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 200
        response = client.post("/api/v1/lineups/optimize", content=b"x" * 16_385)
        assert response.status_code == 413
        assert client.post("/api/v1/lineups/optimize", json={}).status_code == 422


def test_api_engine_never_prepares_statements():
    from src.core.database import engine

    with engine.connect() as connection:
        assert connection.connection.driver_connection.prepare_threshold is None


def test_api_engine_verifies_configured_ca(tmp_path):
    from src.core.database import connect_args

    cert = tmp_path / "ca.crt"
    assert connect_args(SimpleNamespace(database_ca_cert=None)) == {"prepare_threshold": None}
    assert connect_args(SimpleNamespace(database_ca_cert=cert))["sslrootcert"] == str(cert)


@pytest.mark.parametrize(
    ("port", "sslmode", "has_cert", "message"),
    [
        (6543, "verify-full", True, "transaction pooler"),
        (5432, "require", True, "verify-full"),
        (5432, "verify-full", False, "PGSSLROOTCERT"),
        (5432, "verify-full", True, None),
    ],
)
def test_worker_requires_session_pooler_and_verified_tls(
    tmp_path, monkeypatch, port, sslmode, has_cert, message
):
    from src.jobs.refresh_preflight import check_database_connection

    host = "aws-0-us-east-1.pooler.supabase.com"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+psycopg://owner.ref:secret@{host}:{port}/postgres?sslmode={sslmode}",
    )
    cert = tmp_path / "ca.crt"
    if has_cert:
        cert.write_text("test certificate")
    monkeypatch.setenv("PGSSLROOTCERT", str(cert))
    if message is None:
        check_database_connection()
    else:
        with pytest.raises(ValueError, match=message):
            check_database_connection()


def test_preflight_failure_output_is_redacted(monkeypatch, capsys):
    from src.jobs import refresh_preflight

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://owner.ref:secret@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
    )
    with pytest.raises(SystemExit):
        refresh_preflight.main()
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "preflight_failed", "error_type": "ValueError"}
    assert "secret" not in output
