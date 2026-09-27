"""Pre-target history features with explicit participation and DNF coverage gates."""

from datetime import datetime
from statistics import mean, pstdev
from typing import Any

from src.domain.completion import CompletionEvidence, completion_at

FEATURE_VERSION = "history_v2_reported_dnf_excluded"
WINDOWS = {
    "ppr_points": ("fantasy_points_ppr", (3, 4, 8)),
    "targets": ("targets", (3, 4, 8)),
    "receptions": ("receptions", (4,)),
    "carries": ("carries", (3, 4)),
    "rushing_yards": ("rushing_yards", (4,)),
    "receiving_yards": ("receiving_yards", (4,)),
    "rushing_tds": ("rushing_tds", (8,)),
    "receiving_tds": ("receiving_tds", (8,)),
}


def build_player_history(
    *,
    player_id: str,
    position: str,
    season: int,
    week: int,
    cutoff: datetime,
    stats: list[dict[str, Any]],
    participation: list[dict[str, Any]],
    evidence: list[CompletionEvidence],
) -> dict[str, Any]:
    if cutoff.tzinfo is None:
        raise ValueError("Forecast cutoff requires a timezone")
    if position not in {"RB", "WR", "TE"} or not 1 <= week <= 18:
        raise ValueError("Expected supported position and regular-season week")
    undated = [
        r
        for r in stats
        if r["player_id"] == player_id
        and r["game_type"] == "REG"
        and (r["season"], r["week"]) < (season, week)
        and (not r.get("game_id") or r.get("game_datetime") is None)
    ]
    prior = [
        r
        for r in stats
        if r["player_id"] == player_id
        and r["game_type"] == "REG"
        and (r["season"], r["week"]) < (season, week)
        and r.get("game_datetime") is not None
        and r["game_datetime"] < cutoff
    ]
    prior.sort(key=lambda r: (r["season"], r["week"], r["game_id"]))
    if len({r["game_id"] for r in prior}) != len(prior):
        raise ValueError("Duplicate player games in feature input")
    seen = {r["game_id"] for r in prior}
    missing_stats = [
        r
        for r in participation
        if r["player_id"] == player_id
        and r.get("game_type") == "REG"
        and (r["season"], r["week"]) < (season, week)
        and r.get("game_datetime") is not None
        and r["game_datetime"] < cutoff
        and r["game_id"] not in seen
    ]
    eligible = []
    unknown = 0
    dnf = 0
    for row in prior:
        status = completion_at(evidence, player_id, row["game_id"], cutoff)
        if status in ("finished", "unknown"):
            eligible.append(row)
            unknown += status == "unknown"
        elif status == "dnf":
            dnf += 1
    result: dict[str, Any] = {
        "player_id": player_id,
        "position": position,
        "season": season,
        "week": week,
        "feature_version": FEATURE_VERSION,
        "cutoff": cutoff,
        "games_played_prior": len(prior) + len({r["game_id"] for r in missing_stats}),
        "eligible_games_prior": len(eligible),
        "excluded_dnf_games": dnf,
        "unknown_completion_games": unknown,
        "missing_stat_games": len(missing_stats),
        "unavailable_reason": None,
    }
    reason = (
        "unverified_schedule" if undated else "incomplete_stat_coverage" if missing_stats else None
    )
    if not eligible and reason is None:
        reason = "insufficient_history"
    result["unavailable_reason"] = reason
    result["history_quality"] = "none" if reason else "limited" if len(eligible) < 4 else "adequate"
    for name, (field, windows) in WINDOWS.items():
        # Most recent game is an actual observation, even if that game ended early.
        if name not in ("rushing_tds", "receiving_tds"):
            result[f"{name}_prev"] = prior[-1][field] if prior and not reason else None
        for window in windows:
            result[f"{name}_avg_{window}"] = (
                mean(r[field] for r in eligible[-window:]) if not reason else None
            )
    result["ppr_points_std_4"] = (
        pstdev(r["fantasy_points_ppr"] for r in eligible[-4:]) if not reason else None
    )
    return result
