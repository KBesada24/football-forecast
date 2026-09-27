"""Protect snapshots from modification and allow reports for an empty database."""

import sqlalchemy as sa
from alembic import op

revision = "202609210002"
down_revision = "202609210001"
branch_labels = None
depends_on = None

TABLES = ("forecast_batches", "forecast_batch_players", "forecast_publications")


def upgrade():
    op.alter_column(
        "forecast_batches", "data_as_of", nullable=True, existing_type=sa.DateTime(timezone=True)
    )
    op.execute("""
        CREATE FUNCTION reject_forecast_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Forecast snapshots and publications are immutable';
        END;
        $$
    """)
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_forecast_mutation()"
        )


def downgrade():
    for table in TABLES:
        op.execute(f"DROP TRIGGER immutable_snapshot ON {table}")
    op.execute("DROP FUNCTION reject_forecast_mutation()")
    # Keep nullable: blocked attempts may have no source timestamp.
