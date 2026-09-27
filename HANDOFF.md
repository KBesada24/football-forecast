# Football Forecast — agent handoff

Last updated: September 23, 2026 (America/New_York).

## Read this first

The application is a working local development preview, not a production deployment. The latest work adds a **complete ESPN full-PPR My Team lineup optimizer**, alongside the existing Player explorer and Best matchups screens.

The user interrupted implementation to request this handoff, then asked to continue end-to-end checks. The implementation exists, real Week 3 projections have been prepared, and the services are running. **Do not interpret this document as a claim that every production concern is finished.** See verification and remaining work below.

The repository has extensive pre-existing uncommitted/untracked work. No commit was made. Preserve all of it. In particular, most of `backend/src`, tests, and frontend components are untracked; that does not mean they are disposable.

Workspace: `/home/kbesada/Code/football-forecast`.

## 1. User decisions and product intent

- Keep the existing restrained cream/off-white and deep-green UI. The user likes it.
- Use PostgreSQL locally and in production, not SQLite. Local PostgreSQL runs in a container; Supabase is the user's likely production preference, but no Supabase deployment was done.
- Use real NFL data for 2024, 2025, and 2026. Never insert mock predictions into the real dataset to fill an empty screen.
- The original Best matchups screen is a league-wide positional ranking. The user clarified that their desired next feature is entering their own fantasy roster and receiving the best starting lineup.
- Optimize **highest expected total fantasy points**, subject to actual starting slots. No separate safe/upside modes yet.
- Default complete lineup: QB, RB, RB, WR, WR, TE, FLEX, K, D/ST. FLEX allows RB/WR/TE, never QB. Supported starting-slot counts are configurable; no Superflex or IDP.
- ESPN full-PPR preset. The user also uses Yahoo but selected ESPN for this implementation. This does not mean all ESPN custom leagues have identical settings.
- Player history: last **five eligible appearances**, not five calendar weeks; can cross season boundaries. Exclude reported DNF/DNP games, including a player who started but left injured. Actual zero-point appearances count. Unknown completion counts unless reviewed evidence says otherwise.
- Include workload, defense strength against the player's **position**, and previous meetings with that opponent. Small/missing samples must be explicit. No automatic arbitrary head-to-head bonus.
- Strong opposing WR defense can make an RB a better FLEX, but cannot replace a mandatory WR slot with an RB.
- Refresh Tuesday at **8 a.m. Eastern**: ingest previous week's completed games and prepare the next week's matchups/projections. **Do not retrain every Tuesday.** Reuse the approved model with new inputs.
- Availability is conditional: there is no reliable automated injury/news ingestion here. Latest ACT roster status is not proof that someone will play. Manual exclusions and clear warnings are necessary.
- Pregame optimizer only: once any game in the selected week starts, no new recommendations. Previously saved recommendations remain viewable.
- Manual roster entry and browser-local persistence first. No accounts, ESPN authentication, league import, or automatic submission to ESPN.
- The earlier off-topic usage/statusline request was abandoned. No statusline configuration was changed.

## 2. Runtime and access

### Current services

These user-level services were active when checked during this handoff:

| Service | What it runs |
| --- | --- |
| `football-forecast-api` | Uvicorn, `src.main:app`, `127.0.0.1:8000` |
| `football-forecast-ui` | Next production server, `127.0.0.1:3000` |
| `football-forecast-tunnel` | ngrok forwarding to port 3000 |

Existing API/UI/tunnel units are transient user services, not a fully managed production installation. Do not assume they survive a reboot.

Local UI: <http://127.0.0.1:3000>

Last verified public URL: a temporary ngrok address (not recorded here; ngrok's free hostnames embed the host's IP address).

The ngrok URL may change. `ngrok-skip-browser-warning: 1` bypasses the interstitial for HTTP smoke tests. Browser localStorage is per origin: a new ngrok hostname does not inherit the old roster.

Database: rootless Podman PostgreSQL 17 container `football-forecast_postgres_1`, loopback port 5432. Development DB is `football_forecast`; tests use a separate `football_forecast_test`. Connection settings live in ignored `.env` files. **Do not copy secrets into this document or logs.**

Backend Python venv: `backend/venv`, Python 3.14.7. Backend dependencies are pinned in `backend/pyproject.toml`; key libraries are FastAPI, SQLAlchemy, Alembic, psycopg, nflreadpy 0.1.5, and Polars. Frontend uses Next 16.3.4, React 19.2.8, Bun 1.3.6. No new numerical ML library was installed; the small ridge model is implemented in Python.

