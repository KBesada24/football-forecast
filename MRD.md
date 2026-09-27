# Product Requirements Document: Fantasy Football Player Projection Web App

Approved MVP decisions and implementation sequence are recorded in
[`docs/backend-implementation-plan.md`](docs/backend-implementation-plan.md)
(accepted September 16, 2026). That document resolves the scoring, participation,
weekly cutoff, eligibility, model-promotion, and publication choices in this PRD.

## 1. Product Summary

Build a responsive, single-page web application that lets a user search an NFL player and receive a forecast of that player’s **full-PPR fantasy points for a selected upcoming NFL week**, together with source-backed historical context.

The user-facing product is a web page, not a CLI. The application must show:

- A player search/autocomplete experience.
- Next-game matchup context.
- A saved model projection for full-PPR points.
- Recent game-by-game fantasy production.
- Recent opportunity/usage charts.
- The player’s recorded historical fantasy results against the selected upcoming opponent.
- Data freshness, sample-size caveats, model metadata, and limitations.

The numerical forecast must be produced by a batch forecasting pipeline with a
trailing-four-game baseline and an evaluated tabular machine-learning candidate.
Serve the baseline unless the candidate passes the documented promotion criteria.
An LLM can be added later to explain data retrieved from this system, but it must
not create forecasts or invent historical player information.

## 2. Repository Architecture

The main repository already contains these two required subdirectories:

```text
backend/
football-forecast-ui/
```

Use this repository layout. Do not introduce `apps/web`, `services/api`, or an alternative monorepo layout unless there is a compelling technical blocker and the change is documented.

```text
project-root/
├── backend/                         # Python API, NFL data pipeline, ML models, scheduled jobs
├── football-forecast-ui/            # Next.js/React/TypeScript single-page application
├── docs/                            # Shared architecture/data-source documentation
├── README.md                        # Root setup and architecture overview
├── MRD.md
├── .gitignore
└── docker-compose.yml                # Optional local orchestration only
```

### Backend responsibilities

`backend/` owns all server-side data and forecasting work:

- nflreadpy ingestion and source-schema inspection.
- Raw-data caching and provenance metadata.
- Source-to-canonical normalization.
- Player-stat and schedule joins.
- Full-PPR label calculation.
- Leakage-safe feature generation.
- Baseline and machine-learning model training.
- Chronological backtests and metric reports.
- Batch forecast generation and persistence.
- Read-only HTTP API used by the frontend.
- Database migrations and persistence logic.
- Scheduled refresh jobs.

Recommended backend stack:

```text
Python 3.11 or 3.12
FastAPI
Pydantic
nflreadpy
Polars
Pandas only at explicit compatibility boundaries
scikit-learn
LightGBM or CatBoost
SQLAlchemy or SQLModel
Alembic
PostgreSQL / Supabase PostgreSQL
Pytest
```

### Frontend responsibilities

`football-forecast-ui/` owns all browser/user experience work:

- Next.js + React + TypeScript SPA.
- Player-name search and autocomplete.
- Season/week context selection.
- Calls to backend read-only API.
- Projection/matchup card.
- Recent performance chart.
- Recent usage chart.
- Historical performance-versus-opponent section.
- Responsive, accessible loading, empty, no-result, unavailable, and error states.

Recommended frontend stack:

```text
Next.js
React
TypeScript
Tailwind CSS
TanStack Query or SWR
Zod for client response validation where useful
Recharts, Nivo, or another accessible React chart library
```

### Boundary rule

The frontend must not:

- Import Python modules from `backend/`.
- Read local Parquet files.
- Call nflreadpy directly.
- Train or run a model in the browser.
- Calculate authoritative PPR values from raw source data.
- Depend directly on raw nflreadpy field names.

The backend must not:

- Return raw source DataFrames to the frontend.
- Make the frontend reconstruct API/model logic.
- Train models or download source data in response to a player search request.

The only frontend/backend boundary is a versioned, validated HTTP API.

### Local development topology

```text
Browser
   ↓
football-forecast-ui/ (Next.js, default port 3000)
   ↓ HTTP / JSON
backend/ (FastAPI, default port 8000)
   ↓
PostgreSQL / Supabase and model/data artifacts
```

Use environment variables:

```bash
# football-forecast-ui/.env.local (server-only; never NEXT_PUBLIC_)
BACKEND_URL=http://localhost:8000

# backend/.env
DATABASE_URL=postgresql+psycopg://...
CORS_ORIGINS=http://localhost:3000
DATA_DIR=./data
MODEL_DIR=./models
```

Never commit secrets or production database URLs.

## 3. Scope

### MVP question

> Given information available before Week \(t\), what full-PPR fantasy-point total is a supported player projected to score in Week \(t\), and what recent historical context should the user see alongside that forecast?

### Supported players

- Running backs (`RB`)
- Wide receivers (`WR`)
- Tight ends (`TE`)

### Default scoring

The MVP uses full PPR:

| Stat | Points |
|---|---:|
| Passing yards | 0.04 per yard |
| Passing touchdowns | 4 |
| Interceptions thrown | -2 |
| Rushing yards | 0.10 per yard |
| Rushing touchdowns | 6 |
| Receptions | 1 |
| Receiving yards | 0.10 per yard |
| Receiving touchdowns | 6 |
| Fumbles lost | -2 |

The application must label projections and chart values as **Full-PPR**.

Use exactly the formula above for the MVP, assign it a scoring version, and expose
the scoring rules to users. Do not imply equivalence with every fantasy platform:
two-point conversions and return touchdowns are not included in this formula.

