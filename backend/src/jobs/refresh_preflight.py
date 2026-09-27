"""Fail before publication if the worker cannot encrypt or make a PostgreSQL backup."""

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from src.jobs.archive_refresh import encrypt
from src.jobs.weekly_refresh import verify_model

# pg_dump and session state need Supabase's session pooler (5432) or a direct connection.
TRANSACTION_POOLER_PORT = 6543


def check_database_connection() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise ValueError("Worker DATABASE_URL is required")
    url = make_url(os.environ["DATABASE_URL"])
    if url.port == TRANSACTION_POOLER_PORT:
        raise ValueError("Worker needs a session connection, not the transaction pooler")
    if url.query.get("sslmode") != "verify-full":
        raise ValueError("Worker DATABASE_URL must use sslmode=verify-full")
    if not Path(os.environ.get("PGSSLROOTCERT", "")).is_file():
        raise ValueError("PGSSLROOTCERT must point to the database CA certificate")


def main() -> None:
    try:
        check_database_connection()
        season = int(os.environ["NFL_SEASON"])
        if not 2024 <= season <= datetime.now(UTC).year:
            raise ValueError("Unsupported season")
        verify_model()
        for program in ("pg_dump", "pg_restore"):
            version = subprocess.run(
                [program, "--version"], capture_output=True, text=True, check=True, timeout=10
            ).stdout
            if "(PostgreSQL) 17." not in version:
                raise ValueError("PostgreSQL 17 backup clients required")
        with tempfile.TemporaryDirectory(prefix="football-preflight-") as temp:
            source = Path(temp) / "probe"
            source.write_text("encryption preflight, no private data")
            encrypt(source, Path(temp) / "probe.age", os.environ.get("BACKUP_AGE_RECIPIENT", ""))
    except Exception as error:
        print(json.dumps({"status": "preflight_failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
