# Backend implementation status — September 21, 2026

## Latest update

Best matchups now has real-data views: actual-results leaderboards for past/started
weeks, published forecasts when available before kickoff, otherwise separately stored
preliminary estimates. The Week 3 preliminary read model currently has 184 ranked
players (70 RB, 88 WR, 26 TE), with 207 other active-roster candidates omitted for
missing history, coverage, or an eligible matchup. This is not a trained ML model or
a published forecast. Opponent context uses available recorded scores with partial
coverage labeled. Strict forecast-publication gates remain unchanged. Future imports
refresh the next fully upcoming week's preview atomically; scheduling remains manual.
The rankings API performs no model execution. Backend suite: 171 tests passing (September 27, 2026).

The user removed blanket completion verification. Feature/baseline v2 now includes
recorded appearances without completion reports, excluding reported DNF/DNP games.
Unknown statuses remain in provenance, but no longer block averages. Unreported
early exits may remain. This supersedes earlier strict completion gates.

Fresh snapshot `ea0cf7e64de34502868981d30371476f` imported successfully: 11,194
supported stat rows, 12,978 mapped participation rows, and zero unexplained scoring
differences or missing completed-game team coverage. Fifteen 2026 Week 2 games are
complete; one remains upcoming in this import. Jefferson's Week 2 actual is 8.5 PPR.
The UI displays completed results through the selected week, removes the Unverified
column, and preserves the existing styling. Forecast inputs remain prior-week-only.

## Implemented

- Version 2 raw-to-canonical mapping for 2024, 2025, and 2026: stats, schedules,
  weekly rosters, snap counts, and player-ID references.
- Strict scoring-critical null/type checks, identical-duplicate collapse,
  conflicting-duplicate rejection, stable-ID matching, Eastern kickoff conversion,
  neutral-site handling, and verified schedule/opponent context.
- Independently versioned PPR with a reproducible source-score comparison. The
  source total lost-fumbles field includes all units, as verified in
  [upstream calculation code](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R).
  Source PPR adds special-teams touchdowns and two-point conversions and deducts
  the three component fumble categories instead of the total. The report records
  the exact per-row adjustment rather than treating all differences as errors.
- Checksummed raw snapshots and immutable per-validation processed artifacts,
  including the exact mapping config, audit/schema metadata, and quality report.
- Transactional, serialized Postgres upserts, source timestamps, older-import
  guards, successful/failed run records, and separate roster/participation tables.
- Append-only reviewed postgame evidence with timestamps and source URLs. DNP
  assertions cannot contradict recorded participation. Pregame reports cannot
  establish DNF or finished status. Conflicting equally recent evidence stays unknown.
- Prior-week feature and baseline functions with DNF exclusion, confirmed zero-game
  inclusion, limited-history handling, and explicit unavailable states. A raw
  previous-game outcome remains unchanged even when its DNF excludes it from averages.
- Separate database integration fixtures and meaningful rollback, replay,
  scoring, schedule, snapshot integrity, evidence, and leakage tests.
- Atomic baseline forecast batches with exact inputs, features, evidence, cutoff,
  version and input fingerprint; database-enforced update/delete protection.
  One publication per week, idempotent retries, diagnostic blocked attempts, and
  no cross-week fallback. Ingestion, evidence import, and generation share a lock.
- Equal-weight within-position projection/opponent percentiles, tie-aware ranking,
  appearance sample sizes, and explicit missing-opponent-coverage states.
- Read-only API endpoints for player search, metadata, projections, actual history,
  opponent history, aggregate dashboards, and rankings. Request transactions are
  repeatable-read and never execute forecasting or ingestion.

## Real-data verification

The initial import and replay used raw artifact
`464baea422a94ea780fb35a3add6271a`. Generated files are ignored by Git.

- 39,595 source stat rows; 10,913 supported regular-season player-stat records.
- 816 regular-season schedule rows, including future 2026 games.
- 1,287 player records, 24,808 weekly roster records, 12,657 mapped participation records.
- 190 source-PPR differences; all explained by the verified formula differences.
- No missing supported-stat coverage for either team in completed scheduled games.
- 1,914 snap appearances without matching stat records: stored as participation
  with unknown scoring coverage, not fabricated zero-point stat rows.
- 36 unmapped/ambiguous snap-player records and 11 roster records without stable
  IDs are reported; they are not joined by name or silently invented.

The second import updated existing records rather than duplicating player games.
Alembic reports no schema drift through revision `202609210002`.

An earlier September 21 backend test run passed **65 tests** against the dedicated test
Postgres database (see the top of this document for the current suite result). Ruff lint/format checks pass. Two upstream test-client
deprecation warnings remain; they do not fail the tests.

Live HTTP smoke checks passed for database readiness, metadata, player search,
the Justin Jefferson dashboard (eight actual history games), pending Week 3
rankings, and the nine-route OpenAPI schema. No real forecast has been published.

A real Week 3 generation attempt created blocked batch
`8557538df6344a47a802c47ef8b5b7d4`: the existing September 19 import does not contain
complete prior-week results or Week 3 rosters. Nothing was published. This attempt
did not refresh source data. The later refresh above adds completed Week 2 results.

## Not yet complete

- Full participation/scoring coverage and reviewed completion evidence across all
  supported player games. No real completion assertions have been populated.
  Completion reports are now optional; averages exclude only reported DNFs.
- Automated news retrieval/extraction/review. The evidence importer is an operator
  input boundary, not an autonomous news-validation system.
- Automatic source-removal reconciliation: omissions currently block an import
  and preserve stored data rather than delete records based on incomplete evidence.
- ML training, model promotion, and chronological/walk-forward evaluation.
- The deployed Tuesday scheduler and production Supabase/Railway setup.

## Frontend preview

The initial Next.js frontend now connects through a same-origin, read-only API
proxy. It includes real player search, season/week selectors, forecast and matchup
context, PPR history charts and tables, opponent context, and pending/published
rankings. Mobile layout, keyboard search, and honest unavailable states are included.
The public ngrok preview uses a production build; backend and database ports remain
local. See `football-forecast-ui/README.md` for run/stop instructions.

The data foundation, player API, and baseline publication pipeline are usable now.
Missing scoring coverage remains an explicit gate. No real forecast has been
published or backdated.
