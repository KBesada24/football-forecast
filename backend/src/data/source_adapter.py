"""Versioned raw-to-canonical boundary for the NFL data pipeline."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from math import isclose, isfinite
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from src.data.schedule_join import ScheduleIndex
from src.data.schema_validation import SourceSchemaError, validate_source_schema
from src.domain.scoring import SCORING_VERSION, FantasyStats, calculate_full_ppr

POSITIONS = {"RB", "WR", "TE"}
STAT_FIELDS = (
    "passing_yards",
    "passing_tds",
    "interceptions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "rushing_fumbles_lost",
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "receiving_fumbles_lost",
    "sack_fumbles_lost",
    "fumbles_lost_total",
)
COMPARISON_FIELDS = (
    "source_passing_two_points",
    "source_rushing_two_points",
    "source_receiving_two_points",
    "source_special_teams_tds",
)


@dataclass
class CanonicalDataset:
    games: list[dict[str, Any]]
    players: list[dict[str, Any]]
    stats: list[dict[str, Any]]
    rosters: list[dict[str, Any]]
    participation: list[dict[str, Any]]
    report: dict[str, Any]


def canonical_records(
    frame: pl.DataFrame, mapping: dict[str, Any], dataset: str
) -> list[dict[str, Any]]:
    validate_source_schema(frame, mapping, dataset)
    expressions = []
    for name, spec in mapping["datasets"][dataset]["fields"].items():
        raw = spec.get("chosen_raw_field")
        if raw is not None:
            expressions.append((pl.col(raw) if raw in frame.columns else pl.lit(None)).alias(name))
    return frame.select(expressions).to_dicts()


def require(row: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if row.get(field) is None or row.get(field) == "":
            raise SourceSchemaError(f"Missing required value: {field} ({row.get('game_id')})")


def unique(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in seen and seen[key] != row:
            raise SourceSchemaError(f"Conflicting duplicate {keys}: {key}")
        seen[key] = row
    return list(seen.values())


def number(value: Any, name: str, *, count: bool = False) -> float:
    if value is None or isinstance(value, bool):
        raise SourceSchemaError(f"Missing/invalid numeric value: {name}")
    result = float(value)
    if not isfinite(result) or (count and (result < 0 or result != int(result))):
        raise SourceSchemaError(f"Invalid numeric value: {name}={value}")
    return result


def normalize_schedules(
    frame: pl.DataFrame, mapping: dict[str, Any], as_of: datetime
) -> list[dict[str, Any]]:
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    games = []
    for raw in canonical_records(frame, mapping, "schedules"):
        require(raw, ("game_type",))
        if raw["game_type"] != "REG":
            continue
        require(raw, ("game_id", "season", "week", "home_team", "away_team"))
        if raw["home_team"] == raw["away_team"]:
            raise SourceSchemaError("A game cannot have the same home and away team")
        day = date.fromisoformat(raw["game_date"]) if raw["game_date"] else None
        clock = time.fromisoformat(raw["game_time"]) if raw["game_time"] else None
        kickoff = (
            datetime.combine(day, clock, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
            if day and clock
            else None
        )
        scores = [raw["home_score"], raw["away_score"]]
        if any(x is None for x in scores) != all(x is None for x in scores):
            raise SourceSchemaError(f"Only one final score present: {raw['game_id']}")
        completed = all(x is not None for x in scores)
        if completed:
            for score in scores:
                number(score, "final_score", count=True)
            if kickoff is None or kickoff >= as_of:
                raise SourceSchemaError(f"Final score on undated/future game: {raw['game_id']}")
        if raw["location"] not in (None, "Home", "Neutral"):
            raise SourceSchemaError(f"Unknown location value: {raw['location']}")
        games.append(
            {
                **{
                    k: raw[k]
                    for k in (
                        "game_id",
                        "season",
                        "week",
                        "game_type",
                        "home_team",
                        "away_team",
                        "location",
                        "home_score",
                        "away_score",
                    )
                },
                "game_date": day,
                "game_time": clock,
                "game_datetime": kickoff,
                "neutral_site": None if raw["location"] is None else raw["location"] == "Neutral",
                "game_status": "completed"
                if completed
                else ("upcoming" if kickoff and kickoff > as_of else "unavailable"),
            }
        )
    return unique(games, ("game_id",))


def normalize_dataset(
    frames: dict[str, pl.DataFrame],
    mapping: dict[str, Any],
    as_of: datetime,
    artifact_id: str,
) -> CanonicalDataset:
    games = normalize_schedules(frames["schedules"], mapping, as_of)
    index = ScheduleIndex(games)
    provenance = {"source_name": "nflreadpy", "source_retrieved_at": as_of}
    report: dict[str, Any] = {
        "scoring_version": SCORING_VERSION,
        "mapping_version": mapping["mapping_version"],
        "artifact_id": artifact_id,
        "as_of": as_of.isoformat(),
        "issues": [],
        "ppr_differences": [],
        "counts": {},
    }
    raw_stats = canonical_records(frames["player_stats"], mapping, "player_stats")
    supported = [r for r in raw_stats if r["position"] in POSITIONS and r["game_type"] == "REG"]
    supported = unique(supported, ("player_id", "season", "week", "game_type"))
    stats = []
    player_rows: dict[str, dict[str, Any]] = {}

    def remember(row: dict[str, Any], roster: bool = False) -> None:
        player_id = row["player_id"]
        stamp = (row["season"], row["week"], int(roster))
        old = player_rows.get(player_id)
        if old and stamp == old["_stamp"] and old["current_team"] != row["team"]:
            raise SourceSchemaError(f"Conflicting player team context: {player_id}, {stamp}")
        if old is None or stamp > old["_stamp"]:
            player_rows[player_id] = {
                "player_id": player_id,
                "player_name": row["player_name"],
                "position": row["position"],
                "current_team": row["team"],
                "active_status": row.get("roster_status") if roster else None,
                "headshot_url": row.get("headshot_url"),
                "context_season": row["season"],
                "context_week": row["week"],
                "context_is_roster": roster,
                "_stamp": stamp,
                **provenance,
            }

    for raw in supported:
        require(raw, ("player_id", "player_name", "team", "season", "week"))
        values = {k: number(raw[k], k, count=not k.endswith("yards")) for k in STAT_FIELDS}
        if values["receptions"] > values["targets"]:
            raise SourceSchemaError("Receptions exceed targets")
        context = index.context(raw)
        game = index.match(raw)
        if game is not None and game["game_status"] != "completed":
            report["issues"].append(
                {"kind": "stats_for_uncompleted_game", "game_id": raw["game_id"]}
            )
            continue
        if game is None:
            report["issues"].append(
                {
                    "kind": "unmatched_schedule",
                    "player_id": raw["player_id"],
                    "source_game_id": raw["game_id"],
                }
            )
        score = calculate_full_ppr(
            FantasyStats(**{k: values[k] for k in FantasyStats.__dataclass_fields__})
        )
        source_score = raw["fantasy_points_ppr_source"]
        if source_score is not None:
            source_score = number(source_score, "fantasy_points_ppr_source")
            delta = source_score - score
            if not isclose(delta, 0, abs_tol=1e-6):
                components = sum(
                    values[k]
                    for k in ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost")
                )
                adjustment = None
                if all(raw[k] is not None for k in COMPARISON_FIELDS):
                    extras = {k: number(raw[k], k, count=True) for k in COMPARISON_FIELDS}
                    adjustment = (
                        2 * sum(extras[k] for k in COMPARISON_FIELDS[:3])
                        + 6 * extras["source_special_teams_tds"]
                        + 2 * (values["fumbles_lost_total"] - components)
                    )
                explained = adjustment is not None and isclose(delta, adjustment, abs_tol=1e-6)
                report["ppr_differences"].append(
                    {
                        "player_id": raw["player_id"],
                        "season": raw["season"],
                        "week": raw["week"],
                        "canonical": score,
                        "source": source_score,
                        "difference": delta,
                        "expected_difference": adjustment,
                        "explained": explained,
                        "inputs": values,
                        "source_extras": {k: raw[k] for k in COMPARISON_FIELDS},
                    }
                )
        stats.append(
            {
                **{
                    k: raw[k]
                    for k in (
                        "player_id",
                        "player_name",
                        "position",
                        "season",
                        "week",
                        "team",
                        "game_type",
                    )
                },
                **values,
                **context,
                **provenance,
                "fantasy_points_ppr": score,
                "fantasy_points_ppr_source": source_score,
                "mapping_version": str(mapping["mapping_version"]),
                "scoring_version": SCORING_VERSION,
                "data_artifact_id": artifact_id,
            }
        )
        remember(raw)

    rosters = []
    id_map: dict[str, set[str]] = {}
    for dataset in ("players", "rosters"):
        for row in canonical_records(frames[dataset], mapping, dataset):
            if row["external_player_id"] and row["player_id"]:
                id_map.setdefault(row["external_player_id"], set()).add(row["player_id"])
            if (
                dataset != "rosters"
                or row["game_type"] != "REG"
                or row["position"] not in POSITIONS | {"QB", "K"}
            ):
                continue
            if not row["player_id"]:
                report["issues"].append(
                    {
                        "kind": "roster_missing_id",
                        "season": row["season"],
                        "week": row["week"],
                        "team": row["team"],
                    }
                )
                continue
            require(row, ("player_name", "team", "season", "week"))
            rosters.append(
                {
                    **{
                        k: row[k]
                        for k in (
                            "season",
                            "week",
                            "game_type",
                            "player_id",
                            "team",
                            "position",
                            "roster_status",
                        )
                    },
                    **provenance,
                    "data_artifact_id": artifact_id,
                }
            )
            remember(row, roster=True)
    rosters = unique(rosters, ("player_id", "season", "week", "team"))

    participation = []
    stat_keys = {(r["player_id"], r["game_id"]) for r in stats}
    for row in canonical_records(frames["snap_counts"], mapping, "snap_counts"):
        if row["game_type"] != "REG" or row["position"] not in POSITIONS:
            continue
        counts = {
            k: number(row[k], k, count=True)
            for k in ("offense_snaps", "defense_snaps", "special_teams_snaps")
        }
        if sum(counts.values()) == 0:
            continue
        matches = id_map.get(row["external_player_id"], set())
        if len(matches) != 1:
            report["issues"].append(
                {
                    "kind": "unmapped_snap_player",
                    "game_id": row["game_id"],
                    "external_player_id": row["external_player_id"],
                }
            )
            continue
        row["player_id"] = next(iter(matches))
        game = index.match(row)
        if game is None or game["game_status"] != "completed":
            report["issues"].append(
                {"kind": "unmatched_or_uncompleted_snap_game", "game_id": row["game_id"]}
            )
            continue
        remember(row)
        has_stats = (row["player_id"], row["game_id"]) in stat_keys
        if not has_stats:
            report["issues"].append(
                {
                    "kind": "participation_without_stats",
                    "player_id": row["player_id"],
                    "game_id": row["game_id"],
                }
            )
        participation.append(
            {
                "player_id": row["player_id"],
                "game_id": row["game_id"],
                "team": row["team"],
                **counts,
                "has_stat_record": has_stats,
                "data_artifact_id": artifact_id,
                **provenance,
            }
        )
    participation = unique(participation, ("player_id", "game_id"))
    players = [{k: v for k, v in r.items() if k != "_stamp"} for r in player_rows.values()]
    report["counts"] = {
        "raw_stat_rows": len(raw_stats),
        "supported_stat_rows": len(supported),
        "stats": len(stats),
        "games": len(games),
        "players": len(players),
        "rosters": len(rosters),
        "participation": len(participation),
        "ppr_differences": len(report["ppr_differences"]),
        "unexplained_ppr_differences": sum(not r["explained"] for r in report["ppr_differences"]),
        **dict(Counter(r["kind"] for r in report["issues"])),
    }
    report["by_season_position"] = dict(Counter(f"{r['season']}_{r['position']}" for r in stats))
    report["completion_status"] = "unknown: postgame evidence required before averages"
    present_teams = {(r["game_id"], r["team"]) for r in stats if r["game_id"]}
    missing_teams = [
        {"game_id": game["game_id"], "team": team}
        for game in games
        if game["game_status"] == "completed"
        for team in (game["home_team"], game["away_team"])
        if (game["game_id"], team) not in present_teams
    ]
    report["completed_game_teams_without_supported_stats"] = missing_teams
    report["counts"]["completed_game_teams_without_supported_stats"] = len(missing_teams)
    return CanonicalDataset(games, players, stats, rosters, participation, report)