### Common checks

From the repo root:

```bash
systemctl --user is-active football-forecast-api football-forecast-ui football-forecast-tunnel
curl -fsS 'http://127.0.0.1:3000/api/football/lineups/week?season=2026&week=3'
```

From `backend/`:

```bash
venv/bin/pytest -q
venv/bin/ruff check src tests
venv/bin/ruff format --check src tests
venv/bin/alembic current
venv/bin/alembic check
```

From `football-forecast-ui/`:

```bash
bun test lib
bun run lint
bun run build
```

After backend edits, restart `football-forecast-api`. After frontend edits, run the production build and restart `football-forecast-ui`. It is running `next start`, not a hot-reloading development server.

## 3. Overall architecture

```text
nflreadpy / nflverse
    │ offline download, checksum, preserve raw inputs
    ├── legacy canonical ingestion → PostgreSQL players/games/stats/rosters/evidence
    │                                ├── Player explorer
    │                                └── Best matchups / ranking previews
    │
    └── lineup supplements (team stats + play-by-play)
         → ESPN scoring + full-position appearance history
         → five-game / workload / positional defense / head-to-head features
         → frozen per-position model, evaluated offline
         → append-only PostgreSQL lineup_snapshots + local reproducibility artifacts
              → GET /lineups/week: prepared catalog/projections
              → POST /lineups/optimize: exact slot assignment over user's roster
                   → Next allowlisted proxy → My Team UI
                                              └── roster/preferences/results in localStorage
```

Network downloads, model training, and projection inference do **not** run on the API request path. The optimization endpoint only selects a lineup from saved numbers. It does not store the user's roster in PostgreSQL.

The API's database dependency uses a repeatable-read, read-only transaction. Offline jobs have their own write transactions. The API reads prepared data; writes happen in operator jobs.

## 4. Existing application before the My Team addition

The earlier implementation established:

- Containerized PostgreSQL, migrations, settings, FastAPI, health/data endpoints, source schema mapping and auditing, checksummed/replayable ingestion.
- Canonical player identities, weekly roster team context, schedules, RB/WR/TE stat records, snap-based participation, and reviewed completion evidence.
- Player history and selected-week actual results; an unpublished forecast is not fabricated. The large player hero uses meaningful historical context when there is no published forecast, clearly labeled as historical rather than predictive.
- Matchup resolution using the latest same-season roster/stat context no later than the selected week. Future weekly rosters are often absent; this is not the same as an undecided schedule. The earlier Jefferson “Awaiting roster” problem was addressed with this fallback and its context-week caveat.
- Best matchups has actual-results, preliminary, and published modes. Past/started weeks show actual results; upcoming weeks can read offline preliminary ranking previews.
- Existing preliminary rankings combine within-position percentiles of a trailing-four baseline and opponent favorability, 50/50. They are **not** the new My Team optimizer and have not been silently replaced with its model.
- Legacy strict forecast publication is separate from refreshable preliminary rankings. Strict publication has coverage gates and immutable publication records. Earlier work had no real strict forecast publications; the new lineup snapshots are a separate system, not a claim those strict gates were passed.

Relevant files: `src/api/player_service.py`, `src/api/ranking_service.py`, `src/features/player_history.py`, `src/features/matchup_ranking.py`, `src/jobs/generate_forecasts.py`, `src/jobs/prepare_rankings.py`, and the player/rankings frontend components.

Existing planning/status documents in `docs/` and `MRD.md` predate portions of this feature. Where they differ, inspect current code and the explicit decisions above. Do not assume a previously discussed model or integration was built merely because it appears in a plan.

## 5. New backend files and changes

### `backend/src/domain/espn.py`

New scoring version: `espn_full_ppr_2026_v1`.

The old `src/domain/scoring.py` / `full_ppr_v1` remains unchanged. It omitted two-point conversions and return TDs and must not be relabeled as the full ESPN preset.

New player scoring includes:

