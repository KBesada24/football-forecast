"""Import reviewed postgame evidence from a JSON array; never infer it from news keywords."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.db.models import (
    Game,
    PlayerGameCompletionEvidence,
    PlayerGameParticipation,
    PlayerGameStat,
)
from src.domain.completion import CompletionEvidence


def import_evidence(session: Session, evidence: list[CompletionEvidence]) -> int:
    session.execute(text("SELECT pg_advisory_xact_lock(174202409)"))
    now = datetime.now(UTC)
    inserted = 0
    for item in evidence:
        game = session.get(Game, item.game_id)
        if game is None or game.game_status != "completed" or game.game_datetime is None:
            raise ValueError(f"Evidence requires a completed, identified game: {item.game_id}")
        if item.reviewed_at > now or item.retrieved_at < game.game_datetime:
            raise ValueError(
                "Postgame evidence cannot be retrieved before kickoff or reviewed in future"
            )
        source_time = item.source_updated_at or item.source_published_at
        if item.status in ("finished", "dnf") and source_time <= game.game_datetime:
            raise ValueError("Pregame reports cannot establish finished/DNF status")
        if item.status == "dnp":
            participated = session.scalar(
                select(PlayerGameParticipation.id).where(
                    PlayerGameParticipation.game_id == item.game_id,
                    PlayerGameParticipation.player_id == item.player_id,
                )
            )
            stat_record = session.scalar(
                select(PlayerGameStat.id).where(
                    PlayerGameStat.game_id == item.game_id,
                    PlayerGameStat.player_id == item.player_id,
                )
            )
            if participated is not None or stat_record is not None:
                raise ValueError("DNP evidence contradicts recorded participation/statistics")
        record = item.model_dump(mode="python")
        record["source_url"] = str(item.source_url)
        statement = (
            insert(PlayerGameCompletionEvidence)
            .values(evidence_id=item.evidence_id, **record)
            .on_conflict_do_nothing(index_elements=["evidence_id"])
        )
        inserted += len(
            session.scalars(statement.returning(PlayerGameCompletionEvidence.evidence_id)).all()
        )
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    items = TypeAdapter(list[CompletionEvidence]).validate_json(args.path.read_text())
    engine = create_engine(get_settings().database_url)
    try:
        with Session(engine) as session, session.begin():
            count = import_evidence(session, items)
        print(json.dumps({"inserted": count, "submitted": len(items)}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
