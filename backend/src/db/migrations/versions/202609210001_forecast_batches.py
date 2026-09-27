"""Immutable forecast snapshots and one publication per NFL week."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "202609210001"
down_revision = "202609190002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_batches",
        sa.Column("batch_id", sa.String(32), primary_key=True),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("report", postgresql.JSONB(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("status IN ('published', 'blocked')", name="batch_status"),
        sa.UniqueConstraint("season", "week", "input_hash", name="batch_input"),
    )
    op.create_index("ix_forecast_batches_season", "forecast_batches", ["season"])
    op.create_table(
        "forecast_batch_players",
        sa.Column(
            "batch_id", sa.String(32), sa.ForeignKey("forecast_batches.batch_id"), primary_key=True
        ),
        sa.Column("player_id", sa.String(64), sa.ForeignKey("players.player_id"), primary_key=True),
        sa.Column("projection", postgresql.JSONB(), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "forecast_publications",
        sa.Column("season", sa.Integer(), primary_key=True),
        sa.Column("week", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(32),
            sa.ForeignKey("forecast_batches.batch_id"),
            nullable=False,
            unique=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("forecast_publications")
    op.drop_table("forecast_batch_players")
    op.drop_table("forecast_batches")