Forecasts assume participation; they do not model the probability of playing.
Show this limitation to users. Use verified roster membership and the target-week
schedule to establish eligibility, return unavailable for known ineligible
players, and do not interpret missing stat rows as zero-point appearances.

Import 2024, 2025, and 2026 regular-season data. The current season contributes
completed pre-cutoff player games and upcoming schedule context; future games
must not become zero-point historical rows. "No history" means no usable history
in the imported dataset, not necessarily no NFL career appearances.

### Non-goals

- Fine-tuning or training an LLM on NFL data.
- User accounts, billing, notifications, or watchlists.
- Connecting to Sleeper, Yahoo, ESPN, or another fantasy-league account.
- Starting a player, changing lineups, making waiver moves, drafting, trades, or external actions.
- Live/in-game predictions.
- Kicker, DST, IDP, dynasty, keeper, auction, superflex, or TE-premium support.
- Claims that the model guarantees performance or beats commercial projections.

## 4. Data-Source Decision

### Required primary library: `nflreadpy`

Use **`nflreadpy`** as the primary NFL data-access library in `backend/`.

`nflreadpy` is the maintained Python port of `nflreadr`. It downloads nflverse data, uses Polars DataFrames, supports caching/progress tracking, and documents `load_player_stats()` for player game-level statistics. The package also accesses data from nflverse-data, dynastyprocess, and ffopportunity repositories. [web:83]

Do **not** make `nfl_data_py` a required backend dependency. `nfl_data_py` was archived on September 25, 2025, is read-only, and was deprecated in favor of `nflreadpy`. It may only appear in migration notes or a separately documented fallback plan. [web:36]

### Required source policy

```text
Raw nflreadpy Polars DataFrames
        ↓
backend/src/data/source_adapter.py
        ↓
Canonical backend tables/models
        ↓
Feature store + persisted ML predictions
        ↓
FastAPI response DTOs
        ↓
football-forecast-ui API client and components
```

- Raw source-field names are isolated to `backend/src/data/source_adapter.py` and `backend/configs/source_schema_mapping.yaml`.
- All other backend code uses canonical application fields.
- The frontend consumes only documented API DTOs.
- API response examples in this document are product contracts, not claims about native nflreadpy JSON output.
- The agent must inspect the actual runtime schema from the pinned nflreadpy version before finalizing mappings.
- If a scoring-critical raw field is unavailable or ambiguous, fail clearly rather than guessing.

### Authoritative schema hierarchy

When there is a discrepancy, use:

1. Actual schema returned by the pinned installed `nflreadpy` version.
2. Corresponding nflverse/nflreadr data dictionary.
3. Checked-in backend source-schema mapping and tests.
4. Canonical backend schema in this PRD.

This PRD does not override runtime source output.

## 5. Verified nflreadpy Capabilities

The backend may use the following public loader names, subject to confirming the installed-package signatures during the schema audit:

| Need | nflreadpy loader | Backend purpose |
|---|---|---|
| Player weekly/game-level statistics | `load_player_stats(seasons)` | Core stats for PPR labels, game logs, and history features |
| Schedule/game context | `load_schedules(seasons)` | Opponent, home/away, game ID, date/time resolution |
| Player reference data | `load_players()` | Search/identity reference when available |
| Season rosters | `load_rosters(seasons)` | Player name, position, team, status, platform-ID enrichment |
| Weekly rosters | `load_rosters_weekly(seasons)` | Optional historical weekly roster/team association |
| Fantasy platform IDs | `load_ff_playerids()` | Future cross-platform mapping |
| Play-by-play | `load_pbp()` | Future opportunity and opponent feature derivation |
| Team stats | `load_team_stats(seasons=True)` | Future team context |
| Snap counts | `load_snap_counts(seasons)` | Future playing-time features |
| Injuries | `load_injuries(seasons)` | Later only with strict timestamp controls |
| Depth charts | `load_depth_charts(seasons)` | Later only with strict timestamp controls |
| Next Gen Stats | `load_nextgen_stats(...)` | Future advanced metrics |

nflreadpy documents use of `load_pbp()`, `load_player_stats([2022, 2023])`, and `load_team_stats(seasons=True)`. It returns Polars DataFrames, and `.to_pandas()` is supported at explicit compatibility boundaries. [web:83]

## 6. Required Runtime Schema Audit

Before building the feature pipeline, model, database mapping, API, or visualizations, the backend must perform a source-schema audit.

### Required backend implementation

Create:

```text
backend/src/jobs/audit_nflreadpy_schema.py
backend/configs/source_schema_mapping.yaml
backend/tests/test_schema_mapping.py
backend/data/metadata/
docs/source-schema-audit.md
```

### Audit workflow

1. Pin `nflreadpy` in `backend/pyproject.toml` or `backend/requirements.txt`.
2. Use `load_player_stats()` and `load_schedules()` for at least two completed recent seasons.
3. Record exact fields, Polars dtypes, row counts, null counts, and sample records.
4. Record installed package version and loader signatures.
5. Compare runtime fields with the relevant nflverse data dictionaries.
6. Populate every `chosen_raw_field` in `backend/configs/source_schema_mapping.yaml` from actual output.
7. Add tests proving required canonical columns can be generated.
8. Halt with actionable errors if scoring-critical fields cannot be mapped safely.

### Schema audit sample

