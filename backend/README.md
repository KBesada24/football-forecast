# Football Forecast backend

FastAPI, PostgreSQL, nflreadpy, and Polars backend for full-PPR player forecasts.

## Best matchups: actuals and preliminary estimates

The rankings endpoint now serves actual full-PPR leaderboards for started/past weeks
(completed imported games only). Actual DNF scores remain visible and ties share ranks.
For fully upcoming weeks it prefers an immutable published forecast, then a prepared
preliminary ranking stored separately in `ranking_previews`.

After applying migrations, prepare an upcoming week without downloading or publishing:

```bash
python -m src.jobs.prepare_rankings --season 2026 --week 3
```

Each successful canonical ingestion also prepares the next fully upcoming week in the
same transaction. No inference/downloads happen on API requests. The Tuesday scheduler
is still not deployed; this hook runs when the ingestion job is invoked.

Preliminary rankings use latest known same-season active rosters, the trailing-four
eligible-appearance baseline, and a 50/50 within-position percentile blend with opponent
PPR per recorded positional appearance over up to four completed prior games. Reported
DNF/DNP games do not enter player averages. Player stat gaps still exclude a candidate.
Opponent coverage may be partial and is explicitly labeled; missing scores are never
imputed as zero. This relaxed opponent context is only for preliminary estimates, not
the strict published-forecast path. Estimates are never backdated after kickoff.

## Setup

Start PostgreSQL from the repository root:

```bash
podman compose up -d postgres
```

Docker users can run `docker compose up -d postgres` instead.

Create the local environment and install the pinned application and development
dependencies:

```bash
cd backend
cp .env.example .env
python -m venv venv
source venv/bin/activate
python -m pip install -e '.[dev,worker,local]'
```

Apply the database schema:

```bash
alembic upgrade head
```

## Verify nflreadpy source data

The schema audit downloads and inspects 2024, 2025, and the available 2026 season. Generated data and
metadata remain under the ignored `backend/data/` directory.

```bash
python -m src.jobs.audit_nflreadpy_schema
```

The verified mapping is checked in at `configs/source_schema_mapping.yaml`; the
human-readable audit report is `../docs/source-schema-audit.md`.

## Import real data

Run from `backend/` after migrating. Downloads use the pinned nflreadpy package;
an import refreshes its source data rather than reusing a potentially stale cache.

```bash
python -m src.jobs.ingest_seasons --seasons 2024 2025 2026 --validate-only
python -m src.jobs.ingest_seasons --seasons 2024 2025 2026
```

Validation-only does not connect to Postgres. Both modes preserve raw Parquet and
a checksummed schema/provenance manifest under `data/raw/<artifact-id>/`. Canonical
Parquet, the exact mapping configuration, and the scoring/coverage report are saved
under `data/processed/<artifact-id>/<validation-id>/`. The command prints paths.

To reproduce an import without downloading again, use the returned snapshot path:

```bash
python -m src.jobs.ingest_seasons --seasons 2024 2025 2026 --snapshot data/raw/ARTIFACT_ID
```

Imports upsert canonical records in one transaction. Concurrent publication is
serialized. Unexplained scoring differences, missing completed-game team coverage,
and conflicting identities prevent publication. A failed run is recorded and the
last successful data remains intact. Potential source removals block publication
for review; no automatic deletion/reconciliation is implemented yet. Snap counts
without a stat line are preserved separately, never filled with guessed zero PPR.

## Postgame completion evidence and averages

`src/features/player_history.py` builds prior-week-only features and
`src/models/baseline.py` implements the trailing-four eligible-game mean. Confirmed
DNF games are excluded from averages; actual previous-game outcomes remain intact.
Missing stat coverage or unmatched schedules produce an unavailable result.
As requested September 21, completion reports are no longer required: recorded
appearances count unless DNF/DNP is reported. Unreported early exits may remain;
unknown statuses are not rewritten as confirmed finished. Feature/baseline v2
versions distinguish this policy from the original strict v1 policy.
The weekly batch job below persists these features and the
baseline estimates without training a model.

Reviewed evidence can be imported from a JSON array:

```bash
python -m src.jobs.import_completion_evidence path/to/reviewed-evidence.json
```

Each record follows `src/domain/completion.py:CompletionEvidence`: `player_id`,
`game_id`, `status` (`finished`, `dnf`, or `dnp`), `source_url`,
`source_published_at`, optional `source_updated_at`, `retrieved_at`, `reviewed_at`,
`evidence_note`, and `reviewer`. All timestamps must include a timezone. Records
are append-only and identical reimports are ignored. They survive stat refreshes.

