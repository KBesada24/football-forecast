import json

import pytest
from test_source_adapter import build_source_frames

from src.data.ingestion import DATASETS, read_snapshot, sha256, write_json


def snapshot(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    manifest = {
        "artifact_id": "a" * 32,
        "seasons": [2025],
        "nflreadpy_version": "0.1.5",
        "datasets": {},
    }
    for name, frame in build_source_frames().items():
        path = root / f"{name}.parquet"
        frame.write_parquet(path)
        manifest["datasets"][name] = {
            "filename": path.name,
            "sha256": sha256(path),
            "row_count": frame.height,
        }
    write_json(root / "manifest.json", manifest)
    return root


def test_snapshot_replay_and_tamper_detection(tmp_path):
    root = snapshot(tmp_path)
    frames, _ = read_snapshot(root)
    assert set(frames) == set(DATASETS)
    (root / "players.parquet").write_bytes(b"broken")
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_snapshot(root)


def test_snapshot_rejects_unsafe_artifact_path(tmp_path):
    root = snapshot(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["artifact_id"] = "../../outside"
    write_json(root / "manifest.json", manifest)
    with pytest.raises(ValueError, match="artifact ID"):
        read_snapshot(root)
