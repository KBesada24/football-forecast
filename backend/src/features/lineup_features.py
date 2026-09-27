"""Five eligible appearances, workload, shrunk positional defense and head-to-head.

All queries use games strictly before the target week/kickoff. Corrected historical
inputs are simulations, not a claim of archived point-in-time availability.
"""

from collections import defaultdict
from statistics import mean

from src.domain.completion import completion_at

FEATURE_VERSION = "lineup_history5_matchup_v1"


class FeatureIndex:
    def __init__(self, rows: list[dict], evidence: list | None = None):
        self.by_player = defaultdict(list)
        self.pos_games = defaultdict(dict)
        self.evidence = defaultdict(list)
        for item in evidence or []:
            self.evidence[item.player_id].append(item)
        for r in sorted(rows, key=lambda r: r["kickoff"], reverse=True):
            self.by_player[r["id"]].append(r)
            key = (r["opponent"], r["position"])
            game = self.pos_games[key].setdefault(
                r["game_id"],
                {
                    "season": r["season"],
                    "week": r["week"],
                    "kickoff": r["kickoff"],
                    "total": 0.0,
                    "missing": 0,
                },
            )
            game["missing"] += int(r["missing"])
            game["total"] += r["points"] or 0

    def build(
        self, pid: str, position: str, opponent: str | None, season: int, week: int, cutoff
    ) -> dict:
        def before(r):
            return (r["season"], r["week"]) < (season, week) and r["kickoff"] < cutoff

        history = [
            r
            for r in self.by_player[pid]
            if before(r)
            and completion_at(self.evidence[pid], pid, r["game_id"], cutoff) not in {"dnf", "dnp"}
        ]
        recent = history[:5]
        valid = [r for r in recent if not r["missing"]]
        unavailable = (
            "Missing scoring data in the latest five appearances"
            if len(valid) != len(recent)
            else "No eligible game history"
            if not recent
            else None
        )
        avg = mean(r["points"] for r in valid) if valid else None
        weighted = (
            sum(r["points"] * (len(valid) - i) for i, r in enumerate(valid))
            / sum(range(1, len(valid) + 1))
            if valid
            else None
        )
        meetings = [r for r in history if not r["missing"] and r["opponent"] == opponent]
        # Sample-weighted residual, not an automatic bonus for a single big game.
        h2h = mean(r["points"] for r in meetings) if meetings else None
        h2h_weighted = (
            sum(r["points"] / (1 + season - r["season"]) for r in meetings)
            / sum(1 / (1 + season - r["season"]) for r in meetings)
            if meetings
            else avg
        )
        league_games = [
            g
            for (team, pos), games in self.pos_games.items()
            if pos == position
            for g in games.values()
            if before(g) and not g["missing"]
        ]
        # Actual positional totals include DNF outcomes; they describe the opposing unit.
        recent_league = sorted(league_games, key=lambda g: g["kickoff"], reverse=True)[:256]
        league = mean(g["total"] for g in recent_league) if recent_league else None
        defense = sorted(
            [g for g in self.pos_games[opponent, position].values() if before(g)],
            key=lambda g: g["kickoff"],
            reverse=True,
        )[:8]
        usable = [g for g in defense if not g["missing"]]
        defense_avg = mean(g["total"] for g in usable) if usable else None
        # Shrink eight-game context to league; recent five get one extra observation weight.
        recent_def = [g for g in defense[:5] if not g["missing"]]
        smoothed = (
            (sum(g["total"] for g in usable + recent_def) + 8 * league)
            / (len(usable) + len(recent_def) + 8)
            if usable and league
            else league
        )
        relative = smoothed / league - 1 if smoothed is not None and league else 0
        workload = {
            key: mean(r[key] for r in valid) if valid else 0
            for key in ("targets", "carries", "attempts")
        }
        broader = [r for r in history[:8] if not r["missing"]]
        avg8 = mean(r["points"] for r in broader) if broader else avg
        return {
            "average5": avg,
            "weighted5": weighted,
            "average8": avg8,
            "sample": len(valid),
            "unavailable_reason": unavailable,
            "last5": [{k: r[k] for k in ("season", "week", "opponent", "points")} for r in valid],
            "workload": workload,
            "head_to_head": {"average": h2h, "sample": len(meetings)},
            "defense": {
                "average": defense_avg,
                "league_average": league,
                "sample": len(usable),
                "missing_games": len(defense) - len(usable),
                "relative": round(relative, 4),
            },
            "vector": [
                avg or 0,
                (weighted or 0) - (avg or 0),
                (avg8 or 0) - (avg or 0),
                workload["targets"],
                workload["carries"],
                workload["attempts"],
                relative * (avg or 0),
                ((h2h_weighted or 0) - (avg or 0)) * len(meetings) / (len(meetings) + 5),
                len(valid),
            ],
        }
