from copy import deepcopy
from datetime import timedelta

import polars as pl
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_source_adapter import AS_OF, build_source_frames, normalize

from src.core.database import engine
from src.data.persistence import persist_dataset
from src.data.schema_validation import SourceSchemaError
from src.db.models import Player, PlayerGameStat
from src.domain.completion import CompletionEvidence
from src.jobs.import_completion_evidence import import_evidence

pytestmark = pytest.mark.usefixtures("migrate_test_database")


@pytest.fixture
def source_frames():
    frames = build_source_frames()
    away = frames["player_stats"].with_columns(
        pl.lit("00-AWAY").alias("player_id"),
        pl.lit("Away Player").alias("player_display_name"),
        pl.lit("BAL").alias("team"),
        pl.lit("BUF").alias("opponent_team"),
    )
    frames["player_stats"] = pl.concat([frames["player_stats"], away])
    return frames


@pytest.fixture
def transaction():
    with engine.connect() as connection:
        outer = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        outer.rollback()


def test_repeat_import_and_correction_are_upserts(transaction, source_frames):
    data = normalize(source_frames)
    persist_dataset(transaction, data, AS_OF)
    persist_dataset(transaction, data, AS_OF)
    assert transaction.scalar(select(func.count()).select_from(PlayerGameStat)) == 2
    corrected = deepcopy(data)
    corrected.stats[0]["receiving_yards"] += 10
    corrected.stats[0]["fantasy_points_ppr"] += 1
    persist_dataset(transaction, corrected, AS_OF)
    row = transaction.scalar(select(PlayerGameStat).where(PlayerGameStat.player_id == "00-TEST"))
    assert row.receiving_yards == 85


def test_older_import_cannot_regress_player_team(transaction, source_frames):
    data = normalize(source_frames)
    persist_dataset(transaction, data, AS_OF)
    older = deepcopy(data)
    older.players[0].update(context_season=2024, current_team="BAL")
    persist_dataset(transaction, older, AS_OF)
    assert transaction.get(Player, "00-TEST").current_team == "BUF"


def test_source_removal_blocks_publication(transaction, source_frames):
    data = normalize(source_frames)
    persist_dataset(transaction, data, AS_OF)
    removed = deepcopy(data)
    removed.stats = []
    with pytest.raises(SourceSchemaError, match="reconciliation"):
        persist_dataset(transaction, removed, AS_OF + timedelta(hours=1))
    assert transaction.scalar(select(func.count()).select_from(PlayerGameStat)) == 2


def test_failure_rolls_back_partial_update(transaction, source_frames):
    data = normalize(source_frames)
    persist_dataset(transaction, data, AS_OF)
    broken = deepcopy(data)
    broken.players[0]["player_name"] = "Should roll back"
    broken.stats[0]["fantasy_points_ppr"] = None
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), transaction.begin_nested():
        persist_dataset(transaction, broken, AS_OF)
    transaction.expire_all()
    assert transaction.get(Player, "00-TEST").player_name == "Test Player"


def test_unexplained_scoring_blocks_publication(transaction, source_frames):
    data = normalize(source_frames)
    data.report["counts"]["unexplained_ppr_differences"] = 1
    with pytest.raises(SourceSchemaError, match="Unexplained"):
        persist_dataset(transaction, data, AS_OF)
    assert transaction.scalar(select(func.count()).select_from(PlayerGameStat)) == 0


def reviewed_evidence(status="dnf"):
    return CompletionEvidence(
        player_id="00-TEST",
        game_id="2025_01_TEST",
        status=status,
        source_url="https://www.nfl.com/news/test-fixture",
        source_published_at=AS_OF - timedelta(days=1),
        retrieved_at=AS_OF - timedelta(days=1),
        reviewed_at=AS_OF - timedelta(days=1),
        evidence_note="Synthetic test fixture, not a real report.",
        reviewer="test",
    )


def test_evidence_import_idempotent_and_survives_stat_refresh(transaction, source_frames):
    from src.db.models import PlayerGameCompletionEvidence

    data = normalize(source_frames)
    persist_dataset(transaction, data, AS_OF)
    evidence = reviewed_evidence()
    assert import_evidence(transaction, [evidence]) == 1
    assert import_evidence(transaction, [evidence]) == 0
    persist_dataset(transaction, data, AS_OF)
    assert transaction.get(PlayerGameCompletionEvidence, evidence.evidence_id).status == "dnf"


def test_dnp_cannot_override_snap_evidence(transaction, source_frames):
    persist_dataset(transaction, normalize(source_frames), AS_OF)
    with pytest.raises(ValueError, match="contradicts"):
        import_evidence(transaction, [reviewed_evidence("dnp")])