- Passing yards × .04, passing TD × 4, passing INT × −2.
- Rushing/receiving yards × .1, rushing/receiving TD × 6, reception × 1.
- Passing/rushing/receiving two-point conversions × 2.
- Kick/punt return TDs and fumble-recovery TDs × 6; total fumbles lost × −2.
- Kicking: made FGs under 40 yards = 3, 40–49 = 4, 50–59 = 5, 60+ = 6; PAT made = 1. Missed/blocked FG attempts cost 1, implemented as attempts minus makes because nflverse separates blocked outcomes.

D/ST scoring includes sacks, interceptions, recovered fumbles, blocked kicks, safeties, TDs, conversion returns, PAT safeties, plus ESPN points-allowed and yards-allowed tiers. Missing/nonfinite required numeric fields raise instead of becoming zero. Tier boundary tests cover the scoring transitions.

Primary references consulted:

- <https://support.espn.com/hc/en-us/articles/360003914032-Scoring-Formats>
- <https://support.espn.com/hc/en-us/articles/115003847231-Defense-and-Special-Teams-D-ST-Scoring>
- ESPN Chicago championship official rules, Appendix A, for the yardage-tier values: <https://goodkarmabrands.com/images/2025-Advantage-Acura-ESPN-Chicago-Fantasy-Football-Championship-Draft-Contest-Rules-v4.pdf>
- nflverse team-stat dictionary: <https://raw.githubusercontent.com/nflverse/nflreadr/main/data-raw/dictionary_team_stats.json>

The ESPN PDF appendix was rendered and visually inspected locally. This is a preset, not configurable arbitrary league scoring.

### `backend/src/data/lineup_data.py`

- Keeps the existing five-file raw snapshot contract intact.
- Adds a separate `lineup-manifest.json` and checksummed `lineup-team_stats.parquet` / `lineup-pbp.parquet` supplements.
- Reads all QB/RB/WR/TE/K appearances from raw player stats, independently of the legacy RB/WR/TE scoring table.
- Uses existing schedule normalization and completed-game status.
- Checks player team/opponent against the schedule and rejects duplicate player/game rows.
- Adds holes when snap participation exists but scoring data does not. A missing stat row is **not** assumed to be a zero-point game.
- Constructs `DST:<team>` entities and historical D/ST scores.
- PBP disambiguates defensive versus offensive TDs, special-teams TDs, recovered fumbles, safeties, and conversion exceptions. PBP final scores must agree with the schedule.
- Opponent defensive TDs are removed from D/ST points allowed; special-teams points and PATs still count. Yards allowed use net passing plus rushing, subtracting the magnitude of sack yardage.
- Reports missing player-game scoring and missing D/ST games.

Important: these are newly implemented adapters. Tests cover core edge cases, but a comprehensive independent reconciliation of every historical ESPN fantasy score has **not** been performed. Rare double-fumble/return/conversion events deserve further audit before making a production “exact match to ESPN in all cases” claim.

### `backend/src/features/lineup_features.py`

Feature version: `lineup_history5_matchup_v1`.

`FeatureIndex` indexes appearances and opposing position/game totals. Target inputs must be strictly before the selected season/week and cutoff.

Player history:

1. Remove reviewed DNF/DNP appearances known by the cutoff.
2. Select the newest five remaining appearances across seasons.
3. A scoring hole inside those five makes the projection unavailable; a hole outside the current five does not invalidate it.
4. Preserve real zeros. Fewer than five appearances is limited history, not fabricated data.
5. Calculate mean five, linearly recency-weighted five, broader eight-game mean, and average targets/carries/pass attempts.

Opponent features:

- Head-to-head meetings since the loaded history begins in 2024; show raw average/count. The model input weights recent seasons more and shrinks the residual toward zero for small samples.
- Defense is **position totals per game**, not average fantasy points per recorded player.
- Use up to eight opposing games, an extra weight for the recent five, and an eight-observation league prior. League context uses up to 256 latest valid positional game totals.
- Exclude defensive game samples with known scoring holes. Missing defense is neutral rather than excluding an otherwise projectable player.
- Actual opponent outcomes include DNF performances: they describe what the defense allowed, while DNF exclusion applies to a player's personal history.

The nine model inputs are five-game mean, weighted-five deviation, eight-game deviation, targets, carries, pass attempts, positional opponent relative strength × player mean, shrunk head-to-head residual, and history sample size.

### `backend/src/models/lineup_model.py`

Model version: `lineup_ridge_v1`. A small standardized ridge regression learns a residual over the five-game average. Coefficients are frozen JSON, not a serialized executable model.

Chronological experiment:

