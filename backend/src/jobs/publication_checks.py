"""Small, deterministic launch gates; no downloads, DB writes, or model training."""

from collections import Counter
from datetime import datetime, time, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from src.domain.espn import POSITIONS

EASTERN = ZoneInfo("America/New_York")


class NoPublicationWindow(ValueError):
    """Outside the supported regular-season publication window."""


class CoverageError(ValueError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__("Lineup publication blocked; see coverage-report.json")


def target_week(games: list[dict], season: int, now: datetime) -> int:
    """Use this Tuesday–Monday NFL window, never skip to a later available week."""
    local = now.astimezone(EASTERN)
    start_day = local.date() - timedelta(days=(local.weekday() - 1) % 7)
    start = datetime.combine(start_day, time(), EASTERN)
    end = start + timedelta(days=7)
    scheduled = [g for g in games if g["season"] == season and 1 <= g["week"] <= 18]
    dated = [g for g in scheduled if g.get("game_datetime")]
    if not dated:
        raise ValueError("Supported season schedule is absent or has no kickoff times")
    weeks = {g["week"] for g in dated if start <= g["game_datetime"] < end}
    if not weeks:
        if end <= min(g["game_datetime"] for g in dated) or start > max(
            g["game_datetime"] for g in dated
        ):
            raise NoPublicationWindow("No regular-season publication window this Tuesday period")
        raise ValueError("Intended week is missing from the schedule; operator review required")
    if len(weeks) != 1:
        raise ValueError("Ambiguous NFL week in publication window; operator review required")
    return weeks.pop()


def coverage_report(inputs: dict, payload: dict, now: datetime) -> dict:
    season, week = payload["season"], payload["week"]
    errors = []
    previous = [g for g in inputs["games"] if (g["season"], g["week"]) == (season, week - 1)]
    missing = []
    if week > 1:
        if not previous:
            errors.append("Previous NFL week is missing from the schedule")
        for game in previous:
            if (
                game["game_status"] != "completed"
                or not game["game_datetime"]
                or game["game_datetime"] >= now
            ):
                errors.append(f"Previous-week game is not confirmed completed: {game['game_id']}")
    scored = [
        r
        for r in inputs["rows"]
        if not r.get("missing")
        and isinstance(r.get("points"), (int, float))
        and isfinite(r["points"])
    ]
    positions_by_team = {}
    for row in scored:
        positions_by_team.setdefault((row["game_id"], row["team"]), set()).add(row["position"])
    for game in previous:
        for team in (game["home_team"], game["away_team"]):
            positions = positions_by_team.get((game["game_id"], team), set())
            required = []
            if not positions.intersection({"QB", "RB", "WR", "TE"}):
                required.append("offense")
            if "DST" not in positions:
                required.append("DST/team statistics/play-by-play")
            if required:
                missing.append({"game_id": game["game_id"], "team": team, "missing": required})
    if missing:
        errors.append("Previous-week team scoring coverage is incomplete")
    # One team may legitimately have no kicker scoring row. A missing entire K feed is different.
    previous_ids = {g["game_id"] for g in previous}
    if previous and not any(r["position"] == "K" and r["game_id"] in previous_ids for r in scored):
        errors.append("Previous-week kicking data is absent")
    counts = {
        pos: sum(
            p["position"] == pos
            and isinstance(p.get("projection"), (int, float))
            and isfinite(p["projection"])
            and not p.get("unavailable_reason")
            for p in payload["players"]
        )
        for pos in POSITIONS
    }
    for pos, count in counts.items():
        if not count:
            errors.append(f"No usable projections for {pos}")
    return {
        "season": season,
        "week": week,
        "status": "blocked" if errors else "passed",
        "previous_week_games": len(previous),
        "week_one_history_only": week == 1,
        "missing_team_inputs": missing,
        "projected_by_position": counts,
        "excluded_players": dict(
            Counter(
                p["unavailable_reason"] for p in payload["players"] if p.get("unavailable_reason")
            )
        ),
        "errors": errors,
        "limits": "Checks observed schedule and position-level coverage, not individual "
        "injury health or completeness against an independent schedule provider.",
    }
