from dataclasses import dataclass
from math import isfinite

SCORING_VERSION = "full_ppr_v1"


@dataclass(frozen=True, slots=True)
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
    for name in stats.__dataclass_fields__:
        value = getattr(stats, name)
        if not isfinite(value):
            raise ValueError(f"Non-finite scoring value: {name}")
        if not name.endswith("yards") and (value < 0 or value != int(value)):
            raise ValueError(f"Invalid scoring count: {name}")
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