- Training: 2024.
- Validation/tuning: 2025 weeks 1–9.
- Untouched holdout: 2025 weeks 10–18.
- Try ridge penalties 10, 100, 1000 using validation MAE.
- Fit the selected challenger on training + validation, then evaluate once on holdout.
- Require lower holdout MAE and no worse pairwise decision regret than **both** mean-five and weighted-five baselines to promote each position.
- Otherwise use the baseline chosen on validation.
- Do not refit after inspecting the holdout. No 2026 outcomes trained or selected the model.
- Actual target-game DNF outcomes remain in evaluation.

Pairwise regret compares weekly candidate start/sit pairs in a fixed top-36 baseline-selected pool per position. It is a useful proxy, **not a simulation of users' actual fantasy rosters or a full cross-position FLEX backtest**.

This is explicitly a **corrected-data chronological simulation**, not historical archived pregame predictions. Coverage excludes missing recent history. No numerical confidence intervals or invented playing probabilities are presented.

Observed holdout results:

| Position | Deployed | Challenger MAE | Mean-five MAE | Promoted |
| --- | --- | --- | --- | --- |
| QB | ridge | 6.9246 | 7.1856 | yes |
| RB | ridge | 4.7329 | 4.8596 | yes |
| WR | mean5 | 4.7822 | 4.7169 | no |
| TE | ridge | 4.6157 | 4.6628 | yes |
| K | ridge | 3.9578 | 4.2796 | yes |
| D/ST | ridge | 4.6753 | 5.1788 | yes |

Full counts, weighted baseline comparisons, regrets and accuracy are in the model JSON and snapshot payload. Do not tune repeatedly on this same holdout.

### Database changes

- Added `LineupSnapshot` in `src/db/models.py`.
- Migration `202609220002_lineup_snapshots.py`, following `202609220001` ranking previews.
- `lineup_snapshots` stores ID, season, week, generation time and JSONB payload.
- A database trigger rejects UPDATE/DELETE; snapshots are append-only.
- A new preparation creates a new snapshot. API reads the newest one for the week.
- The migration was applied to development and test databases; `alembic check` found no schema drift.

### `backend/src/jobs/prepare_lineups.py`

- Downloads or replays raw inputs, loads supplements, reads reviewed completion evidence.
- `--train` is explicit, one-time initialization. It refuses to overwrite an existing model artifact.
- Default refresh loads the frozen model and checks scoring/feature versions.
- Chooses the next fully upcoming week, or an explicit `--week`.
- Chooses latest same-season roster rows no later than target week. Conflicting team assignments are unavailable; absent upcoming schedule means bye/no game; non-ACT individual statuses are unavailable.
- Adds all scheduled NFL team defenses.
- Produces conditional projections plus explanations, sample sizes, timestamps, provenance, model report and warnings.
- Saves exact inputs, completion evidence, model and snapshot JSON under `data/lineups/<snapshot_id>/`.
- Uses a PostgreSQL advisory lock for snapshot insertion and rechecks first kickoff before saving.
- Does not mutate the legacy publication system.

### `backend/src/domain/lineup.py`

Pydantic request validation accepts 1–30 distinct roster IDs, 1–12 supported starting slots, exclusions, slot-index locks, season/week, and optional expected snapshot ID.

The exact optimizer uses dynamic programming over occupied starting slots, approximately `O(roster × slots × 2^slots)`. Each player is processed once and cannot fill multiple slots. It maximizes filled slots first, then expected total points; negative projections remain eligible if a required slot needs them. Locks reserve that player for that specific eligible slot. Unavailable/excluded players cannot be selected.

Returns starters, total, completeness, missing slots, bench reasons, and point gaps to eligible unlocked starters. Gaps within two points get a qualitative “close call” label in the UI, not a statistical confidence statement.

### API and proxy

`backend/src/api/routers/lineups.py`:

- `GET /api/v1/lineups/week?season=2026&week=3`: catalog, prepared projections, metadata, default slots, and `ready`, `locked`, or `unavailable` status.
- `POST /api/v1/lineups/optimize`: selects the lineup from prepared numbers. Rejects unavailable snapshots, stale expected snapshot IDs, started weeks, unknown/duplicate/ineligible roster input and invalid locks.
- Both paths use the read-only database dependency. Neither runs source loaders or projection models.

`src/main.py` registers the router and permits GET/POST in CORS.

