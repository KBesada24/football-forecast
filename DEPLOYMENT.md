# Football Forecast — zero-budget deployment plan

Last updated: September 27, 2026 (database provider changed from Neon to Supabase). Platform research: September 23–24 and 27, 2026.

Status: **Launch safeguards implemented locally; cloud resources and deployment not yet verified.**

Target: a small, personal, noncommercial beta with **$0 in recurring hosting charges**, within the providers' free allowances. This is not an unlimited-capacity or high-availability production promise.

This document supersedes the earlier paid Railway API/database/worker proposal for the initial release. It does not authorize purchasing services, changing account billing plans, publishing the repository, or deploying the application. Those actions require the user's deployment approval.

**Revision (September 23, 2026): minimal release first.** After a review against the codebase, this plan has two tiers. The **minimal launch path** in [Section 1.1](#11-minimal-launch-path) is the actual work plan for the first public release: only the fixes needed to run on the free stack. Launch safeguards in Sections 11–13 also apply; advanced items explicitly labeled **Deferred** remain future work. Adopt it when real usage, a real incident, or a wider audience justifies it, not before launch. Sections and items marked **Deferred** are not launch requirements.

Read [HANDOFF.md](HANDOFF.md) for application behavior and implementation history. Where that document mentions Railway as a likely host, the current budget-driven decision here takes precedence. Supabase is used only as the PostgreSQL database. Preserve the current UI and football logic unless a deployment-specific change is necessary and tested.

## Contents

1. [Decision and constraints](#1-decision-and-constraints) — including [1.1 Minimal launch path](#11-minimal-launch-path)
2. [Target architecture](#2-target-architecture)
3. [What exists and what is missing](#3-what-exists-and-what-is-missing)
4. [Free-tier budget and capacity](#4-free-tier-budget-and-capacity)
5. [Phase A — repository and account preparation](#5-phase-a--repository-and-account-preparation)
6. [Phase B — serverless compatibility test](#6-phase-b--serverless-compatibility-test)
7. [Phase C — Supabase PostgreSQL](#7-phase-c--supabase-postgresql)
8. [Phase D — Vercel backend](#8-phase-d--vercel-backend)
9. [Phase E — Vercel frontend](#9-phase-e--vercel-frontend)
10. [Configuration and secrets](#10-configuration-and-secrets)
11. [Phase F — Tuesday refresh](#11-phase-f--tuesday-refresh)
12. [Model, artifacts, and backups](#12-model-artifacts-and-backups)
13. [Security and abuse protection](#13-security-and-abuse-protection)
14. [CI, staging, and release order](#14-ci-staging-and-release-order)
15. [End-to-end acceptance checks](#15-end-to-end-acceptance-checks)
16. [Monitoring and incident runbooks](#16-monitoring-and-incident-runbooks)
17. [Launch and rollback](#17-launch-and-rollback)
18. [Implementation work packages](#18-implementation-work-packages)
19. [Decisions, limitations, and fallback](#19-decisions-limitations-and-fallback)
20. [Launch checklist and deployment record](#20-launch-checklist-and-deployment-record)

## 1. Decision and constraints

### Recommended initial stack

| Responsibility | Proposed service | Role |
| --- | --- | --- |
| Website | Vercel Hobby, frontend project | Run the existing Next.js application and its server-side API proxy |
| Python API | Vercel Hobby, backend project | Run FastAPI on demand; read prepared data and optimize submitted rosters |
| Database | Supabase Free (PostgreSQL 17), Data API disabled | Keep PostgreSQL data outside the application deployments; used as plain PostgreSQL only |
| Weekly processing | GitHub Actions, standard Linux runner | Download and validate inputs, run the approved frozen model, publish the next snapshot, then exit |
| Frozen model | A deliberately tracked, versioned model artifact | Make the existing approved model available to each fresh worker |
| Reproducibility artifacts and backups | Encrypted GitHub Actions artifacts, rolling 90 days | Preserve exact files and portable backups; private object storage is deferred |
| Public URL | Vercel-provided website address | Avoid buying a domain for the initial release |

Vercel explicitly supports FastAPI as a Python Function. Using two projects keeps the current Python and Next.js applications separate while letting both use Vercel's deployment platform. This is a compatibility hypothesis for this repository until Phase B passes, not a claim that our backend has already been deployed there. [Vercel FastAPI documentation](https://vercel.com/docs/frameworks/backend/fastapi)

### Non-negotiable constraints

- No paid hosting subscription, paid trial dependency, purchased domain, or automatic plan upgrade.
- Keep PostgreSQL; do not switch production to SQLite.
- Keep real data. Do not manufacture results, projections, injury statuses, or coverage to make a page look populated.
- Keep the current restrained UI and its three areas: Player explorer, Best matchups, and My Team.
- Preserve the approved model; Tuesday refreshes update its inputs, not its training.
- Keep heavy downloads, training, and projection preparation outside HTTP requests.
- Keep the user's ESPN credentials out of scope. The app currently uses manual roster entry, not an ESPN account connection.
- Preserve immutable snapshots, reviewed completion evidence, and existing provenance.
- Never expose database credentials or service secrets in browser bundles, logs, screenshots, or committed environment files.
- Prefer a controlled pause or reduced availability over an unexpected hosting bill.

### Meaning of “production” at this budget

The desired outcome is a stable public address that works without the developer's computer running, with tested deployment/recovery procedures and honest freshness indicators. It does not include an uptime SLA, unlimited traffic, guaranteed exact-time scheduling, automatic live injury coverage, or paid operational support.

Vercel Hobby is restricted to personal, noncommercial use. If the app becomes a commercial product, advertising-supported business, or paid service, reassess eligibility before launch under that model. Being free to visitors does not by itself settle commercial-use eligibility. [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)

### 1.1 Minimal launch path

This is the authoritative launch checklist. Keep two Vercel projects, Supabase PostgreSQL, and GitHub Actions. No cloud resource was created or deployed by the September 24 implementation.

1. **Implemented locally — packaging:** API startup no longer creates data/model directories. `pyproject.toml` declares the FastAPI entrypoint `src.main:app`; `.python-version` pins Python 3.14. API dependencies are separate from `worker`, `local`, and `dev` extras. Measure the actual built function bundle; local installed-package size is not proof it fits.
2. **Implemented locally — frontend and request safety:** production refuses missing `BACKEND_URL`; no localhost fallback. Keep no-store, redirect rejection, the proxy allowlist, and the 10-second timeout. Both proxy and direct backend bound optimization requests to 16 KiB; backend counts actual received bytes before JSON parsing and the proxy preserves HTTP 413.
3. **Implemented locally — publication gates:** `weekly_refresh --season 2026` loads 2024–2026, not the next calendar year in January. This Tuesday–Monday window in America/New_York determines the intended NFL week. Missing/ambiguous schedules or a started week cannot silently select a later week. Prior-week and position coverage checks are required, not deferred.
4. **Implemented locally — approved model:** an exact unchanged copy exists at `backend/artifacts/models/lineup-model-v1.json`, with `.json.sha256`. The weekly worker verifies the checksum before ingestion. Set `MODEL_DIR=./artifacts/models`; existing local `.env` files pointing to `./models` require an owner update or command override. No model was retrained.
5. **Required cloud database:** create one Supabase Free project (PostgreSQL 17) in `us-east-1`, next to Vercel's default function region. Turn the Data API off, or at minimum leave “automatically expose new tables” off. Restore a reviewed local public-schema dump into the empty target using the Section 7 C4 procedure. Verify Alembic revision `202609220002`, important table counts, evidence, and snapshot IDs. Never restore over a populated database.
6. **Required roles:** Supabase's `postgres` role is the owner for migrations/refresh/backup through the **session pooler** (port 5432). A SELECT-only `api_reader` with future-table default privileges connects through the **transaction pooler** (port 6543). Revoke Supabase's `anon`/`authenticated` grants on `public`. No owner credential in the API or previews.
7. **Required backend deployment:** root `backend`; configure production settings, reader `DATABASE_URL` with `sslmode=verify-full`, and `DATABASE_CA_CERT=./certs/supabase-ca.crt`; confirm the certificate is in the built function bundle. Test health, readiness, search, optimization, limits, cold starts, and connection behavior. Use a disposable isolated DB for write tests, not a permanent staging service.
8. **Required frontend deployment:** root `football-forecast-ui`; server-only `BACKEND_URL` points to the stable backend URL. Check Player explorer, Best matchups, and My Team on desktop and cellular.
9. **Implemented but disabled — workflow:** `.github/workflows/weekly-refresh.yml` has Tuesday 8 a.m. Eastern scheduling, manual season input, main-branch restriction, concurrency, timeout, minimum permissions, and SHA-pinned actions. It runs only when repository variable `ENABLE_WEEKLY_REFRESH=true`. Leave unset until authorized setup is complete.
10. **Required owner configuration:** repository secret `REFRESH_DATABASE_URL` is the owner's Supabase **session pooler** SQLAlchemy URL (port 5432, `sslmode=verify-full`). GitHub-hosted runners have no IPv6, and Supabase's direct connection is IPv6-only without a paid add-on. The workflow sets `PGSSLROOTCERT` to the committed `backend/certs/supabase-ca.crt`. Preflight rejects the transaction pooler port 6543, any mode other than `verify-full`, and a missing certificate; repository variable `BACKUP_AGE_RECIPIENT` is a native age public recipient. Keep the private identity outside GitHub and retain a second secure copy. The workflow assumes default branch `main`; update deliberately if that changes.
11. **Implemented locally — encrypted archives:** encrypt the exact replay bundle and PG17 custom dump. Upload only ciphertext and its checksum sidecars. Retry once using the same ciphertext, download it, and verify checksums. Publication, replay, backup, and upload/verification outcomes are distinct.
12. **Required recovery check:** download/decrypt/restore one cloud backup into an empty disposable DB with the owner's production identity. Check schema/data and reapply reader grants. A local fixture roundtrip does not prove the production identity was safely retained.
13. **Required cloud refresh test:** after approval and setup, enable the workflow, trigger manually, inspect intended week/coverage, and confirm the site sees the exact snapshot without a rebuild. On failure disable the variable while investigating. Do not republish merely to retry an archive.
14. **Required operational checks:** confirm failed-workflow notifications, account quotas/spending controls, actual resource usage, and real-device behavior. Public standard runner minutes are free; still verify artifact storage usage and retention in the account.
15. **Retention:** rolling 90 days, about 13 weeks—not a full NFL season. For longer history, download copies periodically before expiry; season-end collection cannot recover already expired artifacts.
16. **After launch:** measure DB growth/compute, Vercel usage, and runtime. Check that schedules remain enabled; public-repository inactivity can disable them.

### 1.2 Required safeguards and accepted beta limits

**Required:** intended-week/previous-week/position checks, direct backend size cap, encrypted exports, one owner-key recovery check, read-only API role, cloud smoke tests, and truthful failure reporting.

**Deferred:** persistent staging, backend service token, custom rate limiter, additional roles, persistent refresh ledger/full-run lease, catch-up trigger, archive-before-publication redesign, private object storage, recurring timed restore drills, elaborate release records.

Accepted limitations:

- Direct backend reads/optimization remain public. CORS is not authentication.
- Successful manual reruns can append duplicate-week snapshots; avoid unnecessary reruns.
- Publication precedes archiving. Cancellation or exhausted uploads can leave a published result without its full replay archive. A new download cannot recover vanished exact inputs.
- Coverage gates use the observed schedule and detect dataset/position gaps, not every individual player omission or an independent schedule-provider mismatch.
- Evidence can include private reviewer identifiers/free-text notes. Public football data does not make every DB field safe to publish.
- Browser-local rosters, participation warnings, scoring/model behavior, and the existing UI are unchanged.

Implementation: `publication_checks.py`, `prepare_lineups.py`, `weekly_refresh.py`, `archive_refresh.py`, `refresh_preflight.py`, `refresh_result.py`, `src/api/body_limit.py`, frontend helper/proxy, packaging/model files, and the workflow. Tests are in `test_deployment_guards.py`, `test_refresh_archives.py`, and `lib/backend.test.ts`.

## 2. Target architecture

Request path:

```text
Browser → Next.js / allowlisted same-origin proxy
        → FastAPI (read-only SQL access + bounded optimizer)
        → Supabase PostgreSQL (transaction pooler, SELECT-only role)
```

No source download, migration, training, or weekly preparation runs in HTTP requests. Serverless instances share durable state through PostgreSQL, not their local filesystem.

Weekly path:

```text
Trusted main-branch workflow, explicitly enabled
  → validate season, frozen-model checksum, encryption, PG17 clients
  → ingest/validate canonical data
  → resolve intended NFL week and prepare projections
  → validate prior-week/position coverage
  → write exact local artifacts; recheck kickoff; publish immutable snapshot
  → encrypt replay bundle and portable database backup
  → upload ciphertext (one retry); download/check checksums
  → report publication / replay / backup / verification separately
```

Archive-before-publication remains deferred. The current flow can publish before an archive failure; it must never imply that a fresh source download recovers the exact lost archive.

## 3. What exists and what is missing

| Area | Implemented locally | Cloud verification still required |
| --- | --- | --- |
| API | Explicit entrypoint, Python pin, dependency extras, no startup mkdir, 16 KiB body guard, prepared statements disabled for the Supabase transaction pooler | Built function size, startup, cold/warm latency, direct 413 |
| Frontend | Production URL validation, existing proxy bounds, backend 413 propagation | Stable URL/protection configuration, mobile behavior |
| Refresh | Explicit season, checksum, intended week, coverage gates, safe status result | Real source data and cloud runtime |
| Replay archive | Exact raw/supplement/prepared/evidence/model files, checksummed manifest, age encryption | Upload sizes, owner-key download/decrypt |
| Backup | PG17 public-schema custom dump, readability check, age encryption; real `age` round trip and local public-schema dump→restore rehearsal passed September 27 | Actual Supabase dump/decrypt/restore with the owner's production identity |
| Automation | Opt-in main-only workflow, concurrency, upload retry/download verification | Secrets, recipient, notifications, real cloud run |

Preserved behavior: immutable snapshots; separate existing Best matchups and My Team scoring paths; complete ESPN lineup optimizer; browser-local rosters; injury warnings/manual exclusions. No live injury feed or model retraining was added.

### Local verification record — September 24, 2026

These checks ran on the developer machine only. None is a cloud verification.

| Check | Result |
| --- | --- |
| Backend tests (`venv/bin/pytest -q`, Python 3.14) | 159 passed, 1 skipped |
| Backend lint and format (`ruff check`, `ruff format --check`) | Passed |
| Frontend tests (`bun test lib`) and lint (`bun run lint`) | 14 passed; lint clean |
| Real `age` encrypt/decrypt round trip (`test_real_age_encryption_and_owner_only_decryption`) | Skipped September 24 (`age` not installed). **Passed September 27** with `age` 1.3.1 |
| PG17 backup → restore rehearsal (unencrypted), using the local Docker `postgres:17-alpine` container's `pg_dump` 17.11 | **Passed.** `pg_dump -Fc --no-owner --no-privileges` of the 38 MB local database produced a 1.5 MB archive. `pg_restore --list` read 144 entries. A `--exit-on-error` restore into a new, empty scratch database succeeded. All 17 public-table row counts matched the source. Alembic revision `202609220002` matched, as did the 4 non-internal triggers and the lineup snapshot ID/timestamp hash. An `UPDATE` on the restored `lineup_snapshots` was rejected ("Lineup snapshots are append-only"), so immutability guards survive a restore. The scratch database and dump file were then removed |

### Local verification record — September 27, 2026 (Supabase switch)

| Check | Result |
| --- | --- |
| Backend tests (`venv/bin/pytest -q`) | 171 passed, 0 skipped. Includes the real `age` round trip, new tests for the Supabase pooler and TLS guards, and the kickoff-vs-now publication gate |
| Backend lint and format | Passed |
| Frontend tests, lint, and `tsc --noEmit` | 15 passed; lint and typecheck clean |
| Date-dependent test fixture | Fixed. The upcoming-game fixture was pinned to September 27 and began failing on that date (7 tests). It is now relative to the real clock |
| Public-schema backup → restore rehearsal (`pg_dump --schema=public`, then `pg_restore -L` with the `CREATE SCHEMA public` entry removed) | **Passed** against an empty scratch database: exit 0, `games` count 816, Alembic `202609220002`, 4 triggers, snapshot content hash identical, `UPDATE lineup_snapshots` still rejected. A plain restore of a `--schema=public` dump fails with “schema public already exists”, which is why the list filter is required. Scratch database and dump removed |
| CodeRabbit CLI review (`coderabbit review --agent --include-untracked`) | Run 1: 3 findings, all fixed. Dashboard showed `0` for missing stats instead of `—`; `MRD.md` still required `NEXT_PUBLIC_API_BASE_URL`; the implementation plan's baseline-eligibility rule was stale. Run 2: 1 finding, fixed: `sslmode=require` does not verify the server, so `verify-full` with the Supabase CA is now required and enforced by preflight. Run 3: stale test counts in `docs/backend-implementation-status.md`, fixed. Run 4: 3 findings. Fixed: a stale eligibility rule in the implementation plan. Not changed, because the behavior is intentional: the chart is oldest→newest and labeled as such while the game log is newest-first; preliminary rankings deliberately use labeled partial opponent coverage, and published forecasts still require complete coverage. Run 5: two `MRD.md` errors (the `PRD.md` filename; an unreachable neutral-site branch in pseudocode), fixed. Run 6: 2 findings, fixed. (a) **Forecast publication now blocks with `target_week_started` when any target kickoff is at or before the current time**, even if the stored status is still `upcoming` and the cutoff precedes kickoff. (b) Saved My Team recommendations now also validate `roster_status`, `unavailable_reason`, and `weighted5`. Run 7: 2 findings, fixed. The workflow summary no longer crashes on a published result missing snapshot/season, so its ACTION REQUIRED line is always written. A schedule row with a missing `game_type` is now reported as a source error instead of silently skipped; all 842 rows in each local nflverse schedule have it. Run 8: 1 finding, fixed: archive verification now fails if any downloaded `.age` file lacks a checksum manifest. Run 9: 1 finding, fixed: the test-suite safety check now refuses a test database with the same name as the app database, whatever the host alias or port, since `localhost` versus `127.0.0.1` previously slipped past it. **Run 10: 0 findings (clean).** |

What these rehearsals do **not** prove: the owner's production identity being retained, a dump taken from Supabase through the session pooler, or reader-role grants after restore. Those remain part of the required cloud recovery check (Section 1.1, step 12; Section 12.6).

Prior local measurements: database about 38 MB (about 1.5 MB as a compressed custom-format dump); Python install about 315 MB including about 172 MB Polars; one prepared lineup artifact about 119 MB uncompressed. These are not cloud bundle/compute/storage guarantees. Measure growth, compressed archive sizes, full worker memory, and latency.

Cloud provisioning, role grants, migration, actual deployment, owner production-key setup, workflow activation, public/mobile checks, and production recovery remain outstanding. Changes are in the local worktree, not claimed committed/pushed.

## 4. Free-tier budget and capacity

### Provider allowances to verify at setup

| Provider | Relevant researched allowance | Planning interpretation |
| --- | --- | --- |
| Vercel Hobby | Free personal/noncommercial hosting with metered usage limits | Two projects do not imply two independent account-wide free allowances |
| Supabase Free | 2 active projects per account, 500 MB database per project, 5 GB egress (plus 5 GB cached), shared CPU/500 MB RAM, **no backups**, paused after 1 week of inactivity | Initial 38 MB database fits. As of September 27 the owner's `KBesada24` org has one other project (paused), so both active slots are available. The encrypted weekly `backup.age` is the only backup |
| GitHub Free | Standard GitHub-hosted runners are free for **public** repositories; the 2,000-minute and 500 MB allowances apply only to private ones | This repository is public, so the runner-minute budget does not constrain the weekly job. Artifact retention is at most 90 days |
| Supabase Storage | 1 GB on Free | Candidate private archive destination if replay history beyond 90 days is ever needed; deferred |

Sources: [Vercel Hobby](https://vercel.com/docs/plans/hobby), [Supabase pricing](https://supabase.com/pricing), [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

**Inactivity pause.** Supabase pauses a Free project after about a week without activity. The weekly refresh runs every 7 days, which is borderline on its own; ordinary site visits also reach the database through the API. A paused project does not bill. It makes the site's data unavailable, and the Tuesday preflight fails with a GitHub failure email. Recovery: restore the project from the Supabase dashboard (free), then rerun the workflow manually before kickoff. Do not add an artificial keep-alive until pausing is actually observed. Supabase decides what counts as activity, so its effectiveness would need to be verified.

### No-surprise-billing policy

1. Select permanent Free/Hobby plans, not paid trials with future conversion.
2. Avoid adding a payment method solely to activate an optional feature.
3. Inspect account-wide usage before creating this app's resources.
4. Disable paid overages where supported and configure applicable hard-stop budgets.
5. Verify whether a control is only an email alert or actually stops billable usage.
6. Do not enable larger paid GitHub runners or paid Vercel features.
7. Do not buy a domain; use the included website address.
8. Record the selected plans and controls in the deployment record at the end.
9. If a platform cannot enforce the required $0 boundary, stop and discuss alternatives rather than assuming a small charge is acceptable.

GitHub distinguishes alert-only budgets from budgets that stop usage. Account-specific enforcement details must be checked; a budget label alone is not an absolute billing guarantee. [GitHub budget controls](https://docs.github.com/en/billing/how-tos/set-up-budgets)

### Initial operational budgets — our targets, not provider guarantees

- Warn when database usage reaches 300 MB; investigate urgently at 400 MB.
- Warn when Supabase egress reaches 70% of the displayed monthly allowance.
- Target routine weekly processing under 30 minutes after optimization; first-run downloads may take longer.
- Set an initial 60-minute workflow timeout and measure before increasing it.
- Actions minutes are not a constraint while the repository stays public. If it is ever made private, reintroduce a minute budget: 2,000 minutes per month, shared across the account.
- Keep Actions artifacts to what Section 12 lists (lineup inputs, quality report, `pg_dump`), with 90-day retention.
- Avoid frequent DB-backed uptime polling; it wastes free egress and function executions.
- Track Vercel usage across both frontend and backend: a browser API call may involve two function executions.

The real refresh runtime has not been measured in GitHub Actions yet. Record it after the first manual run.

## 5. Phase A — repository and account preparation

### A1. Preserve and prepare the source

1. Inspect the current dirty worktree and preserve all unrelated changes.
2. Confirm all application source, migrations, mappings, and tests required for deployment are deliberately included in the eventual commit.
3. Do not run `git add .` without review: this repository contains many untracked files, output screenshots, and local artifacts.
4. Keep `.env`, virtual environments, local data, caches, logs, and `.vercel` account-link files out of source control.
5. Choose a specific, narrowly scoped directory for the approved frozen model; do not remove the broad raw-data ignore rules.
6. Scan both the planned commit and relevant repository history for leaked credentials. Rotate any exposed credential before use.
7. The repository is already public. Before committing, review every new file for anything you would not publish, such as personal notes in `HANDOFF.md`/`MRD.md` or screenshots under `output/`. Public repositories owned by a personal account work with the Vercel Hobby Git integration.
8. Keep the existing package lockfile and pinned Python dependencies reproducible.

### A2. Accounts and ownership

- Use the user's own Vercel, Supabase, and GitHub accounts. As of September 27 the Vercel (`kbesada24`), Supabase, GitHub (`gh`), and CodeRabbit CLIs are authenticated on the owner's machine. The Vercel and Supabase CLIs are not on `PATH`; run them as `bunx vercel` / `bunx supabase`.
- Enable account two-factor authentication and preserve recovery codes outside the repository.
- Confirm free-plan eligibility, remaining allowance, and any existing payment settings.
- Prefer the provider dashboards for initial project creation; add automation tokens only where needed.
- Keep the backend and frontend in the same Vercel account for straightforward ownership, while retaining separate project settings.

### A3. Environment strategy

Use these environments:

| Environment | Database | Credentials | Purpose |
| --- | --- | --- | --- |
| Local development | Existing local PostgreSQL | Local only | Normal development |
| CI tests | Temporary PostgreSQL service in the runner | Disposable test credentials | Automated tests without cloud database writes |
| Staging/preview | Second Supabase Free project (the account's other active slot); branching is not a Free feature | Staging-only roles | Compatibility and release checks |
| Production | Production Supabase project | Restricted production roles | Public beta |

**Minimal launch:** local development, production, and (optionally) CI only. Test changes locally against the restored data before deploying. **Deferred:** the staging row above.

When staging is adopted, default to one persistent production database and a small, temporary staging environment used for releases. Verify the two-active-project allowance before creating it. Isolate credentials.

Do not give arbitrary pull-request code production secrets. If protected environments or reviewer gates are unavailable on the account's free plan, use a documented owner-run release procedure rather than assuming a paid protection feature exists.

**Phase A exit condition:** source is deployable from a clean checkout, ownership is clear, and no paid plan or secret exposure is required.

## 6. Phase B — serverless compatibility test

This is the first technical gate. Use an isolated disposable database for write tests; persistent staging is not required. Verify compatibility before switching the public URL.

### B1. Explicit FastAPI entrypoint

The existing application is `src.main:app` relative to `backend/`.

Proposed configuration, to be validated before adoption:

```toml
# Proposed addition to backend/pyproject.toml; not applied by this document.
[tool.vercel]
entrypoint = "src.main:app"
```

Do not run `python main.py`, `uvicorn --reload`, or a persistent web server as a production start command on Vercel. The platform imports the ASGI app. [FastAPI entrypoint configuration](https://vercel.com/docs/frameworks/backend/fastapi)

### B2. Remove API dependence on local writable storage

- Serving a request must not create or require `backend/data` or `backend/models`.
- Move worker-directory initialization into worker startup, or make API startup independent of those directories.
- Use temporary storage only for genuinely temporary operations, never for the database, saved rosters, models required across runs, or durable snapshots.
- Ensure importing the API cannot start downloads, migrations, training, or snapshot preparation.
- Test app import and lifespan startup with a read-only source directory.

### B3. Separate serving and processing dependencies

Audit the complete API import graph before changing dependency groups.

Proposed packaging:

- Base/API dependencies: FastAPI, SQLAlchemy, psycopg, Pydantic settings, and any libraries actually imported by request handling.
- Worker dependencies: nflreadpy, Polars, data/archive tooling, and model-preparation dependencies.
- Migration dependencies: Alembic and database support.
- Development dependencies: pytest, Ruff, httpx, and test tools.

Implemented extras: `worker`, `local`, and `dev`. Runner: `pip install '.[worker]'`. Local/test: `pip install -e '.[dev,worker,local]'`. The API base excludes nflreadpy/Polars; preserve that import boundary.

Select and pin a Vercel-supported Python version compatible with all wheels. Vercel currently offers 3.12 (default), 3.13, and 3.14, so the local 3.14 environment can be kept. Reproduce the tests on the exact version chosen for deployment.

Measure the built function bundle and use the normal free-plan limits. The standard Python bundle limit is 500 MB uncompressed. Do not depend on an optional large-function beta or a paid entitlement to make the build pass. [Vercel function limits](https://vercel.com/docs/functions/limitations)

### B4. Exercise real request behavior

Test the following locally and on the candidate cloud deployment; isolate checks that write data:

1. App startup with no local data/model directories.
2. Liveness endpoint without touching PostgreSQL.
3. Readiness against an active database and after the database has suspended.
4. Player search, dashboard, rankings, and lineup catalog.
5. A valid nine-slot lineup optimization.
6. The largest allowed roster/slot request, currently 30 players and 12 slots.
7. Invalid/oversized requests and stale snapshot rejection.
8. Multiple concurrent requests without exhausting connections.
9. Both warm and cold frontend-to-backend requests, including the current 10-second timeout boundary.
10. Confirmation that no request wrote a roster or triggered data preparation.

Record response sizes, cold/warm duration, errors, memory, and database connections. Optimize measured problems; do not claim deployment compatibility based only on `/health` returning 200.

**Phase B exit condition:** the real application fits the free runtime and its user-facing flows work acceptably. If it fails after reasonable packaging fixes, evaluate the Render fallback in Section 19 before expanding scope.

## 7. Phase C — Supabase PostgreSQL

Supabase is used only as a managed PostgreSQL 17 server. The app does not use Supabase Auth, Storage, Realtime, or the auto-generated Data API. Its three connection options behave differently, so each client uses a specific one:

| Client | Connection | Why |
| --- | --- | --- |
| FastAPI on Vercel (`api_reader`) | Transaction pooler, `aws-…pooler.supabase.com:6543`, user `api_reader.<project-ref>` | Built for many short-lived serverless connections. It does not support prepared statements; `src/core/database.py` sets psycopg `prepare_threshold=None` |
| Weekly workflow, migrations, `pg_dump` (`postgres`) | Session pooler, same host, port `5432`, user `postgres.<project-ref>` | IPv4-reachable from GitHub runners, and keeps session state for `pg_dump`. `refresh_preflight` rejects port 6543 |
| Direct connection `db.<project-ref>.supabase.co` | Not used | IPv6-only unless the paid IPv4 add-on is purchased |

[Supabase connection documentation](https://supabase.com/docs/guides/database/connecting-to-postgres)

### C1. Provision the database after deployment approval

1. Create one Free project (currently PostgreSQL 17, matching local development) in `us-east-1`. Create it in the owner's own `KBesada24` organization, not the Vercel-integration organization, so it stays on Supabase's Free plan rather than Vercel Marketplace billing.
2. Generate a strong database password and store it only in a password manager.
3. Disable the Data API (Integrations → Data API → Enable Data API off). None of the app's traffic uses it. Projects created after May 30, 2026 no longer expose new `public` tables automatically, but C2 revokes the grants anyway.
4. Confirm the dashboard's storage, egress, and pause behavior, and that no payment method or Pro trial is attached.
5. Turn on **Enforce SSL on incoming connections** (Database Settings → SSL Configuration). Download the CA certificate from the same section and commit it as `backend/certs/supabase-ca.crt`. It is a public CA certificate, not a secret. Every connection string uses `sslmode=verify-full`: `require` encrypts but does not authenticate the server. [Supabase SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement)

### C2. Separate privileges

**Minimal launch:** two roles. The Supabase **`postgres`** role (the owner here) handles migrations, the weekly job, and backups. An **`api_reader`** role has `SELECT` only. **Deferred:** splitting the owner into the refresh-writer, migration-owner, and backup-reader roles below.

| Role | Intended permissions | Used by |
| --- | --- | --- |
| API reader | Connect, schema usage, SELECT on required application tables | FastAPI Vercel project |
| Refresh writer | Required reads and canonical-data writes; INSERT for immutable snapshots | Scheduled workflow |
| Migration owner | Schema ownership and migration privileges | Explicit migration operation only |
| Backup reader | Sufficient access for a complete application backup | Backup operation, if practical to separate |

Run once in the Supabase SQL editor, after the C4 restore. The password is a placeholder; generate it and never commit it:

```sql
-- API reader: SELECT only, including tables created by future migrations.
create role api_reader login password '<generated>';
grant usage on schema public to api_reader;
grant select on all tables in schema public to api_reader;
alter default privileges for role postgres in schema public grant select on tables to api_reader;

-- Supabase API roles must not reach application data, even if the Data API is re-enabled.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated;
```

Verify: as `api_reader`, a `SELECT` succeeds and an `INSERT` fails; `select has_table_privilege('anon', 'public.games', 'select')` is false. Verify the owner can perform legitimate ingestion without disabling snapshot triggers.

Do not use the owner credential as the routine API credential. Do not expose database credentials to the frontend project.

### C3. Connection handling

- API: transaction pooler with prepared statements disabled (implemented). Keep SQLAlchemy's small default pool with `pool_pre_ping`; measure concurrent serverless instances before tuning.
- Worker, migrations, and backups: session pooler. Advisory locks used by preparation are transaction-scoped (`pg_advisory_xact_lock`) and work in either mode.
- Preserve request-level `REPEATABLE READ` and `READ ONLY` behavior; prove it through the transaction pooler.
- Close/rollback sessions on exceptions, timeouts, and cancelled requests.
- Configure finite connection and statement timeouts.

The installed driver is psycopg 3. SQLAlchemy URLs use `postgresql+psycopg://…?sslmode=verify-full`. Percent-encode special characters in the password. The CA path is not placed in the URL. The API passes `DATABASE_CA_CERT` (resolved relative to `backend/`) as psycopg's `sslrootcert`. The workflow sets libpq's `PGSSLROOTCERT`, which covers every worker connection and `pg_dump`. `archive_refresh` converts the URL to a libpq URI in `PGDATABASE` for `pg_dump`, so only one secret format is needed.

### C4. Initial data transfer — recommended route

Restore the existing local database so immutable snapshots, evidence, and original timestamps are preserved.

1. Capture the current schema revision, table counts, latest snapshot identifiers, and model checksum.
2. Dump only the application schema: `pg_dump -Fc --no-owner --no-privileges --schema=public`. This matches what the weekly backup does and excludes the separate test database. Supabase's own schemas (`auth`, `storage`, …) must never be restored over.
3. Inspect the archive for unintended private data.
4. Build a restore list without the `CREATE SCHEMA public` entry, which already exists on Supabase: `pg_restore -l dump > list`, then delete the ` SCHEMA - public ` line. Do **not** use `--clean`: it would try to drop Supabase's `public` schema.
5. Restore with `pg_restore --no-owner --no-privileges --exit-on-error -L list` into the **empty** Supabase database through the session pooler. This exact procedure passed locally on September 27 (Section 3).
6. Apply any migrations newer than the restored revision (`alembic upgrade head`, session pooler).
7. Apply the C2 SQL; a restore is not proof that production permissions are correct.
8. Compare row counts, immutable snapshot IDs, evidence, schedules, and sample API outputs.
9. Preserve the original local database and dump until the cloud release and recovery check pass.

Alternative: create an empty schema with Alembic and replay source ingestion. This rebuilds canonical data, but does not automatically preserve reviewed evidence or historic published snapshots. Use this route only with an explicit transfer plan for those records. Never fabricate a backdated pregame snapshot from current data.

### C5. Migration rules

- Run migrations once as a controlled operation, not at every function startup or frontend build.
- Verify `alembic current`, `alembic heads`, and `alembic check` against the intended target.
- Take a recoverable backup before a risky schema change.
- Prefer additive, backward-compatible migrations so old and new application versions can coexist during deployment.
- Keep test databases and production migration credentials completely separate.
- Do not use a destructive downgrade as the default rollback method.

**Phase C exit condition:** data is restored into the approved empty Supabase target; `anon`/`authenticated` have no table privileges; reader permissions pass positive/negative tests; a backup restores independently into a disposable target.

## 8. Phase D — Vercel backend

### Project settings

| Setting | Proposed value |
| --- | --- |
| Project purpose | Python API only |
| Root directory | `backend` |
| Framework | FastAPI / supported Python integration |
| Entrypoint | Explicitly resolved `src.main:app` |
| Python version | Pinned version validated in Phase B |
| Database | Production Supabase via the transaction pooler (`api_reader`) |
| Region | Near the database, within the free plan's supported choices |
| Application files | Source and required configs only; no venv, bulk raw data, or secrets |

Vercel supports multiple projects from separate directories of the same repository. Configure their roots independently rather than deploying the repository root as if it were one application. [Vercel monorepos](https://vercel.com/docs/monorepos)

### Required behavior

- Import and serve the existing API contract.
- Fail clearly if database configuration is missing. Service authentication is deferred; its variables are not launch requirements.
- Do not create schemas or seed data during build/startup.
- Do not require local model files for request handling.
- Keep exceptions redacted: no DSNs, raw SQL values containing secrets, or full tracebacks returned to users.
- **Deferred:** enforce authentication for application routes using a constant-time secret comparison or another explicitly selected server-to-server mechanism. For the beta, the backend is reachable directly and exposes only the same read-only endpoints and bounded optimization that the public proxy already exposes.
- Keep a minimal public liveness response if needed; protect database-readiness and diagnostic endpoints.
- Decide whether `/docs` and `/openapi.json` are disabled or protected in production.
- Include safe release metadata in logs: commit identifier, environment, and request ID.

### Cross-project access

The frontend project calls the backend project's stable HTTPS alias. It must not pin production to a disposable preview URL.

Vercel deployment protection and application authentication are different layers. If platform protection blocks server-to-server requests, configure a supported server-only bypass for that environment or deliberately use the beta's public, read-only backend. Application authentication remains deferred. Do not disable all protection reflexively or expose a bypass token to the browser.

Vercel's default Standard Protection covers preview and deployment-specific URLs, not the production domain. The frontend should therefore be able to call the backend's production domain without a bypass. Confirm this under Project Settings → Deployment Protection.

**Phase D exit condition (minimal launch):** API calls work from the frontend server and the backend survives redeploys without data loss. **Deferred:** unauthorized direct calls fail.

## 9. Phase E — Vercel frontend

### Project settings

| Setting | Proposed value |
| --- | --- |
| Root directory | `football-forecast-ui` |
| Framework | Next.js |
| Installation | Use the checked-in lockfile and a pinned compatible package-manager version |
| Build | Existing production build script, currently `bun run build` |
| Backend URL | Stable HTTPS alias for the corresponding backend environment |
| Public address | Vercel-provided URL; custom domain deferred |

### Connection changes

1. Keep the existing `/api/football/*` proxy and route allowlist.
2. Add the backend service credential only within server-side fetch code.
3. Reject missing/invalid production `BACKEND_URL` instead of using localhost.
4. Require a trusted HTTPS destination in production; never accept a backend hostname from user input.
5. Preserve the JSON body limit and redirect rejection.
6. Test or adjust the upstream timeout based on measured cold starts; keep it finite and below the outer function deadline.
7. Show an actionable loading/error/retry state without erasing the user's saved roster.
8. Preserve request IDs across the proxy for diagnosis, without logging roster bodies.

The browser uses a same-origin proxy, so broad browser CORS access to the backend is unnecessary. CORS is not authentication and cannot stop direct scripted requests.

### Saved teams and origin changes

The existing roster and saved recommendation are stored in localStorage. They are tied to the exact website origin and browser profile.

- A roster saved under ngrok does not automatically appear under `*.vercel.app`.
- Phone and desktop do not automatically share teams.
- Clearing site data can remove the saved roster.
- A later move to a custom domain creates another origin transition.

Initial-release default: explain the change and let the user re-enter the roster. Export/import is a useful optional improvement, but is not implemented by this plan. Do not claim cloud synchronization or silently copy data from a different browser origin.

**Phase E exit condition:** the current UI works from the permanent beta URL, with server-only credentials and honest local-storage behavior.

## 10. Configuration and secrets

Never place DB credentials in `NEXT_PUBLIC_*`, browser code, checked-in env files, public logs, screenshots, or plaintext artifacts.

| Location | Name | Value / scope |
| --- | --- | --- |
| Backend production | DATABASE_URL | `api_reader` Supabase **transaction pooler** URL (port 6543), `postgresql+psycopg://…?sslmode=verify-full` |
| Backend production | DATABASE_CA_CERT | `./certs/supabase-ca.crt` (committed public CA certificate) |
| Backend production | ENVIRONMENT | production |
| Frontend production | BACKEND_URL | Stable backend HTTPS origin; server-only |
| GitHub repository secret | REFRESH_DATABASE_URL | `postgres` owner Supabase **session pooler** URL (port 5432), `sslmode=verify-full`; trusted main-branch job only |
| Workflow environment | PGSSLROOTCERT | Set by the workflow to `backend/certs/supabase-ca.crt` |
| GitHub repository variable | BACKUP_AGE_RECIPIENT | Native age public recipient; never the private identity |
| GitHub repository variable | ENABLE_WEEKLY_REFRESH | Unset/false until approved setup; true enables manual/scheduled runs |
| Workflow environment | MODEL_DIR | ./artifacts/models |
| Manual input / job env | season / NFL_SEASON | NFL season, default 2026 |
| Owner offline storage | age private identity | Outside GitHub and repo; retain a second secure copy |

The backup command converts the SQLAlchemy URL into a libpq URI in `PGDATABASE`, not process arguments. Owner DB privileges currently serve migrations and refresh; additional roles remain deferred.

### Previews and trust

No permanent staging environment is required. An owner-reviewed trusted preview may use the production API reader. Untrusted/fork PR code receives no production secrets: read-only does not prevent credential disclosure or compute exhaustion. Never give a preview the owner credential or run migrations/refresh there. Once staging exists, use isolated staging credentials.

Service-token variables are not implemented or required. A future server-only token is not a substitute for protecting the public frontend proxy.

### Rotation

Rotate leaked credentials at the provider, update affected server/workflow values, and redeploy/test. Deleting a file is not revocation. Preserve old private archive identities for as long as their backups are retained: changing the public recipient does not re-encrypt old archives.

## 11. Phase F — Tuesday refresh

### F1. Product contract

The target is to start refreshing around **Tuesday 8:00 a.m. America/New_York**:

- Incorporate the previous NFL week's completed games, including Thursday, Sunday, and Monday games and any other games scheduled in that NFL week.
- Use actual schedule/week identifiers, not a hardcoded list of weekdays. Saturday games, international games, postponements, and the season boundary must not be accidentally omitted.
- Update upcoming opponents and player context.
- Reuse the frozen model to prepare the next intended week's recommendations.
- Do not train, tune, or change model selection automatically.

Eight o'clock is the intended start time, not a guaranteed publication timestamp. GitHub documents possible schedule delays/dropped runs, and public-repository schedules may be disabled after prolonged inactivity. An independent freshness check and manual recovery path remain necessary. [GitHub scheduling limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

### F2. Schedule and manual trigger

**Minimal launch:** one Tuesday 8 a.m. trigger plus `workflow_dispatch`, a concurrency group, and the explicit `--season` argument from Section 1.1. The existing worker already refuses to save a snapshot once the week has started. If the scheduled run fails or is dropped, the owner starts it manually. **Deferred:** the 9 a.m. catch-up trigger. Add it only together with the completed-period guard from F5, because without that guard a second successful run publishes a duplicate snapshot for the same week.

The full proposed trigger fragment, after the F5 safeguards exist, is below. It is **not a complete runnable workflow**:

```yaml
name: Weekly football refresh

on:
  schedule:
    - cron: '0 8 * * 2'
      timezone: America/New_York
    - cron: '0 9 * * 2'
      timezone: America/New_York
  workflow_dispatch:
    inputs:
      season:
        description: 'NFL season, not calendar year'
        required: true
        default: '2026'
      week:
        description: 'Optional explicit upcoming NFL week'
        required: false

permissions:
  contents: read

concurrency:
  group: football-refresh-production
  cancel-in-progress: false
```

The 9 a.m. trigger is a catch-up opportunity, not a second required publication. A completed-period check should make it exit without downloading or republishing when the 8 a.m. run succeeded. GitHub supports the IANA `timezone` field on schedules (verified September 23, 2026), so daylight-saving changes need no UTC workaround. [Workflow schedule syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)

The schedule runs the default branch. Keep that branch's refresh code deployment-compatible and do not assume an unmerged workflow will execute on a schedule.

### F3. Runner setup

1. Use a standard Linux GitHub-hosted runner, not a paid larger runner.
2. Pin third-party actions to reviewed immutable commit SHAs when implementing the actual workflow.
3. Check out trusted code with the minimum token permissions; do not persist Git credentials unnecessarily.
4. Install the same tested Python version and locked/pinned worker dependencies.
5. Obtain the approved model from its versioned location and verify SHA-256.
6. Set environment-specific credentials without printing them.
7. Create temporary data directories under the runner workspace.
8. Validate all manual input as data; do not interpolate untrusted workflow inputs directly into shell commands.
9. Apply a workflow timeout, bounded network timeouts, and a finite retry policy.
10. Record source commit, run URL/ID, model version, and intended season/week.

Never run the refresh in a workflow that executes untrusted pull-request code with production secrets. `pull_request_target` is not a shortcut for doing this safely.

### F4. Correct season and target-week selection

Implemented in the refresh/preparation/check modules; verify before production activation:

- Accept an explicit validated season; initial production value is **2026**.
- Load the agreed historical seasons 2024, 2025, and 2026.
- Do not automatically include 2027 data just because the calendar turns to January 2027.
- Determine the intended next NFL week from the schedule and the completed previous week.
- Require the selected week to be fully upcoming under the existing pregame policy.
- Do not silently skip a missing intended week and publish a much later fully upcoming week.
- Handle an offseason/no-supported-upcoming-week condition as an explicit no-op or operator-review state.
- Keep postseason expansion out of scope until supported and deliberately specified; regular-season week numbers must not collide with playoff identifiers.

When the next season is added, make it a deliberate data/model compatibility review rather than an unattended calendar-year side effect.

### F5. Full-run coordination and idempotency — Deferred

**Minimal launch:** the GitHub concurrency group plus the existing snapshot-insertion advisory lock and kickoff check. A duplicate run for the same week creates an extra immutable snapshot, and the API serves the newest one. That is acceptable for a beta; the owner can avoid it by not re-running a successful week.

The present snapshot-insertion advisory lock is not enough to protect the entire workflow for unattended multi-trigger operation.

Implement:

- One production refresh concurrency group in GitHub.
- A database-backed full-run lock or lease to coordinate scheduled and operator-triggered runs.
- A persistent refresh ledger recording season, target week, intended Tuesday period, status, timestamps, attempts, model checksum, source artifact IDs, snapshot IDs, archive references, and redacted failure reason.
- An explicit distinction between an ordinary retry and an authorized correction publication.
- A successful-period short circuit before expensive downloads.
- Recovery for a runner killed between database commit and writing the final job result.

Prefer a direct database connection for a session-scoped advisory lock; do not hold it through a transaction pooler and assume session affinity. A lease-based implementation is also acceptable if expiry, ownership, and recovery are tested.

Do not hold one giant SQL transaction open during network downloads. Coordinate the workflow separately and keep actual database transactions bounded.

Suggested run states: `running`, `canonical_updated`, `snapshot_prepared`, `archived`, `published`, `succeeded`, `blocked`, and `failed`. These are a proposed operational model, not existing table columns.

### F6. Data validation and publication sequence

**Launch validation is implemented. Archive-before-publication remains deferred.**

Before inserting a snapshot:

1. Resolve this Tuesday 00:00–next Tuesday 00:00 window in America/New_York. Use its exact NFL week, not an arbitrary later fully upcoming week.
2. Reject missing/ambiguous in-season windows; report explicit no-op outside the observed regular season. Missing/undated season schedules are errors. Only regular-season weeks 1–18 are supported.
3. Require the target week to be fully upcoming; recheck first kickoff in the insertion transaction.
4. Retain existing canonical schema/scoring/completed-game checks.
5. For Week 2 onward, require the preceding NFL week and completed status on its observed games.
6. Require scored offense and D/ST rows for each previous-week game/team. D/ST depends on team stats and PBP. Require a previous-week kicker scoring row league-wide, not for every individual team (a team can legitimately have no kicker scoring row).
7. Require finite usable projections for QB/RB/WR/TE/K/DST. Individual missing history can exclude a player without blocking everyone.
8. Week 1 has no Week 0 requirement; projections need adequate historical inputs. Upstream download/schema constraints can still block a run if a required source feed is absent.
9. Write `coverage-report.json` with missing inputs/teams, position counts, exclusion reasons, and errors. Block before inserting a snapshot on failure.

These are minimum dataset/position gates, not a promise of every player's coverage. Fresh download timestamps alone do not establish fresh game data. Independent schedule reconciliation is deferred.

The workflow then writes exact local artifacts, publishes, encrypts replay/backup files, uploads, downloads, and checks ciphertext hashes. `data/refresh-result.json` and the public-safe workflow summary distinguish canonical ingestion from lineup publication and archive outcomes. A local result file is not a durable database ledger.

If upload fails, retry the same ciphertext once while the runner still exists. Mark the overall workflow failed if replay encryption, backup, upload, or verification fails. Do not download again and claim original inputs were recovered. A lost runner can leave an archive gap after publication.

Future stronger sequence: prepare → archive/verify → recheck kickoff → publish with archive linkage, under a persistent ledger. That redesign is not part of this launch.

### F7. Retry and failure behavior

- Retry transient download/connection failures a small bounded number of times with backoff and jitter.
- Do not retry schema mismatch, invalid scoring, conflicting identities, or incompatible model versions indefinitely.
- Leave existing published snapshots intact on failure.
- Never relabel a previous week's snapshot as this week's result.
- Keep available historical data visible with a clear explanation when a current recommendation is unavailable.
- Alert on failed or blocked runs and include the run URL, stage, intended week, and safe error summary.
- The later catch-up trigger is deferred. The owner may recover a failed publication manually before kickoff after inspecting whether any snapshot already committed.
- Provide an authorized manual rerun for corrected source availability.
- A missing model is a failure, not permission to append `--train`.

Initially propose an owner check/alert if the expected snapshot is still absent at **10 a.m. Eastern Tuesday**. This is an operational target, not a platform guarantee. A watchdog on the same scheduler can also be delayed; until an independent free monitor is validated, an owner check remains part of operations.

### F8. Download efficiency

The current worker downloads all requested seasons each run. Begin by measuring a full authorized cloud run for correctness, then consider caching immutable historical inputs or fetching only the changing season.

Any optimization must preserve the adapter's expected all-season input contract, checksum provenance, and treatment of source corrections. Do not pass only 2026 data into logic that expects a 2024–2026 history, and do not treat a mutable upstream file as permanently immutable merely because its season ended.

Dependency caches may accelerate installation. Caches are not backups, and a missing cache must never prevent a correct run.

**Phase F exit condition:** a real cloud refresh succeeds with the developer computer off, a repeat run is safe, and deliberately injected failures preserve the last valid data with an observable failure state.

## 12. Model, artifacts, and backups

### 12.1 Frozen model distribution

Approved copy: `backend/artifacts/models/lineup-model-v1.json`. The original ignored local model remains untouched.

Recommended production arrangement:

1. Copy the approved non-secret JSON model into a deliberately tracked directory, such as `backend/artifacts/models/lineup-model-v1.json`.
2. Review its contents before committing; do not include raw personal data or credentials.
3. Add a manifest with checksum, model version, feature version, scoring version, evaluation summary, and source commit/reference.
4. Configure the worker's `MODEL_DIR` to point at that directory.
5. Verify the checksum and versions before every preparation.
6. Exclude the model from the API bundle if serving does not use it.

The path and `.json.sha256` sidecar now exist locally; they are not yet claimed committed or deployed. Committing the JSON to the repository is the simplest distribution option. The repository is public, so the model's coefficients become public. They contain no personal data, but review the file before committing anyway. For the minimal launch, a `.sha256` file is enough; the fuller manifest in step 3 is deferred.

Never retrain on deployment, silently replace the model, or delete the existing file to bypass its overwrite guard. A new model requires a new version and evaluation/release decision.

### 12.2 What must survive the runner

For each successfully published snapshot, preserve enough to reconstruct it:

- Raw source manifest and checksummed Parquet inputs, or a tested deduplicated reference to those exact bytes.
- Lineup supplemental team statistics and play-by-play inputs.
- Source mapping/scoring configuration and relevant code commit.
- Exact prepared lineup inputs and reviewed completion evidence used at the cutoff.
- Frozen model JSON and its checksum.
- Snapshot payload, coverage report, run metadata, and archive manifest.

An upstream URL alone is not a reproducibility archive because upstream files can change. A database snapshot payload alone is not a complete replay bundle either.

### 12.3 Archive destination and encryption

Launch destination: **encrypted GitHub Actions artifacts**, rolling `retention-days: 90`.

Only these files are uploaded:

- `replay.age`: compressed exact raw Parquet inputs and supplemental team/PBP data; source manifests; prepared inputs; reviewed evidence; frozen model; snapshot; coverage/quality reports; mapping/config; dependency specification; and a per-file checksum manifest with code commit/run ID/snapshot ID/season/week.
- `backup.age`: PostgreSQL 17 custom-format dump, validated with `pg_restore --list` before encryption.
- Ciphertext SHA-256 sidecars.

The public repository's downloadable artifacts must not contain plaintext reviewer identifiers, free-text evidence, or DB dumps. Public football statistics do not make all stored metadata public.

Age encryption uses the owner's public recipient only. Partial files do not get the uploaded `.age` extension. Preflight tests tools/recipient/checksum before ingestion, but possession of the private key requires the separate owner recovery test.

Retries reuse existing ciphertext. After upload, the workflow downloads and verifies ciphertext checksums; that does not prove decryption/restoration. A fresh runner cannot recover files that disappeared before upload.

Standard public runner minutes are free. Verify actual artifact storage accounting and no-paid-upgrade settings in the account; do not assume unlimited storage. Review dataset redistribution terms before wider launch.

Private object storage remains deferred. No bucket credentials or extra hosting service are required.

### 12.4 Retention policy

**Minimal launch:** GitHub's 90-day artifact expiry is the retention policy. There is no custom cleanup job. The model stays in Git, and immutable SQL snapshots stay in Supabase. **Deferred:** the finer-grained policy below, which applies once a private archive store is adopted.

Initial target, subject to measured size:

| Item | Retention target |
| --- | --- |
| Approved model versions and checksum manifests | Retain every deployed version |
| Immutable database snapshots and reviewed evidence | Retain; monitor growth rather than deleting around immutability guards |
| Successful raw/replay bundles | At least the latest four weekly bundles initially |
| Database backups | Latest four weekly backups plus the latest pre-migration backup |
| Failed-run diagnostic summaries | 7 days unless needed for an active incident |
| Large failed-run downloads | Remove after diagnosis only when no successful publication references them |
| CI test reports/screenshots | Short retention, initially 3–7 days |

Deduplicate unchanged historical data by checksum where useful, but retain a complete dependency manifest. Deleting a shared historical object still referenced by a retained snapshot destroys replayability.

This four-week raw-archive target is a proposed storage compromise, not indefinite replay retention. Keeping an old immutable SQL result does not guarantee its original raw inputs can still be replayed after the corresponding archive expires. Before enabling cleanup, the owner must accept that boundary or arrange longer-term copies outside the free bucket. Keep model versions, checksums, publication metadata, and reviewed evidence even when an approved raw-data retention window ends.

Before any automated cleanup:

- Calculate projected usage and retain headroom, initially targeting no more than 70% of the actual artifact-store quota.
- List exact candidate objects under this application's archive prefix.
- Check references and backup status.
- Dry-run the deletion plan first.
- Never target an entire bucket, account, repository, or local workspace root.
- Do not shorten retention or delete immutable SQL snapshots silently to stay free; request an explicit product/operations decision.

### 12.5 Database backups

Supabase Free includes **no** backups, so these portable logical backups are the only recovery path. Do not assume paid point-in-time recovery or long retention is included.

Recommended cadence:

- Before a risky schema migration or major data-repair operation.
- After each successful Tuesday refresh.
- Before the initial cloud cutover.

Use a compatible `pg_dump` client (PostgreSQL 17), custom archive format, and `--schema=public` (implemented). Verify nonzero size and archive readability (`pg_restore --list`). Never put credentials in command-line examples, public artifacts, or Git. Pass the connection string through an environment variable from a repository secret.

**Minimal launch:** the encrypted `backup.age` is the portable backup. Reviewed evidence can contain private metadata. GitHub is an independent copy from Supabase, but recovery also requires the owner's separately retained private identity. Never upload plaintext dumps.

Before the initial cloud cutover, also keep the local `pg_dump` used for the migration in Section 7 C4.

### 12.6 Initial owner-key recovery check — required

Recurring timed restore drills remain deferred. One actual cloud download/decrypt/restore using the owner's production identity is required:

1. Generate a native age identity locally using `age-keygen`, outside the repository. Keep the private file and an independent secure copy. Put only the public recipient in GitHub.
2. Download the workflow artifact before expiry and verify ciphertext SHA-256.
3. Decrypt with `age --decrypt -i /secure/path/identity.agekey -o /restricted/temp/database.dump /download/path/backup.age`. These are placeholders, not identities created by this implementation.
4. Use PostgreSQL 17 `pg_restore --list`; drop the ` SCHEMA - public ` entry from the list (Section 7 C4) and restore with `--no-owner --no-privileges --exit-on-error -L list` into a new empty disposable database, never over production.
5. Compare schema revision, key counts, evidence, and snapshot IDs. Reapply the Section 7 C2 SQL and test read/write restrictions.
6. Decrypt `replay.age` in an isolated directory and verify its manifest/member checksums. Replaying old prediction computation is not permission to publish a backdated snapshot.
7. Record results; remove only the exact disposable DB and temporary plaintext created for this check. Keep ciphertext and recovery keys securely.

Weekly backups can lose up to a week of intervening changes. Source re-downloads may not recreate old evidence or original bytes. No recovery-time guarantee is claimed.

Rolling 90 days means roughly 13 weeks, not a full season. If longer replay history is needed, copy artifacts off-platform periodically (for example monthly) before expiry. End-of-season collection cannot recover earlier expired archives.

## 13. Security and abuse protection

### Minimum launch controls

- HTTPS for browser and server-to-server traffic; TLS with server-certificate verification (`verify-full`) for PostgreSQL.
- The API connects as the `SELECT`-only reader role; the owner credential exists only in the GitHub secret and the owner's machine.
- Existing proxy allowlist retained; no arbitrary forwarding destination or admin-job route.
- Both proxy and direct backend enforce the 16 KiB body cap. Backend checks actual bytes before JSON parsing, including missing/misleading Content-Length. Existing roster/slot/schema bounds remain.
- No public ingestion, migration, retraining, or “refresh now” endpoint.
- No SQL/model/DSN details in user-visible errors. The existing `SQLAlchemyError` handler already returns a generic 503.
- No secrets in `NEXT_PUBLIC_*` variables, committed files, or workflow artifacts.

**Deferred:** a server-only backend credential between the two projects, separate migration credentials, statement timeouts, redacted structured logging, and dependency/secret scanning in CI.

### Rate limiting — Deferred

**Minimal launch:** no custom rate limiter. Share the URL with a small personal audience. Vercel Hobby and Supabase Free (with no payment method attached) stop or restrict at their free limits instead of billing, so abuse degrades availability rather than costing money. Confirm this in each dashboard at setup. If traffic abuse appears, add one of the mechanisms below.

The public frontend proxy can be abused regardless of any backend token. Protect both the website's API routes and the backend.

Choose and test a free-compatible mechanism before a wider launch:

1. Prefer available platform-level controls if they enforce the required limits on the actual free account.
2. If unavailable, a small database-backed atomic rate limiter is an option, but it adds writes/compute and must use separately scoped permissions rather than broadening the data-reader role.
3. Do not call an in-memory map a global rate limit: serverless instances do not share memory.
4. Keep an emergency switch to disable optimization while retaining a helpful website response.

Initial tunable targets: 60 read requests and 10 optimization requests per minute per trusted client identity/IP, with normal interactive use verified. Shared networks and search typing can make naive per-IP limits unfair, so measure and adjust. Trust only platform-provided forwarding information, not arbitrary spoofable headers. Minimize retention of identifiers.

If no adequate free control is available, constrain the beta audience and document the exposure rather than promising abuse resistance.

### Current product limitations that must remain visible

- There is no live injury/news feed. An ACT roster status does not establish game-day health or starting status.
- Questionable/injured players may require manual exclusion; deployment does not fix that data limitation.
- Recommendations assume participation and use the configured ESPN preset, not every custom league's scoring.
- No ESPN login, automatic roster import, or submission of a starting lineup to ESPN exists.
- My Team is pregame-only under the current whole-week first-kickoff lockout.
- Legacy Best matchups and My Team have different scoring/model paths.

Provide brief data-source attribution and an accurate privacy/data-retention explanation. Before a wider or commercial release, review the source datasets' actual attribution/redistribution terms; installing an open-source loader does not itself establish all rights to every upstream dataset.

**Security exit condition (minimal launch):** secrets stay server-side, the API role cannot write, existing input bounds hold, and the known availability limitations are accurately disclosed. **Deferred:** unauthorized direct calls are rejected, and rate limits are enforced.

## 14. CI, staging, and release order

### 14.1 CI jobs

**Minimal launch:** run the commands in 14.2 locally before each deploy. A CI workflow with the backend and frontend jobs below is recommended soon after launch because it is free on this public repository. **Deferred:** the integration job.

Create a test workflow, separate from the privileged weekly refresh.

Backend job:

1. Start a disposable PostgreSQL 17 service in the runner.
2. Create separate application and `_test` databases with disposable credentials.
3. Set both `DATABASE_URL` and `TEST_DATABASE_URL` to the intended disposable targets.
4. Install the pinned development dependencies.
5. Apply/check migrations against the disposable database.
6. Run Ruff and the backend tests.
7. Exercise the serverless entrypoint without writable project directories.

The current `backend/tests/conftest.py` requires a separate PostgreSQL database whose name ends in `_test`, and rejects using the application database as the test database. Preserve this protection. Never supply a production DSN to a test job.

Frontend job:

1. Install the pinned package-manager/runtime version.
2. Install dependencies from the existing lockfile without updating it opportunistically.
3. Run frontend unit tests and lint.
4. Run a production Next.js build.
5. Keep network-dependent build behavior explicit; CI must not require production data or secrets to compile.

Integration job:

- Start the API and UI against disposable test fixtures or an isolated staging dataset.
- Test the existing proxy allowlist, request limits, service auth, and status propagation.
- Test environment mismatch and missing-variable failures.
- Add repeatable browser checks for the most important flows currently verified manually in the handoff.

Do not quietly replace real staging validation with fabricated production-looking predictions. Test fixtures belong only in clearly isolated tests.

### 14.2 Commands already available today

Run from `backend/`, with a disposable test database configured:

```bash
venv/bin/pytest -q
venv/bin/ruff check src tests
venv/bin/ruff format --check src tests
venv/bin/alembic current
venv/bin/alembic heads
venv/bin/alembic check
```

Run from `football-forecast-ui/`:

```bash
bun test lib
bun run lint
bun run build
```

CI will normally use the runner's activated environment instead of the local `venv/bin/` paths. Packaging changes may introduce new extras/install commands; update this section when those changes actually exist.

The following existing command is a **database write operation**, not a health check:

```bash
# From backend/, with the intended write credentials and approved model present.
python -m src.jobs.weekly_refresh
```

The explicit season/checksum/coverage safeguards exist. Use `MODEL_DIR=./artifacts/models python -m src.jobs.weekly_refresh --season 2026` only with an authorized write target. GitHub scheduling remains off until ENABLE_WEEKLY_REFRESH is explicitly true.

### 14.3 Deployment policy

**Minimal launch:** use the default Vercel Git integration, where a push to `main` deploys production and other branches create previews. Run the 14.2 checks locally before pushing to `main`. Without staging, only an owner-reviewed trusted backend preview may reuse the production **API reader** DATABASE_URL. Untrusted/fork code receives no production credentials; read-only does not prevent credential disclosure or compute exhaustion. Never give previews the owner credential.

Once staging exists, the recommendation becomes owner-controlled production releases after CI and staging validation.

- Do not assume a preview build or an auto-deploy waits for every GitHub check unless that behavior is configured and verified.
- Keep production autodeployment controlled during schema/configuration changes.
- Use supported free-plan release controls; if a desired branch-protection feature is unavailable, document a manual gate.
- If custom CI deployment is later adopted, pin the Vercel CLI, keep its deployment token server-side, and build with the correct environment.
- Frontend and backend are separate releases. Keep API changes backward-compatible while either project may still run the prior version.
- Do not promote a staging build blindly: environment values captured at build time do not automatically become production values just because its URL is promoted.

### 14.4 Recommended release sequence

**Minimal launch (routine release):** run the local tests; take a `pg_dump` first if the release includes a migration; apply migrations with the owner role; push to `main`; smoke-test the public site. The full sequence below applies once staging exists.

1. Pass local/disposable CI tests.
2. Deploy the candidate backend to staging.
3. Apply staging migrations and verify data compatibility.
4. Deploy the frontend preview connected to that staging backend.
5. Run end-to-end checks and a manual staging refresh.
6. Record the tested commit, schema revision, model checksum, and results.
7. Take a production backup if this is an update rather than an initial empty deployment.
8. Apply backward-compatible production migrations with the migration role.
9. Deploy the production backend with production variables.
10. Verify readiness and safe API responses through authenticated requests.
11. Deploy the production frontend with production variables.
12. Run public-site smoke checks.
13. Enable or confirm the production refresh schedule once the worker version is compatible.
14. Record both deployment IDs and the current recovery point.

Database migration, backend deployment, frontend deployment, and model release are separate operations. Rolling back one does not automatically roll back the others.

## 15. End-to-end acceptance checks

Record each check's environment, commit/deployment, date, result, and any screenshots or logs. The checkboxes below have not yet passed in the cloud. For the minimal launch, the **Player explorer**, **Best matchups**, and **My Team** lists are required. From the other lists, only items that do not depend on a deferred feature are required. Service auth, persistent staging, the run ledger, archive-before-publication, and recurring timed restore drills are deferred. Initial owner-key recovery, coverage checks, and body-limit checks are required.

### Infrastructure and configuration

- [ ] Both Vercel projects are on the intended free plan and use the correct roots.
- [ ] Production backend does not attempt to connect to localhost.
- [ ] No secrets appear in built browser JavaScript, source maps available to users, or error responses.
- [ ] The API starts without writable source directories or local raw/model files.
- [ ] **Deferred:** backend service auth rejects absent and incorrect credentials.
- [ ] Frontend-to-backend access works with any enabled platform deployment protection.
- [ ] API database role cannot insert/update/delete application records.
- [ ] Normal worker writes obey snapshot guards; the privileged owner role could alter/drop protections and must not be described as technically incapable of doing so.
- [ ] Readiness failure produces a controlled unavailable response.
- [ ] Cold-start requests recover with useful loading/retry behavior.
- [ ] Moderate concurrent traffic does not exhaust database connections.
- [ ] Redeploying both projects leaves database content unchanged.

### Player explorer and Best matchups

- [ ] Search returns real players from the intended dataset.
- [ ] Selecting a player displays the correct team/opponent for the selected week.
- [ ] Recent averages and historical actuals remain distinguishable from projections.
- [ ] Missing roster/stat information is not mistaken for an undecided schedule without checking the existing fallback.
- [ ] Best matchups returns the correct actual/preliminary/published mode for the selected week.
- [ ] Position filters and week/season selectors do not mix datasets.
- [ ] A week without a published result does not receive another week's result as an invisible fallback.

### My Team

- [ ] Add a representative roster covering QB, RB, WR, TE, K, and D/ST.
- [ ] Generate a complete default nine-slot lineup.
- [ ] Verify mandatory slots, RB/WR/TE FLEX eligibility, and no duplicate player selections.
- [ ] Verify manual exclusions and slot locks.
- [ ] Verify custom supported slot counts.
- [ ] Verify an incomplete roster produces explicit open slots, not invented replacements.
- [ ] Verify a stale expected snapshot ID requires refresh/retry.
- [ ] Verify request size, duplicate-player, invalid-slot, and unknown-player rejection.
- [ ] Verify the maximum supported roster/slot request remains within runtime limits.
- [ ] Reload and confirm browser-local roster persistence.
- [ ] Verify network errors do not destroy the saved roster/recommendation.
- [ ] Verify server-side first-kickoff lockout, not only a browser-clock simulation.
- [ ] Keep saved pregame recommendations viewable while blocking new recommendations after lockout.
- [ ] Retain the injury/participation warning and manual exclusion controls.

### Weekly processing and data integrity

- [ ] A full cloud run downloads and validates real source data.
- [ ] The configured NFL season remains correct across January and daylight-saving boundaries.
- [ ] Previous-week results and the intended upcoming week are resolved from schedule data.
- [ ] The frozen model checksum is unchanged before and after the run.
- [ ] No training path is invoked by scheduled processing.
- [ ] **Deferred:** automatic completed-period deduplication. For launch, avoid manually rerunning a successful publication.
- [ ] GitHub refreshes serialize. Do not run an independent local publisher concurrently; cross-host coordination remains deferred.
- [ ] A download error, missing model, incompatible version, or coverage failure cannot publish misleading data.
- [ ] A failure after canonical import but before lineup publication is visible as partial progress.
- [ ] Archive failure reports a failed overall run separately from existing publication; upload retry reuses ciphertext without republishing.
- [ ] Inspect DB state after cancellation around commit. A missing job result does not prove publication failed; exact lost archives can be unrecoverable.
- [ ] A run finishing after kickoff cannot create a new pregame recommendation.
- [ ] The website sees the exact newly published snapshot without a frontend rebuild.

### Recovery, cost, and real-device use

- [ ] A database backup restores into a clean isolated database.
- [ ] Archive checksums and model/evidence references survive restore.
- [ ] The owner has an independent encrypted backup and can recover its key.
- [ ] Diagnostic artifact retention fits the Actions allowance.
- [ ] Database, object-store, compute, transfer, and Vercel usage are recorded after the trial run.
- [ ] Spending controls and plan selections are verified, not assumed.
- [ ] Desktop and approximately 390px mobile layouts preserve the existing design without horizontal overflow.
- [ ] The site works on the user's phone over cellular, with the development computer/API/ngrok unavailable.
- [ ] The permanent URL and localStorage transition are explained to the user.

Do not mutate real game schedules or production clocks to test lockout. Use isolated fixtures/staging or existing injected-time tests and verify the deployed code matches the tested revision.

## 16. Monitoring and incident runbooks

### 16.1 Minimum observability

Collect safe, structured information:

- Frontend/backend deployment ID and source commit.
- Request ID, endpoint category, status, and duration.
- Database connection/timeout errors without credentials.
- Refresh run ID, intended season/week, stage, and timestamps.
- Last successful canonical ingestion time.
- Last successful lineup publication time, source-data time, and snapshot ID.
- Model/feature/scoring version identifiers.
- Database/object-store size and remaining relevant quotas.
- Backup timestamp and most recent successful restore drill.

Keep health and freshness separate. An API can return 200 while serving old data. The current readiness endpoint only proves it can execute a database query; it does not prove Tuesday's publication succeeded.

Use built-in provider logs and GitHub workflow notifications first. Test delivery to the owner's actual inbox. Do not introduce a paid monitoring service without approval.

Avoid high-frequency readiness probes that wake the database continuously. Check liveness without a DB query where useful, and perform data-freshness checks at the times when a new snapshot is expected.

### 16.2 Incident: website cannot load football data

1. Confirm which environment and frontend deployment the user opened.
2. Check the frontend error and request ID.
3. Check backend liveness, then readiness sparingly (auth only if later enabled).
4. Check backend URL and deployment protection; a service token matters only if that deferred feature is later implemented.
5. Inspect Vercel quota and Supabase project status: a paused project (inactivity) must be restored from the dashboard.
6. Inspect recent migrations and connection errors.
7. Preserve localStorage and show a retryable unavailable state.
8. Restore a known-good application deployment if a code release caused the issue.

Do not fix this by placing a database password in frontend code or returning fabricated player data.

### 16.3 Incident: Tuesday snapshot missing

1. Find the scheduled workflow run; confirm it exists on the default branch and is enabled.
2. Check ENABLE_WEEKLY_REFRESH, scheduler/default-branch activity, concurrency queue, and job timeout.
3. Inspect workflow step outcomes/summary, ingestion records, and saved snapshots. The local refresh-result.json can disappear with the runner; a persistent refresh ledger is deferred.
4. Confirm NFL season/week and the actual first kickoff.
5. Confirm source data for the previous week is available and adequate.
6. Confirm the approved model exists and its checksum matches.
7. Correct the cause and use the authorized manual trigger before kickoff.
8. If the week already started, retain the unavailable/locked behavior; do not backdate a forecast.

Do not rerun with `--train`, bypass coverage validation, or move the target to an arbitrary later week to turn the workflow green.

### 16.4 Incident: quota nearing exhaustion

1. Identify the specific quota and whether it is shared with unrelated projects.
2. Disable unnecessary preview builds, verbose artifact uploads, and DB-waking probes.
3. Investigate repeated full refreshes, retries, or abusive requests.
4. Apply safe retention only to explicitly identified unneeded artifacts.
5. Preserve backups, models, reviewed evidence, and immutable publications.
6. If needed, temporarily disable expensive public functionality or scheduling and explain the limitation.
7. Ask before changing plans, deleting material history, or spending money.

Do not create multiple accounts/projects to evade provider limits.

### 16.5 Incident: bad published snapshot

1. Stop new recommendations if they would use materially incorrect data.
2. Preserve the bad snapshot and its artifacts for diagnosis.
3. Identify whether the problem is source data, scoring/features, model, or application interpretation.
4. Before kickoff, an authorized corrected snapshot may be prepared with new provenance and the proper versioning.
5. After kickoff, do not create a replacement pretending to be a pregame recommendation.
6. Do not UPDATE/DELETE immutable records or remove database triggers to hide the error.

The current API selects the newest snapshot for a week. There is no general implemented “roll back selected snapshot” control. If a publication-disable/quarantine mechanism is added, it must be explicit, tested, and preserve immutable records. Until then, use a safe unavailable state instead of claiming application rollback undoes data publication.

### 16.6 Incident: leaked credential

1. Revoke/rotate the credential at the provider.
2. Update affected frontend/backend/workflow environment values.
3. Redeploy or rerun only the necessary services.
4. Inspect available access logs and affected permissions.
5. Remove exposed values from artifacts/history using an approved cleanup procedure; deletion alone is not a substitute for revocation.
6. Check whether backup/archive keys or other reused credentials were also affected.

## 17. Launch and rollback

### 17.1 Initial launch sequence

This is the long form of Section 1.1. Where they differ, Section 1.1 governs the first launch.

1. Complete the Section 1.1 code fixes (Steps 1–2).
2. Confirm the user approves creating the free resources and deploying to a public URL.
3. Record account plans and enforce the no-paid-upgrade policy.
4. Restore the local public-schema `pg_dump` into the empty production Supabase database (Section 7 C4), then apply the C2 SQL.
5. Commit the approved model to its tracked path, and add the workflow artifact uploads.
6. Deploy the backend and test readiness.
7. Deploy the frontend connected to that backend.
8. Verify the selected week's actual data state. Do not use an old hardcoded Week 3 example forever.
9. If a fully upcoming week exists and data is adequate, run a controlled production preparation without retraining.
10. If kickoff has already passed, preserve the existing lockout and prepare only the correct future week when appropriate.
11. Enable Tuesday automation. GitHub emails the repository owner about failed workflow runs by default; confirm that this notification setting is on.
12. Perform desktop/mobile/public-network checks.
13. Share the stable frontend URL and explain roster re-entry/localStorage.
14. Retire ngrok only after the cloud site is verified; do not destroy local development services or data.
15. Update this file and `HANDOFF.md` with actual URLs, versions, checks, and remaining caveats.

### 17.2 Application rollback

- Record the previous known-good backend and frontend deployment IDs before each release.
- Roll back/redeploy the affected project using a supported method on the selected plan.
- Verify its environment variables and compatibility with the current database schema.
- Check direct API and frontend-proxied responses; service authentication is deferred.
- Keep schema changes additive where possible so the previous application remains usable.

Rolling back a deployment does not restore database contents, reverse a migration, change the frozen model used by a past snapshot, or restore a browser's localStorage.

### 17.3 Database recovery

- Restore to a new isolated database first and validate it.
- Decide explicitly whether losing writes after the backup is acceptable.
- Preserve the damaged/current database for investigation when practical.
- Switch the backend and worker URLs only after verification.
- Apply any necessary forward migrations and recreate least-privilege permissions.
- Reconcile existing ingestion records, snapshots, workflow summaries, and retained archives before resuming writes. A persistent refresh ledger does not yet exist.

Never automatically downgrade/drop the production database because a frontend deployment failed.

### 17.4 Release record — Deferred

**Minimal launch:** fill in the deployment record table in Section 20 once. After that, Vercel's deployment list and the Git history are enough. Adopt the fuller record below when releases become frequent or several people operate the app.

Record a release as the combination of:

- Frontend deployment and Git commit.
- Backend deployment and Git commit.
- Database migration revision.
- Model checksum/version and scoring/feature versions.
- Latest canonical ingestion and lineup snapshot IDs.
- Archive manifest and backup recovery point.
- Selected provider plans and current usage measurements.

This makes “what is live?” answerable without relying on whichever files happen to be on a laptop.

## 18. Implementation work packages

| Package | September 24 status | Remaining acceptance |
| --- | --- | --- |
| Serverless packaging | Implemented locally: entrypoint, pin, extras, no mkdir | Actual Vercel bundle/startup/latency |
| Frontend config/body limits | Implemented with direct/proxy tests | Cloud URL, role/protection checks |
| Intended week and coverage | Implemented with regression tests | Real Tuesday data and complete cloud run |
| Frozen model | Exact approved copy and checksum; no retraining | Review/commit non-secret artifact |
| Scheduled workflow | Implemented, opt-in disabled | Secrets/recipient; authorized real run |
| Encrypted replay/backup | Tools, manifests, upload retry/download verification implemented; real `age` round trip and public-schema restore rehearsal passed locally | Owner production-key download/decrypt/restore from Supabase |
| Cloud DB/roles | Supabase selected; pooler-safe API engine, schema-limited backup, and worker port guard implemented locally | Provision; empty-target restore; reader write rejection; `anon` has no access |
| CodeRabbit | September 27: 3 findings fixed; re-review recorded in Section 3 | Re-run after future changes |
| CI, staging, ledger, rate limiter | Deferred except local pre-release checks | Add individually when justified |

Next order: local verification/CodeRabbit → deployment approval → Supabase roles/migration → backend/frontend cloud checks → owner-key workflow configuration/manual run → recovery/mobile checks → routine activation.

Before frontend edits follow `football-forecast-ui/AGENTS.md` and installed Next.js docs. Preserve unrelated worktree changes. No backend rewrite, DB replacement, accounts, model changes, or UI redesign are needed.

## 19. Decisions, limitations, and fallback

### Defaults settled by this plan

- Budget: $0 recurring hosting charges, within free allowances.
- Release scope: personal, noncommercial beta; verify that this matches actual intended use before account setup.
- Frontend and API: separate Vercel projects from the same repository.
- Database: Supabase PostgreSQL (plain Postgres; Data API off), not SQLite.
- Scheduled processing: GitHub Actions, not a paid always-running worker.
- URL: included Vercel address initially.
- Current NFL season configuration: 2026 with historical inputs from 2024–2026.
- Refresh target: Tuesday 8 a.m. Eastern (`timezone: America/New_York`), with manual re-runs for failures. The automatic catch-up trigger is deferred until a completed-period guard exists.
- Repository: public, so GitHub Actions standard runners are free. Everything committed is published.
- Scope: the minimal launch path in Section 1.1 first; everything marked Deferred only when justified by real usage.
- Archive/backup: rolling 90-day GitHub artifacts encrypted to the owner's native age recipient.
- Model: distribute the existing approved JSON and never retrain on the routine refresh.
- Team storage: retain browser-local behavior for the first release.
- Injury handling: preserve current warnings/manual exclusions; do not imply a new live feed.

### Decisions/gates still required before launch

| Question | Recommended resolution |
| --- | --- |
| Do the actual account plans permit the intended noncommercial use and repository integration? | Verify in the user's accounts before provisioning |
| Does the API fit Vercel's free Python runtime with acceptable latency? | Answer with Phase B measurements, not assumption |
| Is free private object storage available and adequate? | **Resolved for launch:** use 90-day GitHub Actions artifacts. Revisit only if longer replay history is needed |
| Which free abuse-control mechanism is enforceable? | **Deferred:** limit the audience for the beta and rely on free-plan hard limits; add a mechanism if abuse appears |
| Who receives and acts on failed refresh/backup alerts? | The repository owner, through GitHub's failed-workflow email |
| What coverage prevents publication? | Implemented intended-week, prior-week completion/team scoring/kicker, six-position and kickoff gates; verify with real cloud data |
| How much history fits? | Measure DB growth and compressed artifacts. The previous 38 MB size is not proof that a full season fits |
| Should teams migrate via export/import? | Optional; roster re-entry is the initial default |

The plan is detailed, but these gates intentionally remain evidence-based. An implementation agent must not mark them resolved merely because a free tier is advertised.

### Fallback A — Render Free for the API only

If Vercel cannot reasonably serve this FastAPI application within free limits, preserve the UI and Supabase database, and evaluate Render Free as the API host. Keep GitHub Actions for scheduled work.

Tradeoffs documented by Render:

- Free web services sleep after 15 idle minutes.
- Waking can take about a minute.
- Local filesystem changes are ephemeral.
- Render's free PostgreSQL expires after 30 days, so it is not the database choice for this plan.
- Free service usage has other monthly limits; verify whether adding a payment method permits supplementary billing.

[Render free hosting limitations](https://render.com/docs/free)

This is not a seamless drop-in with the current frontend's 10-second upstream timeout. It would need a tested waking/loading/retry experience and careful outer-function duration handling. Do not use artificial constant pings just to defeat the provider's sleep policy.

### Fallback B — owner-run weekly preparation

If cloud processing cannot run on GitHub Actions (for example, runner memory or a nflverse download block), the website and database could remain hosted while the owner runs the weekly preparation locally and uploads its verified results.

This keeps hosting charges at zero but gives up unattended Tuesday operation. The computer must be available for refreshes, and missed runs become an owner responsibility. Adopt only with explicit user agreement.

### Deferred options

- Railway API/database/worker if a hosting budget becomes available.
- Commercial Vercel plan if the product's use requires it.
- A paid/custom domain, accounts, cross-device team sync, and ESPN integration.
- A more reliable scheduling/monitoring service if exact operational deadlines become important.
- Live injury ingestion and stronger availability rules as a separate product feature.

No fallback should be enacted as an unannounced purchase or material architecture change.

## 20. Launch checklist and deployment record

### Minimal launch checklist

- [ ] User approved the actual deployment, not just this document.
- [ ] Personal/noncommercial scope and account eligibility confirmed.
- [x] New files reviewed for public visibility and committed (`875ca17`, September 27): a secret scan was clean; an IP-bearing ngrok URL was removed from `HANDOFF.md`; `output/` screenshots are ignored.
- [ ] All selected services remain on intended free plans without paid trial dependence or a payment method.
- [x] Locally implemented: no API mkdir, explicit entrypoint, extras, Python pin; cloud packaging remains unverified.
- [x] Locally implemented/tested: missing production BACKEND_URL refuses localhost fallback.
- [x] Local database dumped and restored into Supabase (September 27); all 18 table counts, revision `202609220002`, 4 triggers, and snapshot/batch content hashes match; `alembic check` reports no drift.
- [x] API uses `api_reader` through the transaction pooler (tested locally against the cloud DB, September 27): health, readiness, search, and rankings return 200; INSERT/DELETE/CREATE are rejected; `anon`/`authenticated`/`service_role` have no table privileges; Data API disabled. Repeat from the deployed Vercel function.
- [x] Backend deployed on Vercel (`football-forecast-api`): health, readiness (DB connected via `verify-full`), search, rankings, and lineup week return 200 in about 0.2 s; an oversized POST returns 413.
- [x] Frontend deployed (`football-forecast`) with production `BACKEND_URL`. Player explorer, Best matchups (Week 2: 100 WR results), and My team (correct started-week lock) work in a desktop browser. The proxy returns 404 for non-allowlisted paths and 413 for oversize bodies.
- [x] Supabase CA certificate committed as `backend/certs/supabase-ca.crt`; SSL enforcement on; `verify-full` works from the owner machine, the Vercel function, and the GitHub runner; a wrong CA is rejected.
- [x] Model copy and checksum committed.
- [x] Explicit season, intended-week/coverage gates, direct backend body limit implemented locally.
- [x] Local PG17 dump → empty-database restore rehearsal passed; counts, revision, triggers, and snapshot identity matched (full dump September 24; Supabase-style public-schema dump September 27).
- [x] `age` installed locally and the real encryption round-trip test passes (September 27).
- [x] CodeRabbit CLI review completed and its findings resolved (September 27).
- [ ] Opt-in workflow passes a cloud run; encrypted archives download/verify ✔ (run 36350171349); site shows exact snapshot (pending the first Tuesday publication).
- [ ] Owner identity retained independently (**second copy still pending**; only `~/football-backup.agekey` exists). One cloud backup decrypted and restored successfully ✔ (September 27).
- [x] Tuesday workflow explicitly enabled by the owner (`ENABLE_WEEKLY_REFRESH=true`, September 27); first scheduled run Tuesday, September 29, 8:00 a.m. Eastern. Failure notifications still to be confirmed.
- [ ] Participation/injury notice still visible.
- [ ] Real phone/cellular check passed with local development services unavailable.
- [ ] Owner received the stable URL and understands browser-local team storage.
- [ ] Deployment record below and `HANDOFF.md` updated.

### Deferred hardening checklist

Adopt individually when justified; none of these blocks the minimal launch.

- [ ] Staging environment with isolated credentials.
- [ ] Backend service authentication and rate limiting.
- [ ] Separate refresh-writer, migration, and backup roles.
- [ ] Refresh ledger, full-run guard, and idempotent retry behavior.
- [ ] Catch-up schedule trigger (requires the full-run guard).
- [ ] Archive-before-publication behavior.
- [ ] Private object storage for replay history beyond 90 days.
- [ ] Longer off-platform retention if desired; encryption and initial owner-key recovery are already required.
- [ ] Recurring timed restore drills; the initial owner-key recovery check is required.
- [ ] CI workflow and integration tests.
- [ ] Full release records.

### Actual deployment record — fill in after verification

| Field | Value |
| --- | --- |
| Deployment status | **Deployed September 27, 2026** (database, API, website). Weekly workflow enabled September 27 |
| Owner / alert recipient | To be confirmed; no credentials here |
| Frontend project and public URL | `football-forecast` (`prj_auSkLUoNY0kQkRoPsXzaQyRYGxX6`), root `football-forecast-ui`: <https://football-forecast-xi.vercel.app> |
| Frontend deployment ID / commit | `dpl_7581M8LfP7TgE95Uvwia2rfbHYWu` / `875ca17`; Git integration deploys `main` |
| Backend project and stable URL | `football-forecast-api` (`prj_CVQRmgavQ5cFdkIlWBzKfwQ89a7w`), root `backend`: <https://football-forecast-api.vercel.app> |
| Backend deployment ID / commit | `dpl_HhLXGavE6R1dXRnSdnEU59ReUEFs` / `875ca17`; Git integration deploys `main` |
| Vercel plan and region | Hobby (team `kirollos-besadas-projects`), default function region |
| Supabase project ref / PostgreSQL version / region | `pinpqyoqfgxxezigfagr` (`football-forecast`, KBesada24 org) / PostgreSQL 17.6 / `us-east-1`. Session pooler `aws-0-us-east-1.pooler.supabase.com:5432`; transaction pooler port 6543 |
| Supabase plan and observed quotas | Free (created via CLI in the owner's org). Owner to confirm in Billing that no payment method or Pro trial is attached |
| Production schema revision | `202609220002` (head), restored from the local dump; `alembic check` clean |
| Model version / SHA-256 | Record approved artifact at deployment |
| Latest verified source-data timestamp | Record at deployment |
| Latest lineup snapshot / target season-week | Record at deployment |
| Refresh workflow URL / last successful run | Two manual runs on September 27, a Sunday mid-Week 3. Run 36349966327 exposed a real backup bug: libpq ignores a URI in `PGDATABASE`, fixed in `5d9e440`. Run 36350171349: preflight ✔, backup ✔, upload ✔, download and checksum ✔. Ingestion was correctly blocked by the completed-game coverage gate: nflverse had Sunday final scores but only Thursday's player stats. No publication yet; the first real one is a Tuesday run |
| Archive destination and verified retention | Encrypted GitHub artifacts selected; rolling 90 days configured, cloud unverified |
| Last encrypted backup / independent copy | Artifact `football-refresh-36350171349-1` (1.5 MB, expires December 26, 2026); decrypted successfully with the owner identity |
| Last restore drill / measured recovery time | **Cloud owner-key recovery check passed September 27.** Artifact downloaded, ciphertext checksum verified, decrypted with `~/football-backup.agekey`, and restored (exit 0) into an empty scratch database. All 18 table counts, revision `202609220002`, 4 triggers, and content hashes of 10 tables were identical to live Supabase; the append-only guard held. Compare hashes with `COLLATE "C"`, because musl and glibc `en_US` sort differently. Recovery took a few minutes end to end. Scratch DB and plaintext removed |
| Spending controls verified on | Not verified in cloud accounts |
| Remaining limitations accepted by owner | Record before launch |

### Next action

The app is live (September 27): database, API, and website are deployed and verified. The Supabase database has SSL enforcement on, the Data API off, a read-only `api_reader` (pre-hashed SCRAM password), and Supabase API-role grants revoked. GitHub has `REFRESH_DATABASE_URL` (secret) and `BACKUP_AGE_RECIPIENT` (variable); `ENABLE_WEEKLY_REFRESH` is unset. Database passwords live in `~/.config/football-forecast/supabase.env` (mode 600, outside the repo) until the owner moves them to a password manager.

Remaining owner steps: keep a second copy of `~/football-backup.agekey` off this machine, confirm Supabase billing is Free, run a phone/cellular check, then set `ENABLE_WEEKLY_REFRESH=true`. The owner-key recovery check passed September 27. **Timing risk:** nflverse publishes player stats with a lag. If Monday-night stats are not out by Tuesday 8 a.m. Eastern, the coverage gate blocks that run safely (failure email, nothing published); rerun manually later Tuesday with `gh workflow run weekly-refresh.yml -f season=2026`. Move the cron later if this recurs.

Maintain this document as the operational source of truth: change “planned” to “implemented” only when the code/configuration exists, and change “verified” only after the corresponding check has actually run.
