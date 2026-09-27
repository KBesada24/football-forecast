from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from test_ingestion_persistence import transaction  # noqa: F401

from src.core.database import get_db_session
from src.db.models import LineupSnapshot
from src.main import create_app

pytestmark = pytest.mark.usefixtures("migrate_test_database")


@pytest.fixture
def api(transaction):  # noqa: F811
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: transaction
    with TestClient(app) as client:
        yield client


def add_snapshot(session, kickoff=None):
    sid = uuid4().hex
    now = datetime.now(UTC)
    payload = {
        "snapshot_id": sid,
        "season": 2098,
        "week": 2,
        "first_kickoff": (kickoff or now + timedelta(days=2)).isoformat(),
        "data_as_of": now.isoformat(),
        "scoring_version": "test",
        "notice": "Test",
        "players": [{"id": "QB", "position": "QB", "projection": 21, "unavailable_reason": None}],
    }
    session.add(
        LineupSnapshot(snapshot_id=sid, season=2098, week=2, generated_at=now, payload=payload)
    )
    session.flush()
    return sid


def test_saved_projection_read_path_and_validation(transaction, api, monkeypatch):  # noqa: F811
    sid = add_snapshot(transaction)

    def forbidden(*args, **kwargs):
        raise AssertionError("Request path must not run model or source downloads")

    monkeypatch.setattr("src.models.lineup_model.predict", forbidden)
    monkeypatch.setattr("src.data.lineup_data.load_inputs", forbidden)
    response = api.get("/api/v1/lineups/week?season=2098&week=2")
    assert response.json()["status"] == "ready"
    body = {"season": 2098, "week": 2, "roster": ["QB"], "slots": ["QB"], "snapshot_id": sid}
    response = api.post("/api/v1/lineups/optimize", json=body)
    assert response.status_code == 200
    assert response.json()["total"] == 21
    assert (
        api.post("/api/v1/lineups/optimize", json={**body, "roster": ["not-found"]}).status_code
        == 422
    )
    assert (
        api.post("/api/v1/lineups/optimize", json={**body, "roster": ["QB", "QB"]}).status_code
        == 422
    )
    assert (
        api.post("/api/v1/lineups/optimize", json={**body, "snapshot_id": "f" * 32}).status_code
        == 409
    )
    assert api.get("/api/v1/lineups/week?season=2098&week=1").json()["status"] == "unavailable"


def test_started_week_is_readable_but_cannot_recompute(transaction, api):  # noqa: F811
    add_snapshot(transaction, datetime.now(UTC) - timedelta(minutes=1))
    assert api.get("/api/v1/lineups/week?season=2098&week=2").json()["status"] == "locked"
    assert (
        api.post(
            "/api/v1/lineups/optimize", json={"season": 2098, "week": 2, "roster": ["QB"]}
        ).status_code
        == 409
    )


def test_lineup_snapshots_are_immutable(transaction):  # noqa: F811
    sid = add_snapshot(transaction)
    with pytest.raises(DBAPIError, match="append-only"), transaction.begin_nested():
        transaction.execute(
            update(LineupSnapshot).where(LineupSnapshot.snapshot_id == sid).values(week=3)
        )
