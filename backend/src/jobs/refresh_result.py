"""Public-safe workflow status. A published result does not imply its archive survived."""

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("published", "summary"))
    args = parser.parse_args()
    path = Path("data/refresh-result.json")
    result = json.loads(path.read_text()) if path.is_file() else {"status": "failed"}
    if args.mode == "published":
        # No-op is not an archival error; allow the workflow to continue to its backup.
        raise SystemExit(0 if result["status"] == "published" else 1)
    publication = result["status"]
    replay = (
        os.environ.get("REPLAY_OUTCOME", "missing")
        if publication == "published"
        else "not applicable"
    )
    backup = os.environ.get("BACKUP_OUTCOME", "missing")
    verified = os.environ.get("VERIFY_OUTCOME", "missing")
    lines = [
        "## Football refresh",
        f"- Publication: {publication}",
        f"- Canonical ingestion: {'completed' if 'ingestion' in result else 'not confirmed'}",
        f"- Replay encryption: {replay}",
        f"- Backup encryption: {backup}",
        f"- Uploaded archive download/checksum verification: {verified}",
    ]
    if publication == "published":
        lineups = result.get("lineups") or {}
        lines.append(f"- Snapshot: {lineups.get('snapshot_id', 'unknown')}")
        season = result.get("season", "unknown")
        lines.append(f"- NFL season/week: {season}/{lineups.get('week', 'unknown')}")
    success = (
        publication in ("published", "no_op")
        and os.environ.get("REFRESH_OUTCOME") == "success"
        and (publication != "published" or replay == "success")
        and backup == "success"
        and verified == "success"
    )
    if not success:
        lines.append(
            "- ACTION REQUIRED: do not rerun publication just to replace a lost archive. "
            "A fresh runner cannot recover exact files that never uploaded."
        )
    summary = "\n".join(lines) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(summary)
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
