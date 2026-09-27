# nflreadpy source schema audit

Audit date: 2026-09-11  
Package: `nflreadpy==0.1.5`  
Completed seasons: 2024 and 2025

## Runtime results

| Dataset | Loader | Rows | Columns |
|---|---|---:|---:|
| Weekly player statistics | `load_player_stats([2024, 2025], summary_level="week")` | 38,405 | 150 |
| Schedules | `load_schedules([2024, 2025])` | 570 | 46 |

The generated audit artifact records every runtime column, Polars dtype, null count,
loader signature, and five sample records. It is written to
`backend/data/metadata/nflreadpy-schema-audit.json` and is intentionally ignored by
Git because it contains generated source samples.

The checked-in mapping is `backend/configs/source_schema_mapping.yaml`.

## Important mapping decisions

- Stable player identity uses `player_id`; names are never keys.
- Display names use `player_display_name`, not the abbreviated `player_name`.
- Canonical `game_type` maps from player-stat `season_type` and schedule
  `game_type`.
- Canonical interceptions map from `passing_interceptions`.
- `fumbles_lost_total` is the scoring field. It must not be added to component
  fumble fields: 51 of 10,573 supported regular-season rows differed from the sum
  of rushing, receiving, and sack fumbles lost.
- `fantasy_points_ppr` is retained as a validation field rather than the canonical
  label.
- Although player statistics include `opponent_team`, the schedule join remains
  authoritative and will validate this source value.
- Schedule `gameday` and `gametime` are strings and require parsing.
- No dedicated neutral-site or game-status field was returned. Those values must
  be derived deterministically or left unavailable.

## Full-PPR validation

The PRD scoring function was evaluated across all 10,573 RB/WR/TE regular-season
rows in the two audited seasons:

- 10,386 rows matched the source PPR value exactly within floating-point tolerance.
- 187 rows differed.
- The maximum absolute difference was 8 points.

Known differences include two-point conversions, special-teams production, and
source fumble-scoring semantics, which are not part of the MVP scoring formula.
The application therefore uses its independently calculated Full-PPR value as the
model label and stores the source value only for validation.