```python
# backend/src/jobs/audit_nflreadpy_schema.py
import inspect
import importlib.metadata
import polars as pl
import nflreadpy as nfl

SEASONS = [2024, 2025]

print("nflreadpy version:", importlib.metadata.version("nflreadpy"))
print("load_player_stats:", inspect.signature(nfl.load_player_stats))
print("load_schedules:", inspect.signature(nfl.load_schedules))

player_stats = nfl.load_player_stats(SEASONS)
schedules = nfl.load_schedules(SEASONS)

assert isinstance(player_stats, pl.DataFrame)
assert isinstance(schedules, pl.DataFrame)

print("player_stats schema:", player_stats.schema)
print("player_stats sample:", player_stats.head(5))
print("schedules schema:", schedules.schema)
print("schedules sample:", schedules.head(5))
```

The actual output from this job, not example names in a PRD, defines the final raw source mapping.

## 7. Canonical Backend Data Model

These fields are internal backend schemas. They are not promises that nflreadpy returns exact raw fields with these names.

### Player dimension

```text
player_id: string, required
player_name: string, required
position: string, required
current_team: string, nullable
active_status: string, nullable
headshot_url: string, nullable
source_name: string, required
source_retrieved_at: timestamp, required
```

### Game/schedule dimension

```text
game_id: string, required when source provides it
season: integer, required
week: integer, required
game_type: string, nullable
game_date: date, nullable
game_time: string, nullable
game_datetime: timestamp, nullable
away_team: string, required
home_team: string, required
location: string, nullable
neutral_site: boolean, nullable
game_status: string, nullable
source_name: string, required
source_retrieved_at: timestamp, required
```

The published schedule dictionary documents schedule concepts including game ID, season, week, away/home team, game date/time, scores, location, and game context. Verify actual raw field names against installed schema. [web:84][web:85]

### Canonical player-game stats

```text
season: integer, required
week: integer, required
game_type: string, nullable
player_id: string, required
player_name: string, required
position: string, required
team: string, required
opponent_team: string, nullable
home_away: string, nullable
game_id: string, nullable
game_date: date, nullable

passing_yards: float, default 0
passing_tds: float, default 0
interceptions: float, default 0

carries: float, default 0
rushing_yards: float, default 0
rushing_tds: float, default 0
rushing_fumbles_lost: float, default 0

targets: float, default 0
receptions: float, default 0
receiving_yards: float, default 0
receiving_tds: float, default 0
receiving_fumbles_lost: float, default 0

sack_fumbles_lost: float, default 0
fumbles_lost_total: float, default 0
fantasy_points_ppr: float, required

source_name: string, required
source_retrieved_at: timestamp, required
mapping_version: string, required
```

### Raw-to-canonical candidate map

The following are **candidates to verify**, not finalized claims. The schema-audit milestone must replace each candidate with its actual raw field(s).

| Canonical backend field | Candidate raw fields to inspect | Required behavior |
|---|---|---|
| `season` | `season` | Required integer map |
| `week` | `week` | Required integer map |
| `player_id` | `player_id`, `gsis_id` | Select one stable ID; never use name as primary key |
| `player_name` | `player_name`, `player_display_name`, `full_name` | Choose verified source field |
| `position` | `position` | Required; normalize standard codes |
| `team` | `team`, `recent_team` | Use team on player-game row; document precedence |
| `carries` | `carries`, `rushing_attempts` | Prefer verified `carries`; do not assume alternate exists |
| `rushing_yards` | `rushing_yards` | Required for scoring |
| `rushing_tds` | `rushing_tds` | Required for scoring |
| `targets` | `targets` | Required for MVP features |
| `receptions` | `receptions`, `receiving_receptions` | Required for scoring; verify exact semantics |
| `receiving_yards` | `receiving_yards` | Required for scoring |
| `receiving_tds` | `receiving_tds` | Required for scoring |
| `passing_yards` | `passing_yards` | Keep when available |
| `passing_tds` | `passing_tds` | Keep when available |
| `interceptions` | `interceptions`, `passing_interceptions` | Verify semantics |
| `rushing_fumbles_lost` | `rushing_fumbles_lost` | Verify semantics |
| `receiving_fumbles_lost` | `receiving_fumbles_lost` | Verify semantics |
| `sack_fumbles_lost` | `sack_fumbles_lost` | Keep when available |
| `fantasy_points_ppr_source` | `fantasy_points_ppr` | Validation-only unless exact scoring match is proven |

The nflverse player-stat dictionary is the reference for player-stat definitions, but the installed runtime schema must be verified before mapping. [web:78][web:80]

### Fumbles-lost rule

Calculate canonical `fumbles_lost_total` using exactly one verified approach:

```text
A. A verified source total field, OR
B. A sum of verified non-overlapping fields:
   rushing_fumbles_lost + receiving_fumbles_lost + sack_fumbles_lost
```

Never add a total field and components together. If fumble-loss semantics cannot be verified, stop normalization and report a scoring configuration error.

### Schedule join rule

Derive `opponent_team` and `home_away` server-side inside `backend/src/data/schedule_join.py`.

Join order:

```text
1. Use verified shared game_id between player-game stats and schedule records when available.
2. Otherwise match season + week + player-game team against schedule.home_team / schedule.away_team.
```

Derivation:

```text
if neutral_site and player_team in (home_team, away_team):
    opponent_team = the other team
    home_away = "neutral"
elif player_team == home_team:
    opponent_team = away_team
    home_away = "home"
elif player_team == away_team:
    opponent_team = home_team
    home_away = "away"
else:
    opponent_team = null
    home_away = null
    log unmatched row
```

Do not fabricate schedule context for unmatched rows. Account for historical team-code changes with an explicit mapping only if tests validate it.

## 8. Full-PPR Calculation

Implement the calculation in `backend/src/domain/scoring.py` as a pure, unit-tested function.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class FantasyStats:
    passing_yards: float = 0.0
    passing_tds: float = 0.0
    interceptions: float = 0.0
    rushing_yards: float = 0.0
    rushing_tds: float = 0.0
    receptions: float = 0.0
    receiving_yards: float = 0.0
    receiving_tds: float = 0.0
    fumbles_lost_total: float = 0.0