Frontend `app/api/football/[...path]/route.ts`:

- GET allowlist now includes `lineups/week`.
- POST is allowed only for `lineups/optimize`.
- JSON content type and a streaming 16 KiB request-body bound.
- Controlled error messages; no arbitrary backend proxy destinations.
- `lib/backend.ts` supports this optional POST body, retains no-store, timeout, and redirect rejection.

### Canonical roster adjustment

`backend/src/data/source_adapter.py` now includes QB/K in canonical roster/player identity ingestion, while legacy stat scoring stays RB/WR/TE. This allows reviewed completion evidence to reference QB/K players without silently changing legacy scoring semantics. The fresh raw snapshot was reimported after this adjustment.

## 6. Frontend changes

- `components/forecast-app.tsx`: added My team tab and retains existing tabs/design. My Team is keyed by season/week to isolate state while switching weeks.
- `components/my-team.tsx`: roster search and position filters; 30-player limit; individual remove/sit-out/slot-lock controls; configurable starter counts; recommendation action; complete/partial lineup; bench alternatives; model explanations; stale-result and kickoff-lock messaging; storage/network error states.
- `lib/lineup.ts`: TypeScript contracts, slot eligibility, default slots, storage parsing/validation, and a recommendation fingerprint.
- `lib/lineup.test.ts`: default slots, eligibility, saved draft validation, malformed result handling, fingerprint changes.
- `app/globals.css`: scoped My Team styles, desktop two-column workspace, mobile stacked layout, reduced-motion support and visible focus affordances.

Browser storage keys:

```text
football-forecast:roster:v1
football-forecast:week:v1:<season>:<week>
football-forecast:week:v1:<season>:<week>:result
```

Global roster storage holds minimal member identity and slot configuration. Weekly storage holds exclusions/locks; result storage preserves the pregame recommendation. The fingerprint detects roster/settings changes. Snapshot ID detects a changed weekly dataset. Stale results are labeled, not silently treated as newly computed.

My Team uses its own full-position catalog; the original Player explorer search remains RB/WR/TE. Current D/ST names are abbreviations such as `MIN D/ST`. Full nickname/city search is not implemented yet.

## 7. Real data and generated artifacts

Latest raw source used for My Team:

```text
backend/data/raw/4c224da941e648828aa4cd2015104e3e/
```

This includes the original five datasets plus lineup supplements. Base retrieval timestamp: `2026-09-23T02:42:31.412325+00:00` (September 22 evening Eastern).

Frozen model:

```text
backend/models/lineup-model-v1.json
```

Prepared 2026 Week 3 snapshot:

```text
a7dde5ff025d4086b487a2f4bbcfa7a7
backend/data/lineups/a7dde5ff025d4086b487a2f4bbcfa7a7/
```

First kickoff in that snapshot: `2026-09-25T00:15:00+00:00`, Thursday September 24 at 8:15 p.m. Eastern. The API will stop recomputing this week at that time, even if the process keeps running.

Catalog: 1,000 entities. Non-null projections: 61 QB, 89 RB, 133 WR, 50 TE, 32 K, 32 D/ST. Do not confuse catalog size with projectable players or confirmed starters.

Input audit: 14,919 scored player/team-game rows; 1,995 missing player-game scoring appearances; no missing D/ST games. These holes are retained and can block individual five-game histories.

Canonical reimport after adding QB/K identities: 11,213 legacy stat rows, 816 scheduled regular-season games, 1,525 players, 31,205 weekly roster rows, 13,002 participation rows. All 191 legacy PPR differences were explained; no unexplained differences were reported.

`backend/data/` and `backend/models/` are ignored. A source-only checkout will not contain the trained artifact, raw snapshots or prepared database rows. Plan artifact preservation/deployment explicitly; do not assume cloning the repo is sufficient.

## 8. Refresh workflow and its installation status

Added:

- `backend/src/jobs/weekly_refresh.py`
- `backend/deploy/football-forecast-refresh.service`
- `backend/deploy/football-forecast-refresh.timer`

The job imports fresh source data through the existing ingestion pipeline, then prepares lineup projections from that same raw snapshot using the frozen model. It does not train. Existing ingestion also refreshes legacy ranking previews.

The timer declares `Tue *-*-* 08:00:00 America/New_York` with `Persistent=true`. The service uses the current workstation's absolute path and a 30-minute timeout.

