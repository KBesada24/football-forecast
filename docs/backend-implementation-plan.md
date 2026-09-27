# Backend implementation plan

## Latest change — September 21, 2026

The user removed the blanket completion-verification requirement. This supersedes
earlier requirements below that block averages/forecasts on unknown completion.
Recorded stat appearances now count unless DNF/DNP is reported; confirmed DNFs
remain excluded and genuine zero-point appearances still count. Unknown is not
rewritten as confirmed finished. Missing stats/schedule and publication-cutoff
checks remain in force. Unreported early exits may remain in averages.

The UI game log now includes completed results through the selected week. This is
an explicit display option only: forecast features and opponent pregame context
continue excluding target-week outcomes. No past forecast is fabricated/backdated.

Product defaults accepted: September 16, 2026.
Season coverage and weekly workflow clarified: September 18, 2026.
Postgame injury-review timing clarified: September 19, 2026.

This document defines the intended implementation. Progress as of September 21:
the source adapter, schedule join, scoring comparison, checksummed snapshots,
transactional Postgres ingestion, roster/participation persistence, and source
quality reports are implemented and exercised on 2024–2026 data. Reviewed postgame
evidence storage/import and history/baseline functions are also implemented.
Immutable baseline publications, blended matchup rankings, and the read-only
player API are implemented; real publication is still gated by source/evidence
coverage. The frontend, trained model, and deployed scheduler remain pending.
See [the implementation report](backend-implementation-status.md) for verification
and limitations. Milestones below are requirements, not a claim that all work is done.

## Accepted product decisions

1. **Scoring:** use the formula in `MRD.md` unchanged, version it, and display its
   rules. Two-point conversions and return touchdowns remain excluded. Do not
   claim compatibility with every platform's Full-PPR settings. Source PPR is a
   comparison value, not the canonical training label.
2. **Participation:** forecasts assume the player participates. They are not
   availability-adjusted. Make this limitation visible and return unavailable
   for known ineligible players. Missing source rows do not establish zero-point
   appearances; audit participation coverage before claiming otherwise. Only
   games the player actually played and did not leave early count toward averages.
   Exclude games with no participation, including inactive/DNP games and byes,
   and exclude games started but not finished (DNF), as clarified September 18.
   Include an eligible zero-point appearance only when statistical coverage
   supports that score. Keep DNF actual statistics in raw/canonical history;
   exclude those games from rolling averages and the four-game baseline.
   Verify a source for early exits and whether the player returned; low snaps,
   routine substitutions, and the absence of a stat row do not prove DNF. Unknown
   completion status must remain unknown, not silently become a finished game.
   Postgame confirmation from official team or NFL.com reporting is sufficient;
   live injury detection is not required. Review completed-game exit/return reports
   during Tuesday's refresh, before using those games in the upcoming forecast.
   Evidence need not have existed before or during the game being classified.
   For example, a Monday report confirming a Sunday DNF may exclude that Sunday
   game from the upcoming week's average. Preserve the source URL and relevant
   publication/update and retrieval times for traceability. A report that merely
   mentions an injury does not establish that the player failed to return.
3. **Weekly refresh and cutoff:** start the weekly data refresh on Tuesday at
   08:00 America/New_York (Eastern local time, observing daylight saving), as
   selected September 16, 2026. Refresh completed games from the preceding NFL
   week, including its Thursday, Sunday, and Monday games, and any other scheduled
   game days. Resolve weeks from the NFL schedule rather than filtering weekday
   names. Update roster and upcoming matchup context, recompute historical
   features, and run the existing approved model or baseline for the upcoming NFL
   week. Publish a new weekly snapshot only after the complete batch succeeds; 08:00 is
   the job start, not a promise of instant publication. Use completed prior-week
   games and a recorded cutoff before the target week's first game. Verify source
   freshness and expected completed-game coverage rather than assuming Tuesday's
   download is complete. On delayed or incomplete inputs, retain the last good
   batch and report the delay. Never substitute another week's batch for the
   selected week; return pending/unavailable instead. Record actual snapshot/cutoff times on retries.
   Jobs may run manually in development. Preserve published forecast values and
   cutoffs after source corrections. This schedule is specified, not deployed.
4. **Eligibility and history:** audit a roster source and combine it with the
   target-week schedule. Return unavailable for zero-history players for both
   baseline and ML initially. Preserve history across trades and seasons, but use
   verified target-week team membership for upcoming matchup context. Rolling
   averages use verified games played without an early exit; never insert zeros
   for byes or missing rows. Keep total prior appearances and eligible-history
   counts separate; history quality and the baseline use the eligible count.
   "No history" means no usable history in the imported dataset, not necessarily
   no NFL career appearances.