def calculate_full_ppr(stats: FantasyStats) -> float:
    return (
        0.04 * stats.passing_yards
        + 4.0 * stats.passing_tds
        - 2.0 * stats.interceptions
        + 0.10 * stats.rushing_yards
        + 6.0 * stats.rushing_tds
        + stats.receptions
        + 0.10 * stats.receiving_yards
        + 6.0 * stats.receiving_tds
        - 2.0 * stats.fumbles_lost_total
    )
```

Requirements:

- If a verified source PPR field is available, store it separately as `fantasy_points_ppr_source`.
- Validate calculated PPR against the source PPR field for at least 20 player-game rows over multiple seasons and positions.
- Document mismatches caused by source scoring conventions, bonuses, two-point conversions, or source semantics.
- Use independently calculated PPR for model labels unless validation confirms an exact match to this scoring profile.
- Add scoring tests for zero scores, receptions, mixed rush/receive production, touchdowns, interceptions, fumbles, and missing optional values.

## 9. Forecast Pipeline

### Feature requirements

For a Week \(t\) prediction, calculate all features from games occurring before Week \(t\).

Use one weekly cutoff before the first game of the target week, with statistical
inputs limited to completed games in prior weeks. Start the weekly data refresh
Tuesday at 08:00 America/New_York, observing daylight saving. Validate source
freshness and completed-game coverage for the preceding NFL week (including its
Thursday, Sunday, Monday, and any other scheduled game days). Resolve the upcoming
NFL week and matchups from the schedule, update feature inputs, then generate and publish a complete
forecast batch. Keep the last successful batch if inputs are delayed or validation
fails, and display actual data freshness. The start time is not a guarantee that
new forecasts are immediately available. Preserve published forecasts
and their cutoff when source data is later corrected. Historical evaluations
using subsequently corrected data must be labeled retrospective, rather than
claimed to reproduce the exact information available at the historical cutoff.

Rolling averages count only games the player actually played without an early
exit, not calendar weeks. Exclude DNP/inactive games, byes, and games started but
not finished (DNF). Preserve actual DNF statistics in game history. Retain eligible
zero-point appearances only when statistical coverage supports the score. Verify
early-exit and return-to-game evidence; low snap counts alone cannot establish DNF.
Postgame confirmation from official team or NFL.com reporting is sufficient. Live
injury monitoring is not required: Tuesday's refresh reviews completed-game reports
before generating the upcoming week's forecast. A report published after the
completed game can determine that game's eligibility for subsequent averages.
Retain its source and timestamps; injury alone does not prove failure to return.
Unknown completion status must not silently count as a finished game. Keep actual
appearance counts separate from counts eligible for averages and history quality.
Verify these sources during the data-foundation stage, before averages. Carry
prior-season history across season boundaries and player history across trades;
derive the upcoming matchup from the verified target-week team. Do not insert
zero-score rows for bye weeks or missing records.

Required first-version features:

```text
games_played_prior
ppr_points_prev
ppr_points_avg_3
ppr_points_avg_4
ppr_points_avg_8
ppr_points_std_4

targets_prev
targets_avg_3
targets_avg_4
targets_avg_8

receptions_prev
receptions_avg_4

carries_prev
carries_avg_3
carries_avg_4

rushing_yards_prev
rushing_yards_avg_4
receiving_yards_prev
receiving_yards_avg_4
rushing_tds_avg_8
receiving_tds_avg_8

