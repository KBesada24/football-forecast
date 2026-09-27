"""Preserve reviewed postgame evidence independently of imported game stats."""

import sqlalchemy as sa
from alembic import op

revision = "202609190002"
down_revision = "202609190001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_game_completion_evidence",
        sa.Column("evidence_id", sa.String(64), primary_key=True),
        sa.Column("player_id", sa.String(64), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_note", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.String(128), nullable=False),
        sa.CheckConstraint("status IN ('finished', 'dnf', 'dnp')", name="completion_status"),
    )
    op.create_index(
        "ix_player_game_completion_evidence_player_id",
        "player_game_completion_evidence",
        ["player_id"],
    )
    op.create_index(
        "ix_player_game_completion_evidence_game_id", "player_game_completion_evidence", ["game_id"]
    )


def downgrade() -> None:
    op.drop_table("player_game_completion_evidence")
