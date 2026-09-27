"""Add source provenance, roster context and verified participation.

Revision ID: 202609190001
Revises: 202609110001
"""

import sqlalchemy as sa
from alembic import op

revision = "202609190001"
down_revision = "202609110001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players", sa.Column("context_season", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "players", sa.Column("context_week", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "players",
        sa.Column("context_is_roster", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("games", sa.Column("home_score", sa.Integer()))
    op.add_column("games", sa.Column("away_score", sa.Integer()))
    op.add_column(
        "player_game_stats",
        sa.Column("scoring_version", sa.String(32), nullable=False, server_default="full_ppr_v1"),
    )
    op.add_column(
        "player_game_stats",
        sa.Column("data_artifact_id", sa.String(128), nullable=False, server_default="legacy"),
    )
    op.add_column("data_ingestion_runs", sa.Column("data_artifact_id", sa.String(128)))
    op.create_table(
        "player_weekly_rosters",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("player_id", sa.String(64), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("game_type", sa.String(16), nullable=False),
        sa.Column("team", sa.String(8), sa.ForeignKey("teams.team_code"), nullable=False),
        sa.Column("position", sa.String(16), nullable=False),
        sa.Column("roster_status", sa.String(32)),
        sa.Column("data_artifact_id", sa.String(128), nullable=False),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("player_id", "season", "week", "team"),
    )
    op.create_index("ix_player_weekly_rosters_player_id", "player_weekly_rosters", ["player_id"])
    op.create_table(
        "player_game_participation",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("player_id", sa.String(64), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("team", sa.String(8), sa.ForeignKey("teams.team_code"), nullable=False),
        sa.Column("offense_snaps", sa.Integer(), nullable=False),
        sa.Column("defense_snaps", sa.Integer(), nullable=False),
        sa.Column("special_teams_snaps", sa.Integer(), nullable=False),
        sa.Column("has_stat_record", sa.Boolean(), nullable=False),
        sa.Column("data_artifact_id", sa.String(128), nullable=False),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("player_id", "game_id"),
    )
    op.create_index(
        "ix_player_game_participation_player_id", "player_game_participation", ["player_id"]
    )
    op.create_index(
        "ix_player_game_participation_game_id", "player_game_participation", ["game_id"]
    )


def downgrade() -> None:
    op.drop_table("player_game_participation")
    op.drop_table("player_weekly_rosters")
    op.drop_column("data_ingestion_runs", "data_artifact_id")
    op.drop_column("player_game_stats", "data_artifact_id")
    op.drop_column("player_game_stats", "scoring_version")
    op.drop_column("games", "away_score")
    op.drop_column("games", "home_score")
    op.drop_column("players", "context_is_roster")
    op.drop_column("players", "context_week")
    op.drop_column("players", "context_season")
