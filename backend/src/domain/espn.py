"""Versioned ESPN public full-PPR preset; legacy full_ppr_v1 stays unchanged.

Source: ESPN Scoring Formats and D/ST Scoring (2026-08-18).
Yardage tiers: ESPN Chicago 2025 championship rules, Appendix A.
Source adapters must supply every field; an absent value is never a zero.
"""

from math import isfinite

SCORING_VERSION = "espn_full_ppr_2026_v1"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
OFFENSE = {
    "passing_yards": 0.04,
    "passing_tds": 4,
    "passing_interceptions": -2,
    "rushing_yards": 0.1,
    "rushing_tds": 6,
    "receptions": 1,
    "receiving_yards": 0.1,
    "receiving_tds": 6,
    "fumbles_lost_total": -2,
    "passing_2pt_conversions": 2,
    "rushing_2pt_conversions": 2,
    "receiving_2pt_conversions": 2,
    "special_teams_tds": 6,
    "fumble_recovery_tds": 6,
}
KICKING = {
    "fg_made_0_19": 3,
    "fg_made_20_29": 3,
    "fg_made_30_39": 3,
    "fg_made_40_49": 4,
    "fg_made_50_59": 5,
    "fg_made_60_": 6,
    "pat_made": 1,
}


def number(row: dict, name: str) -> float:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError(f"Missing or invalid scoring field: {name}")
    return float(value)


def player_points(row: dict) -> float:
    result = sum(number(row, key) * weight for key, weight in OFFENSE.items())
    # Blocked attempts are a separate nflverse outcome, also missed for ESPN.
    if row["position"] == "K":
        result += sum(number(row, key) * weight for key, weight in KICKING.items())
        result -= number(row, "fg_att") - number(row, "fg_made")
    return round(result, 4)


def tier(value: float, tiers: tuple[tuple[float, int], ...]) -> int:
    return next(points for ceiling, points in tiers if value <= ceiling)


def defense_points(row: dict) -> float:
    pa = number(row, "points_allowed")
    ya = number(row, "yards_allowed")
    if pa < 0:
        raise ValueError("Points allowed cannot be negative")
    points = tier(
        pa, ((0, 5), (6, 4), (13, 3), (17, 1), (27, 0), (34, -1), (45, -3), (float("inf"), -5))
    )
    points += tier(
        ya,
        (
            (99, 5),
            (199, 3),
            (299, 2),
            (349, 0),
            (399, -1),
            (449, -3),
            (499, -5),
            (549, -6),
            (float("inf"), -7),
        ),
    )
    weights = {
        "sacks": 1,
        "interceptions": 2,
        "recoveries": 2,
        "blocked_kicks": 2,
        "safeties": 2,
        "touchdowns": 6,
        "conversion_returns": 2,
        "pat_safeties": 1,
    }
    return points + sum(number(row, key) * weight for key, weight in weights.items())