**The timer/service files exist but were NOT installed or enabled.** `systemctl --user status football-forecast-refresh.timer` returned “Unit ... could not be found” during this handoff. Earlier commentary about adding the Tuesday job referred to code, not an active schedule. Do not claim automated Tuesday refresh is operational yet.

To run a refresh manually, from `backend/`:

```bash
venv/bin/python -m src.jobs.weekly_refresh
```

To prepare again from the saved data without retraining:

```bash
venv/bin/python -m src.jobs.prepare_lineups \
  --snapshot data/raw/4c224da941e648828aa4cd2015104e3e \
  --season 2026 --week 3
```

This creates another append-only snapshot and is a write operation. Do not run it merely to inspect state. After Week 3 starts, choose a fully upcoming week instead.

The initial `--train` run already happened. Do not delete the existing model to bypass its overwrite guard. Changes to features/scoring or model-selection logic require a versioned experiment and an honest evaluation plan.

## 9. Verification

### Automated checks re-run September 23

- Backend: **121 tests passed**.
- Backend Ruff: passed.
- Alembic drift check: “No new upgrade operations detected.”
- Frontend Bun tests: **11 passed**.
- Frontend ESLint: passed.
- Production Next build passed during implementation, and the rebuilt UI service was restarted.
- Two backend test warnings remain: Starlette/FastAPI deprecation notices about httpx TestClient / AnyIO BlockingPortal. They are not test failures.

New backend tests in `tests/test_lineup.py` and `tests/test_lineup_api.py` cover ESPN scoring/tier boundaries, kicker misses, D/ST pick-six treatment, exact optimizer against brute force, FLEX, locks, exclusions, incomplete rosters, duplicate/invalid inputs, recent-five holes/zero/cross-season/target leakage, DNF evidence, positional totals, frozen ridge inference, API request-path isolation, immutable snapshots, stale snapshots and kickoff lockout.

### Browser/HTTP checks

Used the Playwright CLI skill with an isolated browser session named `lineup`. This test roster is in the automation browser only, not the user's actual ESPN roster.

Verified against real running services:

- Local Next proxy returns Week 3 `ready`, correct snapshot ID and 1,000 catalog entities.
- Public ngrok GET returns the same real catalog.
- Added a 13-player sample roster through the UI across all six position groups.
- Generated a complete 9-slot lineup, 176.7 displayed projected points for that particular sample roster.
- Reloaded the page and confirmed the recommendation text was unchanged.
- Locked Trevor Lawrence into QB and manually excluded Brock Purdy; the recomputed result respected both.
- Removed the sample kicker and recomputed; UI showed an open K slot, partial total and incomplete-lineup heading.
- Desktop 1440px screenshot inspected; no horizontal overflow.

Browser checks continued after this initial handoff draft; see the final verification addendum below for the latest outcomes. A locator mistake when attempting to open the starting-slots disclosure caused automation timeouts; this was a test locator issue, not evidence of a product failure. Use `page.locator("summary").filter({hasText:"Starting slots"})` to target the disclosure precisely.

Artifacts are in `output/playwright/`. Do not confuse earlier screenshot files of the old rankings screen with this new feature. Browser snapshots under `.playwright-cli/` are ignored scratch artifacts.

## 10. Remaining work / caveats for the next agent

1. Finish any verification still marked pending in the addendum, then update this document. Do not claim tests were run if only code paths were read.
2. Install/enable the Tuesday refresh timer if continuing the approved build. Validate the calendar, paths, DB availability, failure logging and user-session/linger behavior. It currently exists only as source files.
3. Add full team names/aliases to D/ST search. `nflreadpy.load_teams()` was inspected and provides `team_abbr`, `team_name`, `team_nick`; no integration was made. Preserve/checksum that input if adding it to preparation.
4. There is no automatic injury/news feed, no starting-role/depth-chart certainty, and no per-player playing probability. Projections include some backup QBs with historical stats; they are conditional estimates, not assurances of starting status.
5. Expand scoring reconciliation for rare PBP events before claiming exact ESPN parity for all seasons. Current tests are meaningful but not comprehensive source reconciliation.
6. Improve operational reporting for a failed weekly refresh or stale sources. Missing previous-week data is reported at appearance/context level but preparation does not enforce the strict publication pipeline's global completeness gate.
7. Consider a genuine roster-level/cross-position lineup backtest and feature ablations. The current promotion gate is per-position and uses a pairwise start/sit proxy.
8. Existing Best matchups and Player explorer retain legacy scoring/baselines. My Team has its own ESPN profile. A future unification needs deliberate versioning and product copy, not silent renaming of old outputs.
9. Review storage behavior across tabs and corrupted storage. Inputs/results have validation and storage errors are caught, but no cross-tab synchronization/export/import exists. A changed ngrok domain uses different storage.
10. Long rosters make the mobile editor tall before the recommendation. A jump-to-lineup/sticky action could improve usability without changing the visual design.
11. The public endpoint is a development preview without authentication or production-grade rate limiting/abuse protection. Requests are bounded and read-only, but internet exposure is not equivalent to production hardening.
12. No Supabase/Railway/Neon deployment, ESPN account integration, custom scoring configuration, or automatic ESPN lineup submission has been implemented.

