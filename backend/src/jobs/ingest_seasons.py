"""Backend operator job: download/replay, validate, and transactionally import NFL data."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import polars as pl
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from src.core.config import BACKEND_DIR, get_settings
from src.data.ingestion import download_snapshot, read_snapshot, sha256, write_json
from src.data.persistence import persist_dataset
from src.data.schema_validation import SourceSchemaError, load_schema_mapping
from src.data.source_adapter import normalize_dataset
from src.db.models import DataIngestionRun
from src.jobs.prepare_rankings import refresh_next_rankings


def run(seasons: list[int], snapshot: Path | None, validate_only: bool) -> dict:
    settings = get_settings()
    engine = None if validate_only else create_engine(settings.database_url, pool_pre_ping=True)
    run_id = None
    artifact_id = None
    if engine is not None:
        with Session(engine) as session, session.begin():
            record = DataIngestionRun(
                source_name="nflreadpy",
                seasons=seasons,
                status="running",
                started_at=datetime.now(UTC),
            )
            session.add(record)
            session.flush()
            run_id = record.id
    try:
        snapshot = snapshot or download_snapshot(seasons, settings.data_dir)
        frames, manifest = read_snapshot(snapshot)
        artifact_id = manifest["artifact_id"]
        if set(manifest["seasons"]) != set(seasons):
            raise ValueError("Requested seasons do not match snapshot seasons")
        as_of = datetime.fromisoformat(manifest["retrieved_at"])
        mapping_path = BACKEND_DIR / "configs" / "source_schema_mapping.yaml"
        mapping = load_schema_mapping(mapping_path)
        dataset = normalize_dataset(frames, mapping, as_of, artifact_id)
        dataset.report["mapping_sha256"] = sha256(mapping_path)
        # Each validation has its own output; replay never replaces prior reports/artifacts.
        result_dir = settings.data_dir / "processed" / artifact_id / uuid4().hex
        result_dir.mkdir(parents=True, exist_ok=False)
        for name in ("games", "players", "stats", "rosters", "participation"):
            rows = getattr(dataset, name)
            if rows:
                pl.DataFrame(rows, infer_schema_length=None).write_parquet(
                    result_dir / f"{name}.parquet"
                )
        write_json(result_dir / "quality-report.json", dataset.report)
        write_json(result_dir / "mapping.json", mapping)
        if dataset.report["counts"]["unexplained_ppr_differences"]:
            raise SourceSchemaError(
                f"Unexplained PPR differences: {result_dir / 'quality-report.json'}"
            )
        if dataset.report["counts"].get("stats_for_uncompleted_game", 0):
            raise SourceSchemaError("Player stats reference uncompleted games; see quality report")
        if dataset.report["counts"].get("completed_game_teams_without_supported_stats", 0):
            raise SourceSchemaError(
                "Completed-game team coverage is incomplete; see quality report"
            )
        if engine is not None:
            with Session(engine) as session, session.begin():
                persist_dataset(session, dataset, as_of)
                refresh_next_rankings(session)
                session.execute(
                    update(DataIngestionRun)
                    .where(DataIngestionRun.id == run_id)
                    .values(
                        status="succeeded",
                        completed_at=datetime.now(UTC),
                        row_counts=dataset.report["counts"],
                        data_artifact_id=artifact_id,
                    )
                )
        return {
            "status": "validated" if validate_only else "imported",
            "snapshot": str(snapshot),
            "report": str(result_dir / "quality-report.json"),
            "counts": dataset.report["counts"],
        }
    except Exception as error:
        if engine is not None:
            with Session(engine) as session, session.begin():
                session.execute(
                    update(DataIngestionRun)
                    .where(DataIngestionRun.id == run_id)
                    .values(
                        status="failed",
                        completed_at=datetime.now(UTC),
                        data_artifact_id=artifact_id,
                        error_message=(
                            str(error)[:1000]
                            if isinstance(error, (ValueError, SourceSchemaError))
                            else type(error).__name__
                        ),
                    )
                )
        raise
    finally:
        if engine is not None:
            engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", type=int, default=[2024, 2025, 2026])
    parser.add_argument(
        "--snapshot", type=Path, help="Replay a checksummed raw snapshot without downloads"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Write artifacts/report without database access",
    )
    args = parser.parse_args()
    print(json.dumps(run(args.seasons, args.snapshot, args.validate_only), indent=2))


if __name__ == "__main__":
    main()
