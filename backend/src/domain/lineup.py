"""Exact bounded roster optimizer. No data fetching, model inference or writes."""

from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slot = Literal["QB", "RB", "WR", "TE", "FLEX", "K", "DST"]
DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DST"]
ELIGIBILITY = {slot: {slot} for slot in DEFAULT_SLOTS}
ELIGIBILITY["FLEX"] = {"RB", "WR", "TE"}


class LineupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season: int = Field(ge=2024, le=2100)
    week: int = Field(ge=1, le=18)
    snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    roster: list[str] = Field(min_length=1, max_length=30)
    slots: list[Slot] = Field(
        default_factory=lambda: DEFAULT_SLOTS.copy(), min_length=1, max_length=12
    )
    excluded: list[str] = Field(default_factory=list, max_length=30)
    # Slot index -> player ID; a lock is an explicit user preference, not kickoff locking.
    locks: dict[int, str] = Field(default_factory=dict, max_length=12)

    @model_validator(mode="after")
    def consistent(self):
        if len(set(self.roster)) != len(self.roster):
            raise ValueError("Roster contains duplicate players")
        if any(not 1 <= len(pid) <= 64 for pid in self.roster):
            raise ValueError("Invalid player ID")
        if not set(self.excluded).issubset(self.roster):
            raise ValueError("Excluded players must be on your roster")
        if len(set(self.locks.values())) != len(self.locks):
            raise ValueError("A player cannot be locked into multiple slots")
        for index, pid in self.locks.items():
            if not 0 <= index < len(self.slots) or pid not in self.roster:
                raise ValueError("Lock must reference an existing slot and roster player")
            if pid in self.excluded:
                raise ValueError("A locked player cannot also be excluded")
        return self


def optimize(request: LineupRequest, players: list[dict]) -> dict:
    by_id = {p["id"]: p for p in players}
    unknown = set(request.roster) - by_id.keys()
    if unknown:
        raise ValueError("Some roster players are absent from this week's dataset; re-add them")
    usable = {
        pid: by_id[pid]
        for pid in request.roster
        if pid not in request.excluded
        and by_id[pid].get("projection") is not None
        and not by_id[pid].get("unavailable_reason")
    }
    for slot, pid in request.locks.items():
        if pid not in usable or usable[pid]["position"] not in ELIGIBILITY[request.slots[slot]]:
            raise ValueError("A locked player is unavailable or ineligible for that slot")

    # Process players once; DP over occupied slots is O(roster * slots * 2^slots),
    # not exponential in roster size. Fill as many slots as possible, then maximize points.
    ordered = sorted(usable)
    locked_ids = set(request.locks.values())

    @cache
    def solve(player_index: int, mask: int) -> tuple[int, float, tuple[tuple[int, str], ...]]:
        if player_index == len(ordered):
            return (0, 0.0, ())
        pid = ordered[player_index]
        best = solve(player_index + 1, mask)
        for i, slot in enumerate(request.slots):
            if mask & (1 << i) or usable[pid]["position"] not in ELIGIBILITY[slot]:
                continue
            if i in request.locks and request.locks[i] != pid:
                continue
            if pid in locked_ids and request.locks.get(i) != pid:
                continue
            count, score, assignment = solve(player_index + 1, mask | (1 << i))
            candidate = (count + 1, score + usable[pid]["projection"], ((i, pid),) + assignment)
            if candidate[:2] > best[:2]:
                best = candidate
        return best

    count, score, assignment = solve(0, 0)
    assigned = dict(assignment)
    starters = [
        {
            "slot": slot,
            "index": i,
            "player": usable.get(assigned.get(i)),
            "locked": i in request.locks,
        }
        for i, slot in enumerate(request.slots)
    ]
    chosen = set(assigned.values())
    bench = []
    for pid in request.roster:
        if pid in chosen:
            continue
        player = by_id[pid]
        alternatives = [
            s
            for s in starters
            if s["player"] and not s["locked"] and player["position"] in ELIGIBILITY[s["slot"]]
        ]
        gap = (
            min(s["player"]["projection"] for s in alternatives) - player["projection"]
            if alternatives and pid in usable
            else None
        )
        bench.append(
            {
                "player": player,
                "reason": "Manually excluded"
                if pid in request.excluded
                else player.get("unavailable_reason") or "Lower projected lineup total",
                "gap": round(gap, 2) if gap is not None else None,
            }
        )
    return {
        "complete": count == len(request.slots),
        "total": round(score, 2),
        "starters": starters,
        "bench": bench,
        "missing_slots": [s["slot"] for s in starters if s["player"] is None],
    }
