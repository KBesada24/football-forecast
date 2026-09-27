"""Reviewed evidence, not snap-count thresholds, determines completion status."""

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class CompletionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str = Field(min_length=1, max_length=64)
    game_id: str = Field(min_length=1, max_length=64)
    status: Literal["finished", "dnf", "dnp"]
    source_url: HttpUrl
    source_published_at: AwareDatetime
    source_updated_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime
    reviewed_at: AwareDatetime
    evidence_note: str = Field(min_length=10, max_length=4000)
    reviewer: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def chronology(self):
        updated = self.source_updated_at or self.source_published_at
        if not self.source_published_at <= updated <= self.retrieved_at <= self.reviewed_at:
            raise ValueError("Evidence timestamps must follow publication/update/retrieval/review")
        return self

    @property
    def evidence_id(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def completion_at(
    evidence: list[CompletionEvidence], player_id: str, game_id: str, cutoff: datetime
) -> str:
    eligible = [
        e
        for e in evidence
        if e.player_id == player_id and e.game_id == game_id and e.reviewed_at <= cutoff
    ]
    if not eligible:
        return "unknown"
    # A later review of an older article must not override a newer source update.
    newest_time = max(e.source_updated_at or e.source_published_at for e in eligible)
    statuses = {
        e.status for e in eligible if (e.source_updated_at or e.source_published_at) == newest_time
    }
    return statuses.pop() if len(statuses) == 1 else "unknown"