5. **Promotion:** overall MAE is the primary metric. Report RMSE, Spearman rank
   correlation, per-position metrics, sample sizes, coverage, and limited-history
   performance. Establish numeric improvement and position-regression guardrails
   using development data, then freeze them before examining the final holdout.
   Continue serving the baseline if improvement is inconclusive or criteria fail.
6. **Publication and corrections:** retain the last successful dataset and
   forecast batch when a job fails. Block publication on identity conflicts,
   ambiguous scoring semantics, or invalid required fields. Report other gaps.
   Reconcile removed records only within a validated, complete import scope;
   never treat a partial source response as proof that records were removed.
7. **Season coverage:** import 2024, 2025, and 2026. The current 2026 season is
   incomplete: only completed games before the target-week cutoff contribute
   statistics, while future schedule rows provide upcoming matchup context.
   Use recent 2026 and 2025 appearances first in rolling history, with 2024 retained
   as older history when needed. Never treat unplayed 2026 games as zero outcomes.
8. **Refresh versus training:** Tuesday jobs use new inputs with the existing
   approved model parameters; they do not retrain. Training/evaluation/promotion
   is a separate explicit workflow. A baseline's average and a model's predictions
   can change as new completed games enter the feature history without retraining.

9. **Best-matchup ranking:** the user selected a mix of projected fantasy points
   and opponent favorability. Initial implementation default: equal weighting of
   within-position percentile ranks for the two components. Show projected PPR,
   opponent favorability, and the combined rank separately. This is a ranking
   score, not an additional fantasy-point prediction or a causal matchup effect.
   Compare RB with RB, WR with WR, and TE with TE initially.

For the initial opponent component, evaluate PPR allowed to the relevant position
per verified appearance over the opponent's last four completed team games before
the cutoff. Use the same scoring definition, report game/appearance sample sizes,
and rank higher allowances as more favorable. Preserve actual points allowed,
including DNF production, because those outcomes occurred. Use available prior
games when fewer than four exist and flag limited history. Missing or unverified
coverage makes the combined rank unavailable; do not substitute neutral/zero
favorability. Keep the individual player forecast visible when otherwise valid.
This descriptive signal is not adjusted for the strength of past opponents and
must not be labeled a quantified causal boost. Freeze ranking rules before
evaluating them. The equal weighting and initial signal are engineering defaults,
not claims that these choices have already demonstrated predictive value.

DNF exclusion affects history features, not historical truth or future eligibility:
a previous early exit does not automatically rule a player out next week. For
training/evaluation, retain actual outcomes for participating target-week players,
including later DNFs. Do not filter targets using hindsight about whether they
finished. Build pre-target averages using only eligible prior games: recorded stat
appearances count unless reviewed evidence reports DNF or DNP. Missing completion
evidence leaves an appearance eligible, counted separately as unknown, never as
confirmed completion. Do not substitute an unapproved proxy such as a snap-count
threshold.
For historical evaluation, distinguish postgame evidence available before the
next forecast from evidence first published after that forecast. This is a
backtest-reproducibility concern, not a requirement for live injury monitoring.

Historical evaluations based on subsequently corrected source data are
retrospective evaluations. Retrieval time, historical feature cutoff, and actual
source availability are distinct concepts and must not be presented as equivalent.

## Milestone 1: mapping and scoring contract

1. Start local Postgres, apply migrations, and establish the existing test result.
2. Separate pure unit tests from database migration fixtures. Validate that
   integration tests target the dedicated test database before writing to it.
3. Extend `backend/configs/source_schema_mapping.yaml` with transformations, null
   policies, scoring semantics, dictionary references, and verification tests.
4. Verify the source total fumbles-lost meaning against its dictionary and
   representative records. Never combine a total with its components.
5. Turn the exploratory source-PPR comparison into a reproducible report with
   per-row inputs, differences, supported explanations, and unexplained cases.
6. Verify schedule timezone, neutral-site semantics, and completion evidence.
   Keep unsupported context unavailable.
   Audit participation and roster sources here, including stable-ID joins and
   evidence for zero-point appearances and confirmed early exits/returns, before
   normalization and feature work. Audit coverage across 2024, 2025, and 2026.
