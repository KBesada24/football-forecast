"""Audited full-position inputs. Raw supplements are preserved, never downloaded by APIs."""

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import nflreadpy as nfl
import polars as pl
from nflreadpy.config import update_config

from src.core.config import BACKEND_DIR
from src.data.ingestion import read_snapshot, sha256, write_json
from src.data.schema_validation import load_schema_mapping
from src.data.source_adapter import normalize_schedules
from src.domain.espn import POSITIONS, defense_points, number, player_points


def supplement(root: Path, seasons: list[int]) -> None:
    """A separate manifest preserves backwards compatibility with five-file snapshots."""
    if (root / "lineup-manifest.json").exists():
        return
    update_config(cache_mode="off", verbose=False)
    metadata = {}
    for name, loader in (("team_stats", nfl.load_team_stats), ("pbp", nfl.load_pbp)):
        frame = loader(seasons)
        path = root / f"lineup-{name}.parquet"
        frame.write_parquet(path)
        metadata[name] = {
            "sha256": sha256(path),
            "rows": frame.height,
            "retrieved_at": datetime.now(UTC).isoformat(),
        }
    write_json(root / "lineup-manifest.json", metadata)


def defense_inputs(team: dict, opponent: dict, game: dict, plays: list[dict]) -> dict:
    """PBP disambiguates offensive vs defensive scores/recoveries and PAT exceptions."""
    code = team["team"]
    other = opponent["team"]
    final = game["home_score"] if other == game["home_team"] else game["away_score"]
    for side in ("home", "away"):
        values = {p[f"{side}_score"] for p in plays if p[f"{side}_score"] is not None}
        if values != {game[f"{side}_score"]}:
            raise ValueError(f"PBP final score disagrees with schedule: {game['game_id']}")
    values = {
        "points_allowed": final,
        "yards_allowed": number(opponent, "passing_yards")
        + number(opponent, "rushing_yards")
        - abs(number(opponent, "sack_yards_lost")),
        "sacks": number(team, "def_sacks"),
        "interceptions": number(team, "def_interceptions"),
        "blocked_kicks": sum(
            number(team, k) for k in ("def_punt_blocks", "def_pat_blocks", "def_fg_blocks")
        ),
        "recoveries": 0,
        "touchdowns": 0,
        "safeties": 0,
        "conversion_returns": 0,
        "pat_safeties": 0,
    }
    for p in plays:
        special = any(
            p.get(k) == 1 for k in ("kickoff_attempt", "punt_attempt", "field_goal_attempt")
        )
        conversion = p.get("extra_point_attempt") == 1 or p.get("two_point_attempt") == 1
        if p.get("touchdown") == 1 and not conversion:
            defensive = p.get("td_team") != p.get("posteam") and not special
            if p.get("td_team") == other and defensive:
                values["points_allowed"] -= 6
            if p.get("td_team") == code and (defensive or special):
                values["touchdowns"] += 1
        for n in (1, 2):
            if (
                p.get(f"fumble_recovery_{n}_team") == code
                and p.get(f"fumbled_{n}_team") == other
                and (special or p.get("defteam") == code)
                and not conversion
            ):
                values["recoveries"] += 1
        if p.get("safety") == 1:
            if p.get("defteam") == code:
                values["pat_safeties" if conversion else "safeties"] += 1
            if p.get("posteam") == code and not special:
                values["points_allowed"] -= 1 if conversion else 2
        if p.get("defteam") == code and (
            p.get("defensive_two_point_conv") == 1 or p.get("defensive_extra_point_conv") == 1
        ):
            values["conversion_returns"] += 1
    return values


