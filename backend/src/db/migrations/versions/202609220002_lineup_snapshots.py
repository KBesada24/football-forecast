"""Versioned complete-lineup projections, separate from legacy RB/WR/TE forecasts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "202609220002"
down_revision = "202609220001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lineup_snapshots",
        sa.Column("snapshot_id", sa.String(32), primary_key=True),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_lineup_snapshots_season", "lineup_snapshots", ["season"])
    op.execute("""CREATE FUNCTION forbid_lineup_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'Lineup snapshots are append-only'; END; $$""")
    op.execute("""CREATE TRIGGER immutable_lineup_snapshot BEFORE UPDATE OR DELETE
        ON lineup_snapshots FOR EACH ROW EXECUTE FUNCTION forbid_lineup_snapshot_mutation()""")


def downgrade():
    op.drop_table("lineup_snapshots")
    op.execute("DROP FUNCTION forbid_lineup_snapshot_mutation()")
