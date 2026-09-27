"""Download once and preserve checksummed input snapshots for reproducible imports."""

import hashlib
import importlib.metadata
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import nflreadpy as nfl
import polars as pl
from nflreadpy.config import update_config

from src.jobs.audit_nflreadpy_schema import summarize_frame

DATASETS = ("player_stats", "schedules", "rosters", "snap_counts", "players")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    temp.replace(path)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_snapshot(seasons: list[int], data_dir: Path) -> Path:
    if not seasons or any(year < 2009 or year > datetime.now(UTC).year for year in seasons):
        raise ValueError("Expected supported season years between 2009 and the current year")
    seasons = sorted(set(seasons))
    artifact_id = uuid4().hex
    root = data_dir / "raw" / artifact_id
    root.mkdir(parents=True, exist_ok=False)
    # Every import deliberately refreshes upstream data; replay uses a saved snapshot.
    update_config(cache_mode="off", verbose=False)
    loaders = {
        "player_stats": lambda: nfl.load_player_stats(seasons, summary_level="week"),
        "schedules": lambda: nfl.load_schedules(seasons),
        "rosters": lambda: nfl.load_rosters_weekly(seasons),
        "snap_counts": lambda: nfl.load_snap_counts(seasons),
        "players": nfl.load_players,
    }
    manifest: dict[str, Any] = {
        "artifact_id": artifact_id,
        "seasons": seasons,
        "nflreadpy_version": importlib.metadata.version("nflreadpy"),
        "started_at": datetime.now(UTC).isoformat(),
        "datasets": {},
    }
    for name, loader in loaders.items():
        frame = loader()
        if not isinstance(frame, pl.DataFrame) or frame.is_empty():
            raise ValueError(f"Source dataset is empty or invalid: {name}")
        path = root / f"{name}.parquet"
        frame.write_parquet(path)
        manifest["datasets"][name] = {
            "filename": path.name,
            "sha256": sha256(path),
            "retrieved_at": datetime.now(UTC).isoformat(),
            **summarize_frame(frame),
        }
    manifest["retrieved_at"] = datetime.now(UTC).isoformat()
    write_json(root / "manifest.json", manifest)
    return root


def read_snapshot(root: Path) -> tuple[dict[str, pl.DataFrame], dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"[a-f0-9]{32}", manifest.get("artifact_id", "")):
        raise ValueError("Invalid snapshot artifact ID")
    if set(manifest["datasets"]) != set(DATASETS):
        raise ValueError("Snapshot does not contain all required datasets")
    if manifest["nflreadpy_version"] != importlib.metadata.version("nflreadpy"):
        raise ValueError("Snapshot package version differs from installed nflreadpy")
    frames = {}
    for name in DATASETS:
        info = manifest["datasets"][name]
        if info["filename"] != f"{name}.parquet":
            raise ValueError("Unexpected snapshot filename")
        path = root / info["filename"]
        if sha256(path) != info["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
        frames[name] = pl.read_parquet(path)
        if frames[name].is_empty() or frames[name].height != info["row_count"]:
            raise ValueError(f"Empty or inconsistent snapshot dataset: {name}")
        if name != "players" and set(frames[name].get_column("season").unique()) != set(
            manifest["seasons"]
        ):
            raise ValueError(f"Snapshot season coverage does not match manifest: {name}")
    return frames, manifest