def load_inputs(root: Path) -> dict:
    import json

    frames, manifest = read_snapshot(root)
    extras = json.loads((root / "lineup-manifest.json").read_text())
    for name in ("team_stats", "pbp"):
        path = root / f"lineup-{name}.parquet"
        if sha256(path) != extras[name]["sha256"]:
            raise ValueError(f"Lineup supplement checksum mismatch: {name}")
        frames[name] = pl.read_parquet(path)
        if frames[name].height != extras[name]["rows"]:
            raise ValueError("Lineup supplement row count mismatch")
    as_of = datetime.fromisoformat(manifest["retrieved_at"])
    mapping = load_schema_mapping(BACKEND_DIR / "configs/source_schema_mapping.yaml")
    games = normalize_schedules(frames["schedules"], mapping, as_of)
    completed = {g["game_id"]: g for g in games if g["game_status"] == "completed"}
    rows = []
    seen = set()
    for r in frames["player_stats"].iter_rows(named=True):
        if r["season_type"] != "REG" or r["position"] not in POSITIONS:
            continue
        if r["game_id"] not in completed:
            continue
        key = (r["player_id"], r["game_id"])
        if key in seen:
            raise ValueError(f"Duplicate player game: {key}")
        seen.add(key)
        g = completed[r["game_id"]]
        if {r["team"], r["opponent_team"]} != {g["home_team"], g["away_team"]}:
            raise ValueError("Player team/opponent does not match schedule")
        rows.append(
            {
                "id": r["player_id"],
                "name": r["player_display_name"],
                "position": r["position"],
                "team": r["team"],
                "opponent": r["opponent_team"],
                "game_id": r["game_id"],
                "season": r["season"],
                "week": r["week"],
                "kickoff": g["game_datetime"],
                "points": player_points(r),
                "targets": number(r, "targets"),
                "carries": number(r, "carries"),
                "attempts": number(r, "attempts"),
                "missing": False,
            }
        )
    # Snaps prove participation, not a zero score. Missing recent scoring rows remain holes.
    pfr_ids = {
        r["pfr_id"]: r["gsis_id"]
        for r in frames["rosters"].iter_rows(named=True)
        if r["pfr_id"] and r["gsis_id"]
    }
    for r in frames["players"].iter_rows(named=True):
        if r.get("pfr_id") and r.get("gsis_id"):
            pfr_ids[r["pfr_id"]] = r["gsis_id"]
    for r in frames["snap_counts"].iter_rows(named=True):
        pid = pfr_ids.get(r["pfr_player_id"])
        if (
            not pid
            or r["position"] not in POSITIONS
            or r["game_id"] not in completed
            or (pid, r["game_id"]) in seen
            or not sum(r.get(k) or 0 for k in ("offense_snaps", "defense_snaps", "st_snaps"))
        ):
            continue
        g = completed[r["game_id"]]
        rows.append(
            {
                "id": pid,
                "name": r["player"],
                "position": r["position"],
                "team": r["team"],
                "opponent": r["opponent"],
                "game_id": r["game_id"],
                "season": r["season"],
                "week": r["week"],
                "kickoff": g["game_datetime"],
                "points": None,
                "targets": 0,
                "carries": 0,
                "attempts": 0,
                "missing": True,
            }
        )
        seen.add((pid, r["game_id"]))
    teams = {
        (r["game_id"], r["team"]): r
        for r in frames["team_stats"].iter_rows(named=True)
        if r["season_type"] == "REG"
    }
    # Collect only fields used by the adapter, avoiding a large 372-column Python copy.
    pbp_columns = [
        "game_id",
        "play_id",
        "home_score",
        "away_score",
        "posteam",
        "defteam",
        "td_team",
        "touchdown",
        "safety",
        "kickoff_attempt",
        "punt_attempt",
        "field_goal_attempt",
        "extra_point_attempt",
        "two_point_attempt",
        "defensive_two_point_conv",
        "defensive_extra_point_conv",
        "fumble_recovery_1_team",
        "fumble_recovery_2_team",
        "fumbled_1_team",
        "fumbled_2_team",
    ]
    pbp = defaultdict(list)
    for r in frames["pbp"].select(pbp_columns).unique(["game_id", "play_id"]).iter_rows(named=True):
        if r["game_id"] in completed:
            pbp[r["game_id"]].append(r)
    missing_defense = []
    for gid, g in completed.items():
        for team, opponent in ((g["home_team"], g["away_team"]), (g["away_team"], g["home_team"])):
            if (gid, team) not in teams or (gid, opponent) not in teams or not pbp[gid]:
                missing_defense.append(f"{gid}:{team}")
                continue
            values = defense_inputs(teams[gid, team], teams[gid, opponent], g, pbp[gid])
            rows.append(
                {
                    "id": f"DST:{team}",
                    "name": f"{team} D/ST",
                    "position": "DST",
                    "team": team,
                    "opponent": opponent,
                    "game_id": gid,
                    "season": g["season"],
                    "week": g["week"],
                    "kickoff": g["game_datetime"],
                    "points": defense_points(values),
                    "targets": 0,
                    "carries": 0,
                    "attempts": 0,
                    "missing": False,
                    "scoring_inputs": values,
                }
            )
    return {
        "games": games,
        "rows": rows,
        "rosters": frames["rosters"].to_dicts(),
        "artifact": manifest["artifact_id"],
        "as_of": as_of.isoformat(),
        "supplement_as_of": max(v["retrieved_at"] for v in extras.values()),
        "audit": {
            "scored_games": sum(not r["missing"] for r in rows),
            "missing_player_games": sum(r["missing"] for r in rows),
            "missing_defense_games": missing_defense,
        },
    }
