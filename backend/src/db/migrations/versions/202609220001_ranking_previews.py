"""Separate refreshable preliminary rankings from published forecasts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "202609220001"
down_revision = "202609210002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ranking_previews",
        sa.Column("season", sa.Integer(), primary_key=True),
        sa.Column("week", sa.Integer(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )


def downgrade():
    op.drop_table("ranking_previews")
