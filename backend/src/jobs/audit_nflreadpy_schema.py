import argparse
import importlib.metadata
import inspect
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import nflreadpy as nfl
import polars as pl
from nflreadpy.config import update_config

from src.core.config import get_settings

DEFAULT_SEASONS = (2024, 2025, 2026)
SAMPLE_SIZE = 5


def summarize_frame(frame: pl.DataFrame) -> dict[str, Any]:
    return {
        "row_count": frame.height,
        "column_count": frame.width,
        "schema": {name: str(dtype) for name, dtype in frame.schema.items()},
        "null_counts": frame.null_count().row(0, named=True),
        "sample_records": frame.head(SAMPLE_SIZE).to_dicts(),
    }


def loader_signature(loader: Callable[..., pl.DataFrame]) -> str:
    return str(inspect.signature(loader))


def build_audit(seasons: Sequence[int]) -> dict[str, Any]:
    settings = get_settings()
    cache_dir = settings.data_dir / "raw" / "nflreadpy-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    update_config(cache_mode="filesystem", cache_dir=cache_dir, verbose=True)

    player_stats = nfl.load_player_stats(list(seasons), summary_level="week")
    schedules = nfl.load_schedules(list(seasons))

    if not isinstance(player_stats, pl.DataFrame) or not isinstance(schedules, pl.DataFrame):
        raise TypeError("nflreadpy loaders must return Polars DataFrames")

    return {
        "audited_at": datetime.now(UTC).isoformat(),
        "seasons": list(seasons),
        "nflreadpy_version": importlib.metadata.version("nflreadpy"),
        "loader_signatures": {
            "load_player_stats": loader_signature(nfl.load_player_stats),
            "load_schedules": loader_signature(nfl.load_schedules),
        },
        "datasets": {
            "player_stats": summarize_frame(player_stats),
            "schedules": summarize_frame(schedules),
        },
    }


def write_audit(audit: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit nflreadpy runtime schemas")
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=list(DEFAULT_SEASONS),
        help="Completed NFL seasons to inspect",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (defaults to backend/data/metadata)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    output_path = args.output or settings.data_dir / "metadata" / "nflreadpy-schema-audit.json"
    audit = build_audit(args.seasons)
    write_audit(audit, output_path)
    print(f"Wrote schema audit to {output_path}")


if __name__ == "__main__":
    main()
