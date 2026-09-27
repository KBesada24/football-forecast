"""Tuesday data refresh + saved next-week estimates, never model retraining."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from src.core.config import get_settings
from src.data.ingestion import sha256, write_json
from src.jobs.ingest_seasons import run as ingest
from src.jobs.prepare_lineups import run as prepare_lineups
from src.jobs.publication_checks import NoPublicationWindow


def verify_model() -> None:
    path = get_settings().model_dir / "lineup-model-v1.json"
    checksum = path.with_suffix(".json.sha256")
    if not path.is_file() or not checksum.is_file():
        raise ValueError("Approved model and .json.sha256 sidecar are required; never auto-train")
    expected = checksum.read_text().strip().split()[0]
    if sha256(path) != expected:
        raise ValueError("Approved model checksum mismatch")


def run(season: int, result_path: Path) -> dict:
    if not 2024 <= season <= datetime.now(UTC).year:
        raise ValueError("Season must be between 2024 and the current calendar year")
    result = {"season": season, "status": "running", "stage": "preflight"}
    write_json(result_path, result)
    try:
        verify_model()
        result["stage"] = "ingestion"
        write_json(result_path, result)
        imported = ingest(list(range(2024, season + 1)), None, False)
        result.update(ingestion=imported, stage="lineup_preparation")
        write_json(result_path, result)
        prepared = prepare_lineups(Path(imported["snapshot"]), season, None, False)
        result.update(lineups=prepared, status="published", stage="published")
    except NoPublicationWindow:
        result.update(status="no_op", reason="Outside regular-season publication window")
    except Exception as error:
        # Do not expose SQLAlchemy/libpq errors or reviewed evidence in public CI logs.
        result.update(status="failed", error_type=type(error).__name__)
        write_json(result_path, result)
        raise
    write_json(result_path, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--result-path", type=Path, default=Path("data/refresh-result.json"))
    args = parser.parse_args()
    try:
        result = run(args.season, args.result_path)
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps({k: result[k] for k in ("season", "status", "stage")}, indent=2))


if __name__ == "__main__":
    main()