7. Test missing columns, ambiguous scoring fields, null handling, zero scores,
   mixed production, interceptions, fumbles, and legitimate negative values.

Exit: verified scoring-critical semantics, explicit mapping/null rules, and a
reproducible scoring report. The prior audit's 187 differences are observations
to investigate, not a blanket exemption from validation.

## Milestone 2: ingestion and persistence

1. Add `src/data/ingestion.py` to load requested seasons with pinned nflreadpy.
   Include 2024, 2025, and completed 2026 games. Extend the runtime schema audit
   to 2026 before normalizing it; the existing audit only verified 2024 and 2025.
   Retain upcoming schedule entries separately from completed player statistics.
2. Save raw Parquet snapshots and manifests with checksums, retrieval time,
   package/loader details, and artifact IDs, separate from the mutable cache.
3. Add `src/data/source_adapter.py` to validate and normalize RB/WR/TE regular-season
   records, retain stable IDs, apply the verified null policy, and attach provenance.
   Reconcile verified participation with scoring coverage so eligible zero-point
   appearances are retained and nonparticipation does not enter averages as zero.
   Store completion/early-exit status and supporting provenance independently of
   actual scored statistics; preserve unknown states explicitly.
4. Collapse identical duplicates; reject conflicting duplicate keys explicitly.
5. Add `src/data/schedule_join.py`: use shared game ID first, verify team membership,
   and use a unique season/week/game-type/team fallback only when needed. Handle
   neutral sites before home/away labels. Report unmatched and contradictory rows.
6. Calculate canonical PPR and retain source PPR separately.
7. Persist teams, players, games, and player-game stats in dependency order using
   transactional upserts. Older imports must not regress current player metadata.
8. Record successful and failed ingestion runs independently of data rollback.
   Define complete-snapshot reconciliation before handling source removals.
9. Add `src/jobs/ingest_seasons.py` with season selection and validation-only mode.

Proposed interface from `backend/` (not implemented yet):

```bash
python -m src.jobs.ingest_seasons --seasons 2024 2025 2026
```

Exit: one repeatable import command, traceable data artifacts, and no duplicate
player-game rows on rerun.

## Milestone 3: database and data-quality verification

1. Verify identities, foreign keys, canonical uniqueness, team membership, and
   opponent consistency.
2. Validate finite values and valid count domains while allowing legitimate
   negative yardage and fantasy points. Recalculate persisted PPR.
3. Test home, away, neutral, unmatched, and ambiguous joins without row multiplication.
4. Test repeated imports, source corrections, older-season imports, complete-scope
   removals, and rollback on failure. A failed run must preserve the last good data.
5. Report counts by season/position, exclusions, duplicates, nulls, schedule coverage,
   scoring differences, artifact IDs, and blocking versus nonblocking findings.
6. Compare results with the audit's 10,573 supported rows without hard-coding that
   historical 2024–2025 observation as an invariant against source corrections or
   additional 2026 records. Report per-season coverage, including the incomplete
   current season. Verify DNP and DNF exclusion from averages, preserved DNF history,
   unknown completion handling, and supported zero-point appearances.

Exit: verified histories in Postgres, integration tests for reruns and failure
recovery, and an inspectable quality report.

## Milestone 4: features and baseline

1. Represent historical cutoff and source retrieval time separately.
2. Use the roster and participation sources verified in Milestone 1. Build future candidates from roster
   and schedule data, not eventual target-week statistical outcomes. Disclose the
   narrower coverage of evaluations limited to observed player-game rows.
3. Add `src/features/player_history.py` implementing the PRD's prior-game, rolling
   usage/PPR, variability, position, and prior-appearance-count features.
4. Apply the accepted cross-season, trade, bye, and missing-history rules.
5. Add `src/models/baseline.py`: mean of the last four prior appearances, mean of
   eligible history for one to three, and unavailable for zero eligible appearances.
   Here eligible means a recorded appearance with complete statistics, unless reviewed
   evidence reports DNF or DNP. Unknown completion status stays eligible but is counted
   separately (`unknown_completion_games`) and never treated as confirmed completion.
   Select the last four eligible games, skipping reported DNF games.
   Persist history
   quality as `adequate`, `limited`, or `none`, respectively.
6. Test that modifying target-week or later outcomes cannot change target-week
   features or predictions, while next-week features may change. Also test
   shuffled inputs, season boundaries, trades, and isolation between players.
7. Save immutable feature artifacts with definition versions, input artifact IDs,
   cutoffs, and timestamps. Register the baseline and persist its forecasts.
