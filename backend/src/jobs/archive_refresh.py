"""Encrypt exact replay inputs and portable backups. Only *.age files leave the runner."""

import argparse
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

from src.core.config import BACKEND_DIR, get_settings
from src.data.ingestion import sha256, write_json


def command(args: list[str], *, env: dict | None = None) -> None:
    completed = subprocess.run(args, env=env, capture_output=True, timeout=1800, check=False)
    if completed.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed; private tool output withheld")


def encrypt(source: Path, destination: Path, recipient: str) -> None:
    if not re.fullmatch(r"age1[0-9a-z]{58}", recipient):
        raise ValueError("BACKUP_AGE_RECIPIENT must be a native age public recipient")
    partial = destination.with_suffix(destination.suffix + ".partial")
    command(["age", "--encrypt", "-r", recipient, "-o", str(partial), str(source)])
    if not partial.is_file() or partial.stat().st_size == 0:
        raise ValueError("Encryption produced no archive")
    partial.replace(destination)


def contained(path: str, root: Path) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Archive input is missing or outside DATA_DIR")
    return resolved


def replay_bundle(result: dict, destination: Path, recipient: str) -> None:
    settings = get_settings()
    if result.get("status") != "published":
        raise ValueError("Only an actually published snapshot has a replay bundle")
    lineup = result["lineups"]
    raw = Path(result["ingestion"]["snapshot"])
    artifact = Path(lineup["artifact_dir"])
    files = {}
    for name in (
        "manifest.json",
        "player_stats.parquet",
        "schedules.parquet",
        "rosters.parquet",
        "snap_counts.parquet",
        "players.parquet",
        "lineup-manifest.json",
        "lineup-team_stats.parquet",
        "lineup-pbp.parquet",
    ):
        files[f"raw/{name}"] = contained(str(raw / name), settings.data_dir)
    for name in (
        "inputs.json",
        "completion-evidence.json",
        "model.json",
        "snapshot.json",
        "coverage-report.json",
    ):
        files[f"lineup/{name}"] = contained(str(artifact / name), settings.data_dir)
    report = contained(result["ingestion"]["report"], settings.data_dir)
    files["processed/quality-report.json"] = report
    files["processed/mapping.json"] = contained(
        str(report.parent / "mapping.json"), settings.data_dir
    )
    files["config/source_schema_mapping.yaml"] = BACKEND_DIR / "configs/source_schema_mapping.yaml"
    files["config/pyproject.toml"] = BACKEND_DIR / "pyproject.toml"
    manifest = {
        "snapshot_id": lineup["snapshot_id"],
        "season": lineup["season"],
        "week": lineup["week"],
        "source_commit": os.environ.get("GITHUB_SHA", "local-unrecorded"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "model_sha256": sha256(files["lineup/model.json"]),
        "files": {name: sha256(path) for name, path in files.items()},
    }
    with tempfile.TemporaryDirectory(prefix="football-replay-") as temp:
        folder = Path(temp)
        write_json(folder / "archive-manifest.json", manifest)
        with tarfile.open(folder / "replay.tar.gz", "w:gz") as archive:
            for name, path in files.items():
                archive.add(path, arcname=name, recursive=False)
            archive.add(folder / "archive-manifest.json", arcname="archive-manifest.json")
        encrypt(folder / "replay.tar.gz", destination, recipient)


def database_backup(destination: Path, recipient: str) -> None:
    url = make_url(get_settings().database_url)
    # libpq does not expand a URI placed in PGDATABASE, so pass each part separately.
    # The password is never a command-line argument.
    parts = {
        "PGHOST": url.host,
        "PGPORT": str(url.port) if url.port else None,
        "PGUSER": url.username,
        "PGPASSWORD": url.password,
        "PGDATABASE": url.database,
        "PGSSLMODE": url.query.get("sslmode"),
        "PGSSLROOTCERT": url.query.get("sslrootcert"),
    }
    env = {**os.environ, "PGCONNECT_TIMEOUT": "15"}
    env.update({name: str(value) for name, value in parts.items() if value})
    with tempfile.TemporaryDirectory(prefix="football-backup-") as temp:
        dump = Path(temp) / "database.dump"
        # Application tables live in public; Supabase-managed schemas are not ours to restore.
        command(
            [
                "pg_dump",
                "-Fc",
                "--no-owner",
                "--no-privileges",
                "--schema=public",
                "-f",
                str(dump),
            ],
            env=env,
        )
        if not dump.is_file() or dump.stat().st_size == 0:
            raise ValueError("Database backup is empty")
        command(["pg_restore", "--list", str(dump)])
        encrypt(dump, destination, recipient)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("replay", "backup", "verify"))
    parser.add_argument("--result-path", type=Path, default=Path("data/refresh-result.json"))
    parser.add_argument("--output", type=Path, default=Path("data/encrypted"))
    args = parser.parse_args()
    try:
        if args.kind == "verify":
            manifests = list(args.output.glob("*.sha256.json"))
            if not manifests:
                raise ValueError("No encrypted archive checksums downloaded")
            covered = set()
            for manifest in manifests:
                info = json.loads(manifest.read_text())
                name = info["filename"]
                if Path(name).name != name or not name.endswith(".age"):
                    raise ValueError("Invalid archive filename")
                if sha256(args.output / name) != info["sha256"]:
                    raise ValueError("Downloaded encrypted archive checksum mismatch")
                covered.add(name)
            if {path.name for path in args.output.glob("*.age")} != covered:
                raise ValueError("Downloaded archives and checksum manifests differ")
        else:
            recipient = os.environ.get("BACKUP_AGE_RECIPIENT", "")
            args.output.mkdir(parents=True, exist_ok=True)
            destination = args.output / f"{args.kind}.age"
            if args.kind == "replay":
                result = json.loads(args.result_path.read_text())
                if result.get("status") == "no_op":
                    print(json.dumps({"status": "not_applicable", "stage": "replay"}))
                    return
                replay_bundle(result, destination, recipient)
            else:
                database_backup(destination, recipient)
            write_json(
                destination.with_suffix(".sha256.json"),
                {
                    "filename": destination.name,
                    "sha256": sha256(destination),
                },
            )
    except Exception as error:
        print(
            json.dumps({"status": "failed", "stage": args.kind, "error_type": type(error).__name__})
        )
        raise SystemExit(1) from None
    print(json.dumps({"status": "succeeded", "stage": args.kind}))


if __name__ == "__main__":
    main()
