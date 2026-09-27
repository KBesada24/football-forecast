import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.data.ingestion import sha256, write_json
from src.jobs import archive_refresh, refresh_result


def test_encryption_rejects_private_key_and_bad_recipient(tmp_path):
    with pytest.raises(ValueError, match="public recipient"):
        archive_refresh.encrypt(tmp_path / "source", tmp_path / "out.age", "AGE-SECRET-KEY-1fake")


def test_partial_encryption_never_gets_upload_extension(tmp_path, monkeypatch):
    def failed(args, **_kwargs):
        Path(args[args.index("-o") + 1]).write_bytes(b"partial")
        raise RuntimeError("failed")

    monkeypatch.setattr(archive_refresh, "command", failed)
    with pytest.raises(RuntimeError):
        archive_refresh.encrypt(tmp_path / "source", tmp_path / "out.age", "age1" + "a" * 58)
    assert not list(tmp_path.glob("*.age"))


def test_backup_uses_libpq_env_and_verifies_readability(tmp_path, monkeypatch):
    monkeypatch.setattr(
        archive_refresh,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+psycopg://worker:secret@localhost/example?sslmode=require"
        ),
    )
    calls = []

    def command(args, *, env=None):
        assert "secret" not in " ".join(args)
        calls.append((args, env))
        if args[0] == "pg_dump":
            Path(args[-1]).write_bytes(b"test dump")

    monkeypatch.setattr(archive_refresh, "command", command)
    monkeypatch.setattr(
        archive_refresh, "encrypt", lambda source, dest, _: shutil.copyfile(source, dest)
    )
    archive_refresh.database_backup(tmp_path / "backup.age", "unused")
    assert (
        calls[0][1]["PGDATABASE"] == "postgresql://worker:secret@localhost/example?sslmode=require"
    )
    assert "--schema=public" in calls[0][0]
    assert calls[1][0][:2] == ["pg_restore", "--list"]


def test_command_redacts_tool_stderr(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr=b"database password"),
    )
    with pytest.raises(RuntimeError, match="output withheld") as error:
        archive_refresh.command(["pg_dump"])
    assert "password" not in str(error.value)