## 11. Working instructions for the next agent

- Read `football-forecast-ui/AGENTS.md` before frontend edits. It requires reading relevant docs in the installed `node_modules/next/dist/docs/` rather than assuming older Next APIs.
- Use `apply_patch` for source/document changes and preserve unrelated dirty files. Never reset this worktree to “clean it up.”
- Keep secrets in existing ignored environment files.
- Do not add fake actuals, injury statuses, predictions or made-up confidence intervals to fix visual emptiness.
- Preserve immutable snapshots. A correction is a new version/snapshot, not UPDATE/DELETE.
- No retraining or external data fetches in HTTP handlers.
- Continue concise progress updates to the user while doing longer work.
- Browser test wrapper: `bash /home/kbesada/.codex/skills/playwright/scripts/playwright_cli.sh -s=lineup ...`. Check `command -v npx` first. Open a new session if it has expired. Use fresh snapshots and specific locators.
- The original implementation was not committed, and there is no guarantee all legacy README/status documents have been updated for My Team. This handoff is the consolidated implementation map.

## Final verification addendum

Completed September 23, 2026, using the running local API/production frontend and public ngrok proxy:

- Added a 13-player sample roster through real UI controls and received a complete nine-slot recommendation. Confirmed saved recommendation survives reload.
- Manual QB lock, manual exclusion and missing-kicker/partial-lineup behavior passed.
- Changed WR starting slots from two to three: server returned a complete **10-slot** lineup. Restored ESPN defaults afterward.
- Switched to Week 2, which has no saved lineup snapshot: displayed the unavailable message, with no accidental Week 3 result. “Open 2026 Week 3” restored the saved Week 3 recommendation.
- Desktop 1440px and mobile 390px checks found no horizontal overflow; screenshots saved below.
- Simulated a failed weekly-data request in the automation browser. Recommendation was disabled; Retry successfully recovered when the simulated failure was removed.
- Simulated browser time after the first kickoff. Recompute was disabled while the saved pregame lineup remained visible. Restored browser time afterward. This complements the backend started-week rejection tests; the live DB/schedule was not altered to simulate kickoff.
- Public ngrok **POST** successfully returned the complete nine-slot lineup, total `176.69` before display rounding. Duplicate roster input was rejected with 422; a non-allowlisted POST path was rejected with 404.
- The browser console recorded the single expected failed-resource error from the deliberate network-failure test, not an unexplained runtime error.
- After the final service restart, Player explorer loaded Justin Jefferson, Best matchups returned 94 WR rows, and returning to My Team preserved the saved roster/recommendation.

A final production build exposed a real packaging issue: `lib/lineup.test.ts` imported `bun:test`, but the Next TypeScript project did not have Bun type declarations. Changed the test to the project's existing `node:test` + `node:assert/strict` pattern. No dependency or compiler-check suppression was added. **All 11 frontend tests, ESLint and the production build then passed.** Restarted `football-forecast-ui` with that successful build.

Artifacts:

- `output/playwright/lineup-desktop.png`
- `output/playwright/lineup-mobile.png`

The Playwright checks were executed through the CLI, not committed as a Playwright test suite. Only the isolated automation browser has the sample roster. No user ESPN account was connected or modified. No NFL data/model/snapshot was changed by these checks.

The scheduled refresh remains **not installed/enabled**. Live injuries, full D/ST-name search, broader scoring reconciliation and production hardening remain the follow-ups listed above. No feature implementation beyond the frontend test-import fix was made during this end-to-end pass.