This job accepts reviewed assertions; it does not fetch articles or validate their
meaning automatically. Review official postgame reports and follow-ups, including
whether a player returned. Do not mark a player finished merely because no injury
news was found, or mark DNF from a pregame Out designation. No real completion
evidence has been populated yet. Historical reports reviewed today are not
silently treated as evidence available at a past forecast cutoff.

The Tuesday 08:00 America/New_York refresh is still a planned deployment job.
It will run new inputs through the approved model without weekly retraining.

## Generate a weekly publication

After importing complete results, upcoming weekly rosters, and reviewed evidence:

```bash
python -m src.jobs.generate_forecasts --season 2026 --week 3
```

This command uses the existing trailing-four baseline, **not a trained ML model**.
It never downloads data or retrains. It requires the target week to be wholly
upcoming, prior scheduled games to be completed, and both-team stat coverage plus
target-team roster coverage. Individual players with missing statistical coverage,
inactive/unknown roster status, or no eligible
history receive explicit unavailable results. At least one available forecast is
required for publication; all-unavailable attempts are blocked.

The command prints its batch ID, status, gate failures, coverage counts, and
unavailable reasons. Exit code 2 means a blocked publication, not success. A blocked
attempt and its frozen inputs remain available in `forecast_batches` for diagnosis.
No publication pointer is created. Exceptions roll back the entire transaction.

Each batch stores exact source inputs, eligible-history features, reviewed evidence,
versions, timestamps, and a SHA-256 input fingerprint. One immutable publication is
allowed per NFL week; rerunning a published week returns the original batch. Database
triggers reject updates/deletes of snapshot and publication records. Corrected
canonical history can change while published forecast values remain unchanged.
The API never substitutes a different week's publication.

Optional `--cutoff 2026-09-22T08:30:00-04:00` records an explicit cutoff **only when
that time is already in the past**. Sources retrieved after the cutoff block the
job: today's mutable database is not an as-of historical backtesting store.

Rankings combine equal-weight, within-position percentiles of projected PPR and
opponent PPR allowed per appearance over its last four completed games. Actual
opponent outcomes include early exits. Missing appearance/stat coverage leaves
the ranking unavailable, even when the player's individual forecast is valid.
Ties receive the same rank; ranks compare only RB with RB, WR with WR, and TE with TE.
This descriptive opponent signal is not a proven causal adjustment.

The new `forecast_batches`, `forecast_batch_players`, and `forecast_publications`
tables serve this baseline workflow. Earlier `player_week_features`,
`player_week_predictions`, `model_versions`, and `forecast_generation_runs` scaffold
tables are not populated by it; the trained-model workflow is still pending.

## Run checks

Database integration tests migrate the separate `football_forecast_test` database.
Unit tests do not need a running Postgres instance. Test configuration rejects a
database that matches the application database or lacks the `_test` suffix.

```bash
ruff check .
ruff format --check .
pytest
```

## Run the API

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Useful local endpoints:

- API documentation: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/api/v1/health>
- Database readiness: <http://127.0.0.1:8000/api/v1/health/ready>
- Player search: `/api/v1/players/search?q=Justin%20Jefferson`
- Metadata: `/api/v1/meta/current-context`
- Projection: `/api/v1/players/{playerId}/projection?season=2026&week=3`
- Actual history: `/api/v1/players/{playerId}/history?season=2026&week=3&limit=8`
- Opponent history: `/api/v1/players/{playerId}/vs-opponent?season=2026&week=3`
- Combined dashboard: `/api/v1/players/{playerId}/dashboard?season=2026&week=3`
- Best matchups: `/api/v1/rankings?season=2026&week=3&position=WR`

Requests use read-only, repeatable-read transactions and never run ingestion or
forecast generation. Responses use the MRD's camelCase player contracts and
snake_case metadata, with additional completion, ranking, cutoff, and provenance
fields. History shows actual DNF scores; averages exclude reported DNFs, without
requiring a finished report for every appearance. Missing scoring coverage still
blocks affected averages. History/dashboard accept `include_selected_week=true`
to show completed results through the chosen week. The default remains prior-week
only; this display option does not alter projection inputs or publication cutoffs.
Database errors return a redacted
503; invalid query values return 422 and unknown players return 404.