def test_archive_paths_cannot_escape_data_dir(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "private"
    outside.write_text("not an archive input")
    (allowed / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        archive_refresh.contained(str(allowed / "link"), allowed)


def test_replay_manifest_matches_exact_inputs(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    artifact = tmp_path / "lineup"
    processed = tmp_path / "processed"
    for folder in (raw, artifact, processed):
        folder.mkdir()
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
        (raw / name).write_bytes(b"exact raw fixture bytes")
    for name in (
        "inputs.json",
        "completion-evidence.json",
        "model.json",
        "snapshot.json",
        "coverage-report.json",
    ):
        (artifact / name).write_text('{"reviewer":"private reviewer"}')
    for name in ("quality-report.json", "mapping.json"):
        (processed / name).write_text("{}")
    monkeypatch.setattr(archive_refresh, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    # Inspect plaintext only in the test's isolated temp dir, never as a workflow artifact.
    monkeypatch.setattr(
        archive_refresh, "encrypt", lambda source, dest, _: shutil.copyfile(source, dest)
    )
    result = {
        "status": "published",
        "ingestion": {"snapshot": str(raw), "report": str(processed / "quality-report.json")},
        "lineups": {
            "artifact_dir": str(artifact),
            "snapshot_id": "a" * 32,
            "season": 2026,
            "week": 3,
        },
    }
    dest = tmp_path / "replay.tar.gz"
    archive_refresh.replay_bundle(result, dest, "unused")
    import hashlib

    with tarfile.open(dest) as bundle:
        manifest = json.load(bundle.extractfile("archive-manifest.json"))
        for name, expected in manifest["files"].items():
            assert hashlib.sha256(bundle.extractfile(name).read()).hexdigest() == expected
        assert (
            "private reviewer"
            in bundle.extractfile("lineup/completion-evidence.json").read().decode()
        )
        assert manifest["snapshot_id"] == "a" * 32


@pytest.mark.parametrize(
    "replay,backup,verified,expected",
    [
        ("success", "success", "success", 0),
        ("failure", "success", "success", 1),
        ("success", "failure", "success", 1),
        ("success", "success", "failure", 1),
    ],
)
def test_published_is_not_archived(tmp_path, monkeypatch, replay, backup, verified, expected):
    monkeypatch.chdir(tmp_path)
    write_json(
        tmp_path / "data/refresh-result.json",
        {
            "status": "published",
            "season": 2026,
            "ingestion": {},
            "lineups": {"snapshot_id": "a" * 32, "week": 3},
        },
    )
    monkeypatch.setattr("sys.argv", ["refresh_result", "summary"])
    for name, value in {
        "REFRESH_OUTCOME": "success",
        "REPLAY_OUTCOME": replay,
        "BACKUP_OUTCOME": backup,
        "VERIFY_OUTCOME": verified,
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit) as error:
        refresh_result.main()
    assert error.value.code == expected


def test_summary_survives_incomplete_published_result(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "data/refresh-result.json", {"status": "published", "lineups": {}})
    monkeypatch.setattr("sys.argv", ["refresh_result", "summary"])
    with pytest.raises(SystemExit) as error:
        refresh_result.main()
    output = capsys.readouterr().out
    assert error.value.code == 1
    assert "- Snapshot: unknown" in output
    assert "- NFL season/week: unknown/unknown" in output
    assert "ACTION REQUIRED" in output


def test_downloaded_checksum_rejects_corruption(tmp_path, monkeypatch):
    source = tmp_path / "backup.age"
    source.write_bytes(b"encrypted fixture")
    write_json(tmp_path / "backup.sha256.json", {"filename": source.name, "sha256": sha256(source)})
    monkeypatch.setattr("sys.argv", ["archive_refresh", "verify", "--output", str(tmp_path)])
    archive_refresh.main()
    source.write_bytes(b"corrupted")
    with pytest.raises(SystemExit) as error:
        archive_refresh.main()
    assert error.value.code == 1


def test_downloaded_archive_without_checksum_fails(tmp_path, monkeypatch):
    source = tmp_path / "backup.age"
    source.write_bytes(b"encrypted fixture")
    write_json(tmp_path / "backup.sha256.json", {"filename": source.name, "sha256": sha256(source)})
    (tmp_path / "replay.age").write_bytes(b"uncovered")
    monkeypatch.setattr("sys.argv", ["archive_refresh", "verify", "--output", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        archive_refresh.main()
    assert error.value.code == 1


@pytest.mark.skipif(
    not shutil.which("age") or not shutil.which("age-keygen"),
    reason="Install age and age-keygen for real encryption roundtrip",
)
def test_real_age_encryption_and_owner_only_decryption(tmp_path):
    key = tmp_path / "test-identity.agekey"
    subprocess.run(["age-keygen", "-o", str(key)], capture_output=True, check=True)
    recipient = subprocess.run(
        ["age-keygen", "-y", str(key)], capture_output=True, text=True, check=True
    ).stdout.strip()
    source = tmp_path / "private-backup.dump"
    source.write_bytes(b"private reviewer evidence and backup fixture")
    encrypted = tmp_path / "backup.age"
    archive_refresh.encrypt(source, encrypted, recipient)
    assert b"private reviewer" not in encrypted.read_bytes()
    decoded = subprocess.run(
        ["age", "--decrypt", "-i", str(key), str(encrypted)], capture_output=True, check=True
    ).stdout
    assert decoded == source.read_bytes()


def test_workflow_uploads_only_encrypted_files_and_has_opt_in():
    import yaml

    workflow = Path(__file__).parents[2] / ".github/workflows/weekly-refresh.yml"
    document = yaml.safe_load(workflow.read_text())
    job = document["jobs"]["refresh"]
    assert "ENABLE_WEEKLY_REFRESH" in job["if"]
    assert job["timeout-minutes"] == 60
    assert document["concurrency"]["cancel-in-progress"] is False
    uploads = [s for s in job["steps"] if s.get("uses", "").startswith("actions/upload-artifact@")]
    assert len(uploads) == 2
    for step in uploads:
        assert step["with"]["path"].splitlines() == [
            "backend/data/encrypted/*.age",
            "backend/data/encrypted/*.sha256.json",
        ]
        assert step["with"]["retention-days"] == 90