8. Add migrations as needed for scoring/feature versions, forecast cutoff and batch
   identity, unavailable reasons, and immutable published history. The current
   table skeleton does not yet implement all these lifecycle requirements.
9. Add opponent-position history summaries from completed pre-cutoff team games.
   Verify participation coverage, scoring consistency, denominator/sample counts,
   and no target-week leakage before using them for matchup ranks.

Exit: stored, reproducible baseline forecasts with passing leakage tests and
explicit eligibility/history limitations.

## Milestone 5: model evaluation and batch forecasts

1. Verify model-package compatibility with the actual Python environment. Start
   with LightGBM if compatible, pin tested dependencies, and save configuration.
2. Pair prior-only features with canonical target PPR. Exclude outcome columns and
   fit any preprocessing on training data only. Keep target-week DNF outcomes in
   evaluation/training for players who participated; prior-average exclusions
   must not select only future finishers as evaluation targets.
3. Develop with chronological splits inside 2024 and reserve 2025 as the initial
   final season holdout. Freeze configuration and promotion thresholds first.
   Imported 2026 data is used for live prediction inputs and separate forward
   monitoring, not to fit or tune the initial 2025 holdout experiment. Import scope
   does not imply that every season enters every training/evaluation run.
   Audit and validate any additional historical seasons before expanding training.
4. Run a separate walk-forward evaluation: train through the previous week and
   predict the target week. Do not conflate this with the fixed-model holdout.
5. Compare model and baseline on the same eligible rows, reporting coverage,
   exclusions, all required metrics, and per-position/history breakdowns.
6. Apply the frozen promotion criteria; retain the baseline on inconclusive or
   failed results. Do not tune against the final holdout after inspecting it.
7. Save the model, feature/scoring definitions, dependency versions, seed,
   configuration, training period, data artifact IDs, and evaluation report.
8. Add `src/jobs/generate_forecasts.py` to load the selected model or baseline,
   generate pre-target predictions, and publish a complete batch atomically.
   The Tuesday workflow refreshes prior-week inputs and upcoming matchups and
   publishes a new snapshot without training or automatically promoting a model.
   Include per-position best-matchup rankings, both component values and their
   sample sizes, the ranking-definition version, and unavailable reasons. Compute
   ranks only after the eligible forecast cohort is complete. Test deterministic
   ties, missing components, and position isolation.
   Preserve published predictions; source corrections must not overwrite them.
9. Verify save/reload equivalence, reproducibility within documented tolerances,
   rerun behavior, cutoff enforcement, and last-good-batch retention on failure.

Exit: a reproducible evaluation report and versioned forecasts ready for API reads.

## Remaining engineering decisions

These do not reopen the accepted product defaults:

- Verify reliable early-exit/return-to-game coverage for all three seasons. DNF
  exclusion is accepted; the source that can support it has not yet been verified.
- Verify source field semantics, zero-production participation coverage, and roster
  timestamps using actual data and authoritative dictionaries.
- Specify numeric promotion thresholds from development results before holdout use.
- Implement the agreed Tuesday 08:00 America/New_York refresh in deployment,
  including daylight-saving handling, freshness checks, and failure/retry behavior.
- Finalize batch/version storage and complete-snapshot reconciliation mechanics.

Next milestones after this plan: read-only product API endpoints, frontend
integration, and deployment preparation. Local development/testing continues to
use Postgres; the intended production database remains Supabase Postgres.

## Source capabilities and refresh timing

Documentation checked September 16, 2026:

- [nflreadpy loaders](https://nflreadpy.nflverse.com/api/load_functions/) expose
  player statistics, schedules, weekly rosters, and snap counts. Remaining source
  work is to verify and join these datasets, not to invent participation facts.
- [Weekly rosters](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html)
  provide week-level roster history. A roster status is not proof of game participation
  or an exact timestamp of when the status became known.
- [Snap counts](https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html)
  include offensive, defensive, and special-teams snaps. Their PFR player IDs need
  verified mapping to our canonical player IDs before combining records.
- The [upstream update schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
  documents nightly player-stat updates after game days and daily roster updates.
  Snap-count delivery depends on PFR. Detailed participation data from 2023 onward
  arrives after the postseason, so it cannot be a required in-season input.
  Later stat corrections are expected; Tuesday snapshots are not guaranteed final.

Keep Tuesday as the chosen primary refresh. No additional weekly refresh has
been authorized or scheduled. Show the actual successful data timestamp to users.