position
season
week
```

### Mandatory no-leakage rule

Correct conceptual pattern:

```python
prior = player_stat.shift(1)
rolling_average = prior.rolling(window=4, min_periods=1).mean()
```

Forbidden:

```python
# Incorrect: includes target-week outcome.
rolling_average = player_stat.rolling(window=4).mean()
```

Required test:

- Change a fixture player’s actual Week \(t\) stat line.
- Assert generated feature values for that player’s Week \(t\) remain unchanged.
- Assert Week \(t+1\) values are allowed to change.

Leakage-test failure is release-blocking.

### Baseline

Implement a trailing-four-eligible-game PPR average baseline. Eligible games are
verified appearances without an early exit. Skip DNF games when selecting the
four games; all fallback counts below refer to eligible history in our dataset.

Fallbacks:

- 1–3 prior games: available-game mean.
- 0 prior games: structured unavailable state for both baseline and ML forecasts in the initial MVP.
- Persist `history_quality` for the frontend: `none`, `limited`, or `adequate`.

### ML model

Use LightGBM `LGBMRegressor` or CatBoost for the first model.

Tuesday refreshes do not retrain the model. They supply refreshed historical
features and upcoming matchup context to the existing approved model or baseline,
then publish a new weekly snapshot. Training, evaluation, and model promotion are
separate explicit jobs. The weekly "best matchups" snapshot blends projected PPR
and opponent favorability. Initially use equal weights for within-position
percentile ranks, display both components, and version the ranking definition.
The initial opponent component is PPR allowed per verified appearance at the
player's position over the opponent's last four completed pre-cutoff team games,
with sample sizes and coverage caveats. This is descriptive matchup context, not
a claimed causal increase in projected points. Missing coverage makes the combined
rank unavailable rather than implying a neutral matchup. Detailed rules are in
the implementation plan.

Requirements:

- Fixed random seed.
- Model config stored under `backend/configs/`.
- Combined RB/WR/TE model with position categorical input is acceptable initially.
- Separate position-specific models are permitted only with documented evaluation justification.
- Save model artifact, feature list, config, train period, data artifact ID, model version, timestamp, and metrics.

### Backtesting

Never use random row-level splitting.

Retain actual target-week outcomes for participating players, including players
who subsequently leave early. DNF exclusion applies to eligible historical averages,
not to selecting future finishers for training or evaluation. A prior DNF does
not by itself determine next-week availability. Verify completion-status coverage
and historical availability before implementing these history filters.

The initial chronological experiment develops on 2024 and holds out 2025. Keep
2026 out of fitting and tuning that experiment; use completed 2026 games for live
forecast inputs and separate forward monitoring. Importing a season does not
automatically include it in a model's training set.

Required evaluations:

- Chronological season holdout.
- Walk-forward evaluation: train only through Week \(t-1\), predict Week \(t\).

Required metrics:

- MAE.
- RMSE.
- Spearman rank correlation.
- Per-position MAE/RMSE.
- Baseline versus ML comparison.

Use overall MAE as the primary promotion metric, with per-position guardrails and
forecast coverage reported. Set numeric improvement and regression thresholds
using development data and freeze them before final holdout evaluation. Serve
the baseline if candidate improvement is inconclusive or the criteria fail.

## 10. Backend API

Implement a read-only FastAPI service in `backend/`. Define Pydantic request/response models under `backend/src/api/schemas/`. Version endpoints under `/api/v1`.

### CORS

In development, permit only configured frontend origins such as:

```text
http://localhost:3000
```

In production, use explicit deployed UI origins. Never use unrestricted CORS in production.

### Player search

```text
GET /api/v1/players/search?q={query}
```

```ts
type PlayerSearchResponse = {
  results: Array<{
    playerId: string;
    displayName: string;
    position: "RB" | "WR" | "TE" | string;
    team: string | null;
    active: boolean | null;
    headshotUrl: string | null;
  }>;
};
```

Sources: normalized backend player dimension and recent roster/player-game context.

Requirements:

- Minimum query length: 2 characters.
- Bounded result count.
- Name normalization for punctuation/spacing when practical.
- Include team and position for disambiguation.
- Prefer recent/active players while keeping historical lookup practical.

### Projection overview

```text
GET /api/v1/players/{playerId}/projection?season={season}&week={week}
```

```ts
type PlayerProjectionResponse = {
  availability: "available" | "unavailable" | "insufficient_history";

  player: {
    playerId: string;
    displayName: string;
    position: "RB" | "WR" | "TE" | string;
    team: string | null;
    headshotUrl: string | null;
  };

  matchup: {
    season: number;
    week: number;
    opponent: string | null;
    homeAway: "home" | "away" | "neutral" | null;
    gameId: string | null;
    gameDate: string | null;
    gameDateTime: string | null;
    status: "upcoming" | "completed" | "bye" | "unavailable";
  };

  forecast: {
    scoringFormat: "full_ppr";
    projectionPpr: number | null;
    baselineProjectionPpr: number | null;
    recentPprAverage4: number | null;
    gamesPlayedPrior: number;
    historyQuality: "none" | "limited" | "adequate";
    modelName: string | null;
    modelVersion: string | null;
    trainingDataEnd: { season: number; week: number } | null;
    generatedAt: string | null;
    dataAsOf: string | null;
  };

  caveats: string[];
};
```

Origins:

| Response group | Backend source |
|---|---|
| `player` | Canonical player data |
| `matchup` | Canonical game schedule joined by player/team/week |
| `projectionPpr` | Saved batch model forecast |
| `baselineProjectionPpr`, `recentPprAverage4`, `gamesPlayedPrior` | Persisted feature/forecast row |
| Model timestamps/version fields | Model and batch-job metadata |
| `caveats` | Deterministic backend availability/history rules |

No forecast may be calculated ad hoc from raw source data in this request.

### Recent history

```text
GET /api/v1/players/{playerId}/history?season={season}&week={week}&limit={limit}
```

```ts
type PlayerHistoryResponse = {
  playerId: string;
  scoringFormat: "full_ppr";
  targetContext: { season: number; week: number };
  games: Array<{
    season: number;
    week: number;
    gameId: string | null;
    gameDate: string | null;
    team: string | null;
    opponent: string | null;
    homeAway: "home" | "away" | "neutral" | null;
    fantasyPointsPpr: number;
    carries: number | null;
    targets: number | null;
    receptions: number | null;
    rushingYards: number | null;
    receivingYards: number | null;
    rushingTds: number | null;
    receivingTds: number | null;
    touchdowns: number;
  }>;
};
```

Rules:

- Default limit: 8 completed player games before target week.
- Target-week outcome must never appear when the target week is upcoming.
- Do not turn a bye/absent game into a zero-point row without explicit source semantics.
- `touchdowns` is an app-derived display field: verified rushing touchdowns plus receiving touchdowns for RB/WR/TE.

### Historical results versus opponent

```text
GET /api/v1/players/{playerId}/vs-opponent?season={season}&week={week}
```

```ts
type PlayerVsOpponentResponse = {
  playerId: string;
  opponent: string | null;
  gamesCount: number;
  summary: {
    averagePpr: number | null;
    medianPpr: number | null;
    minimumPpr: number | null;
    maximumPpr: number | null;
    averageTargets: number | null;
    averageCarries: number | null;
    averageReceptions: number | null;
  };
  caveat: string;
  games: Array<{
    season: number;
    week: number;
    gameDate: string | null;
    playerTeam: string | null;
    opponent: string;
    homeAway: "home" | "away" | "neutral" | null;
    fantasyPointsPpr: number;
    carries: number | null;
    targets: number | null;
    receptions: number | null;
    rushingYards: number | null;
    receivingYards: number | null;
    rushingTds: number | null;
    receivingTds: number | null;
  }>;
};
```

Backend computation:

```text
1. Resolve target player’s selected season/week schedule context.
2. Determine target opponent using canonical schedule join.
3. Retrieve earlier canonical player-game records for the player.
4. Filter where historical opponent_team equals target opponent.
5. Return exact filtered games and descriptive aggregates.
```

Caveats:

| Prior games | Required backend caveat |
|---:|---|
| 0 | “No prior recorded matchups against {opponent} are available in this dataset.” |
| 1 | “One prior matchup is not enough to establish a reliable trend.” |
| 2–3 | “Small sample: {n} prior matchups. Team personnel and player roles may have changed.” |
| 4+ | “Historical context only. Earlier matchups may involve different teams, coaches, roles, and defensive personnel.” |

### Aggregate dashboard endpoint

```text
GET /api/v1/players/{playerId}/dashboard?season={season}&week={week}
```

```ts
type PlayerDashboardResponse = {
  projection: PlayerProjectionResponse;
  recentHistory: PlayerHistoryResponse;
  versusOpponent: PlayerVsOpponentResponse;
};
```

This is the recommended endpoint for `football-forecast-ui/` page rendering. Keep granular endpoints for testing and future reuse.

### Metadata endpoint

```text
GET /api/v1/meta/current-context
```

Return:

```text
supported_positions
scoring_format
available_seasons
available_weeks_by_season
latest_data_as_of
latest_model_version
latest_forecast_generation_time
```

## 11. Frontend Requirements: `football-forecast-ui/`

### Technology

- Next.js, React, TypeScript.
- Tailwind CSS or equivalent responsive styling.
- TanStack Query, SWR, or equivalent for caching/fetching/error handling.
- Typed backend API client stored in `football-forecast-ui/lib/api/`.
- Recharts, Nivo, or another accessible React chart library.

### API client rule

Create centralized API functions and TypeScript types. Do not scatter `fetch()` logic throughout components.

Suggested location:

```text
football-forecast-ui/lib/api/client.ts
football-forecast-ui/lib/api/types.ts
football-forecast-ui/lib/api/players.ts
```

The browser calls only the same-origin proxy at `/api/football/*`. The proxy reads the backend
origin from the server-only environment variable:

```text
BACKEND_URL
```

Do not expose the backend URL through a `NEXT_PUBLIC_` variable.

### SPA layout

```text
+------------------------------------------------------------------+
| App name                                                         |
| [ Search player name ....................................... ]  |
+------------------------------------------------------------------+
| Player header: Name | Position | Team | Full-PPR                 |
| Week X vs/at Opponent | game date/time                           |
+----------------------+-------------------------------------------+
| Projection Card      | Context Card                              |
| 14.6 projected PPR   | Recent avg, usage, sample-size context    |
| Baseline, timestamps | model metadata                            |
+----------------------+-------------------------------------------+
| Recent Full-PPR Game Log chart                                  |
+------------------------------------------------------------------+
| Recent Usage chart                                               |
+------------------------------------------------------------------+
| History vs. Upcoming Opponent: summary + individual games        |
+------------------------------------------------------------------+
| Data limitations and forecast disclaimer                         |
+------------------------------------------------------------------+
```

### Search behavior

- Debounce player-name search requests.
- Require at least 2 query characters before API search.
- Support mouse and keyboard autocomplete navigation.
- Display player name, position, and team in every result.
- Handle duplicate names clearly.
- Update selected-player content without a full browser-page reload.
- Store selected player and optional season/week in URL query parameters when practical.

### Context behavior

- Default to an upcoming supported gameweek when backend resolution is reliable.
- Provide season/week selection for historical/backtest viewing.
- Clearly label selected historical context; do not imply a completed game is still an upcoming forecast.

### Projection card

Must display:

- Projected Full-PPR Points rounded to one decimal place.
- Four-game baseline rounded to one decimal when present.
- Recent four-game average rounded to one decimal when present.
- `Week {week} vs. {opponent}` or `Week {week} at {opponent}`.
- Forecast-generated timestamp and data-as-of timestamp.
- Compact model-version label.
- History-quality caveat when needed.

Do not say “will score.” Use projected, estimated, or forecast.

### Recent performance chart

- Render API `recentHistory.games`.
- X axis: game date or season/week.
- Y axis: `fantasyPointsPpr`.
- Tooltip: opponent, home/away, PPR, carries, targets, receptions, yards, and touchdowns where present.
- Include an optional horizontal four-game-average line.
- Do not include selected future game result.
- Clearly distinguish no-game/bye from a legitimate 0-point performance.

### Recent usage chart

- RB: carries and targets.
- WR/TE: targets and receptions.
- Use appropriately labeled count axes.
- Do not combine yardage and count measures on one unlabeled axis.
- All plotted values come from API historical data, not client-generated estimates.

### History-versus-opponent section

Render API `versusOpponent` data:

- Prior-game count.
- Average and median historical PPR.
- Individual historical games table/chart.
- Season, week, date, team, home/away, PPR, and relevant opportunity fields.
- Required backend caveat displayed prominently.

Treat this as descriptive context, not a forecast guarantee.

### States

| State | Required UI |
|---|---|
| No player selected | Search-led empty state explaining the app briefly |
| Loading | Skeleton cards and chart placeholders; never show stale prior-player data as current |
| No results | Clear no-results message |
| Unsupported position | Explain RB/WR/TE-only MVP scope |
| No scheduled game | Show history where available and state projection unavailable |
| Insufficient history | Clear low-history/fallback message |
| No opponent history | Explicit no-history state; never a fake zero chart |
| API error | Friendly retry UI without stack traces or backend internals |

### Accessibility and responsiveness

- Work from 320px mobile width through desktop.
- Use semantic labels, keyboard-operable search, readable focus states, and sufficient contrast.
- Do not use color as the only meaning carrier.
- Ensure important numbers are readable without hovering on a chart.
- Add accessible text/chart summaries where practical.

## 12. Backend Structure

Use this structure inside the existing `backend/` folder:

```text
backend/
├── src/
│   ├── main.py                         # FastAPI app factory / entrypoint
│   ├── api/
│   │   ├── routers/
│   │   │   ├── players.py
│   │   │   └── metadata.py
│   │   ├── schemas/
│   │   │   ├── players.py
│   │   │   └── metadata.py
│   │   └── dependencies.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── database.py
│   ├── data/
│   │   ├── source_adapter.py
│   │   ├── schema_validation.py
│   │   ├── normalize.py
│   │   ├── schedule_join.py
│   │   └── repositories.py
│   ├── domain/
│   │   ├── scoring.py
│   │   ├── player_history.py
│   │   └── forecasting.py
│   ├── ml/
│   │   ├── features.py
│   │   ├── baseline.py
│   │   ├── train.py
│   │   ├── backtest.py
│   │   ├── predict.py
│   │   └── model_registry.py
│   ├── jobs/
│   │   ├── audit_nflreadpy_schema.py
│   │   ├── ingest_data.py
│   │   ├── build_features.py
│   │   ├── train_model.py
│   │   ├── generate_forecasts.py
│   │   └── sync_database.py
│   └── db/
│       ├── models.py
│       └── migrations/
├── configs/
│   ├── source_schema_mapping.yaml
│   └── model_config.yaml
├── data/                               # Gitignore artifacts
│   ├── raw/
│   ├── processed/
│   ├── features/
│   ├── predictions/
│   └── metadata/
├── models/                             # Gitignore model binaries
├── reports/
├── tests/
│   ├── test_schema_mapping.py
│   ├── test_scoring.py
│   ├── test_schedule_join.py
│   ├── test_features_no_leakage.py
│   ├── test_api_players.py
│   └── test_pipeline_smoke.py
├── pyproject.toml
├── .env.example
└── README.md
```

## 13. Frontend Structure

Use this structure inside the existing `football-forecast-ui/` folder:

```text
football-forecast-ui/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── player-search.tsx
│   ├── player-header.tsx
│   ├── projection-card.tsx
│   ├── matchup-card.tsx
│   ├── recent-performance-chart.tsx
│   ├── usage-chart.tsx
│   ├── versus-opponent.tsx
│   ├── history-table.tsx
│   ├── forecast-caveats.tsx
│   ├── dashboard-skeleton.tsx
│   └── error-state.tsx
├── hooks/
│   ├── use-player-search.ts
│   └── use-player-dashboard.ts
├── lib/
│   ├── api/
│   │   ├── client.ts
│   │   ├── types.ts
│   │   └── players.ts
│   ├── formatters.ts
│   └── query-params.ts
├── public/
├── .env.local.example
├── package.json
├── tsconfig.json
└── README.md
```

## 14. Storage and Scheduled Jobs

### Backend artifacts

Use local Parquet/JSON in development:

```text
backend/data/raw/
backend/data/processed/
backend/data/features/
backend/data/predictions/
backend/data/metadata/
backend/models/
backend/reports/
```

In deployment, use PostgreSQL/Supabase for API query data and object/local storage for large model/Parquet artifacts.

### Suggested database tables

```text
players
teams
games
player_game_stats
player_week_features
player_week_predictions
model_versions
data_ingestion_runs
forecast_generation_runs
```

Suggested uniqueness:

```text
players: player_id
games: game_id
player_game_stats: (player_id, season, week, game_type)
player_week_predictions: (player_id, season, week, model_version)
```

### Job rules

Backend jobs may be invoked via Makefile, task runner, cron, GitHub Actions, Railway/Render scheduler, or another documented orchestration system. They must not be user-facing CLI features.

Required job sequence:

```text
schema audit
→ ingest/cache source data
→ normalize data and join schedules
→ validate PPR labels
→ build features
→ train or load validated model
→ batch generate forecasts
→ persist/upsert query records
```

The FastAPI service reads prepared tables and saved forecasts only.

## 15. Testing and Acceptance Criteria

### Backend source and data tests

- [ ] `backend/` pins and uses `nflreadpy` by default.
- [ ] A runtime schema audit records installed package version, loader signatures, actual columns, dtypes, null counts, and samples.
- [ ] `backend/configs/source_schema_mapping.yaml` documents finalized mappings, transformations, null rules, verification date, and tests.
- [ ] Pipeline fails clearly for missing/ambiguous scoring-critical fields.
- [ ] Player-game data uses stable player IDs and documented deduplication.
- [ ] Schedule joins correctly derive opponent/home-away for home and away fixture cases.
- [ ] Unmatched joins are logged and not fabricated.
- [ ] Full-PPR scorer is unit tested.
- [ ] Calculated and source PPR values are compared when a verified source PPR column exists.

### Backend ML tests

- [ ] Default modeling rows are RB/WR/TE regular-season games.
- [ ] All history/rolling features are shifted prior to aggregation.
- [ ] Changing target-week stats cannot change target-week features.
- [ ] Chronological holdout and walk-forward backtests run.
- [ ] Baseline and ML metrics are compared side by side.
- [ ] Saved model/prediction artifacts include data and model metadata.

### API tests

- [ ] FastAPI endpoints use Pydantic schemas.
- [ ] Search returns disambiguated player matches.
- [ ] Projection reads persisted predictions, not live model training.
- [ ] History returns only completed pre-target games.
- [ ] Versus-opponent response returns exact source-grounded historical games and correct sample sizes.
- [ ] Error responses are structured and do not expose secrets/internal paths.
- [ ] CORS is restricted to configured frontend origin(s).

### Frontend tests

- [ ] `football-forecast-ui/` uses a centralized typed backend API client.
- [ ] User can search/select a player without full-page reload.
- [ ] Projection card displays Full-PPR, forecast, baseline, matchup, freshness, and model metadata.
- [ ] Recent-PPR chart and usage chart render backend history data correctly.
- [ ] History-vs-opponent correctly handles zero, one, 2–3, and 4+ games.
- [ ] Loading/empty/no-result/unavailable/error states are complete.
- [ ] Mobile and desktop layouts work.
- [ ] UI does not say a player “will score” a value or imply historical matchup data guarantees an outcome.

## 16. Delivery Milestones

### Milestone 0: Repository integration and source truth

Deliver:

- Backend and frontend README files.
- Root architecture explanation.
- Pinned backend dependencies.
- Runtime source schema audit.
- Finalized `source_schema_mapping.yaml`.
- Backend mapping tests.

Exit criterion: no model or frontend dashboard work proceeds until raw-to-canonical mappings are verified.

### Milestone 1: Backend data foundation

Deliver:

- nflreadpy ingestion.
- Raw-data/provenance artifacts.
- Canonical player/game tables.
- Schedule join.
- Full-PPR scorer and validation report.

Exit criterion: agent can show correctly normalized player games with verified schedule context.

### Milestone 2: Backend forecast pipeline

Deliver:

- Leakage-safe features.
- Trailing-4 baseline.
- LightGBM/CatBoost forecast model.
- Chronological holdout/walk-forward report.
- Versioned model and batch forecast artifacts.

Exit criterion: anti-leakage tests pass; metrics compare model with baseline.

### Milestone 3: Backend API

Deliver:

- FastAPI application.
- Search, projection, history, versus-opponent, dashboard, and metadata endpoints.
- Database/persisted-query integration.
- API tests and CORS configuration.

Exit criterion: endpoint integration tests return validated, stored, source-grounded responses.

### Milestone 4: Frontend SPA

Deliver:

- Single Next.js page with player search.
- Player/matchup header.
- Projection card.
- Recent PPR and usage charts.
- Opponent-history section.
- Responsive loading/error/empty states.

Exit criterion: user can search a supported player and understand forecast/context entirely in `football-forecast-ui/`.

### Milestone 5: Hardening and deployment readiness

Deliver:

- Root and subproject documentation.
- Environment variable examples.
- Scheduled-job deployment notes.
- Accessibility/mobile review.
- Basic logs/observability for pipeline and API failures.

## 17. Agent Instructions

1. Use the existing directory structure: `backend/` and `football-forecast-ui/`.
2. Do not rework the repo into a different monorepo layout unless blocked; document any exception.
3. Treat `backend/` as the exclusive owner of NFL data access, ML, data normalization, persistence, and API behavior.
4. Treat `football-forecast-ui/` as the exclusive owner of the SPA presentation and backend API consumption.
5. Use `nflreadpy`, not archived `nfl_data_py`, as the default backend data library.
6. Begin with a real schema audit and do not assume candidate raw source columns are exact.
7. Populate `backend/configs/source_schema_mapping.yaml` from actual package output before building source transformations.
8. Do not expose raw nflreadpy objects or column names to the frontend.
9. Do not train models, download NFL data, or run feature generation in response to a frontend player search.
10. Never use an LLM to create numerical projections, historical stats, or opponent-history facts.
11. Never use random train/test splits for this forecasting problem.
12. Treat target-week data leakage as a release-blocking error.
13. Build and test the complete vertical slice in this order:

```text
backend schema audit
→ backend ingestion/normalization/schedule join/scoring
→ backend features/baseline/model/backtest/batch forecasts
→ backend API
→ football-forecast-ui API client and SPA
```

14. At completion, provide an implementation report covering:

- Backend and frontend architecture.
- Pinned package versions.
- Verified raw schemas and final mapping file.
- Data coverage and known gaps.
- PPR validation results.
- Baseline/model backtest metrics.
- API endpoint list.
- Frontend verification notes.
- Required scheduled jobs and deployment environment variables.
- Known limitations and next steps.

## 18. Definition of Done

The MVP is complete when:

1. The existing `backend/` and `football-forecast-ui/` directories contain the correctly separated backend and SPA implementations.
2. `backend/` uses a pinned `nflreadpy` version and includes a real runtime schema audit.
3. A tested, versioned source adapter maps actual nflreadpy player-stat/schedule data into canonical backend tables.
4. The backend calculates and validates full-PPR player-game labels for RB/WR/TE.
5. The backend accurately joins player games to schedules for opponent/home-away context where possible.
6. The backend trains/evaluates a leakage-safe forecast pipeline chronologically and compares against a trailing-4 baseline.
7. The backend batch-generates and persists forecasts before API reads.
8. FastAPI provides validated, read-only endpoints for player search, forecast overview, history, versus-opponent data, dashboard data, and metadata.
9. `football-forecast-ui/` provides a responsive one-page player-search experience that consumes those endpoints.
10. The SPA displays projection, matchup, recent fantasy production, usage, historical opponent results, caveats, and data freshness without claiming certainty.
11. Documentation makes local setup, data refresh, forecast generation, API serving, frontend serving, and deployment handoff reproducible.
