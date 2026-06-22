"""command center score snapshots

Revision ID: 0052_command_center_scores
Revises: 0051_reliability_shortcuts
Create Date: 2026-06-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0052_command_center_scores"
down_revision = "0051_reliability_shortcuts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("score_name", sa.String(length=80), nullable=False),
        sa.Column("score_percent", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("movement", sa.String(length=20), nullable=False),
        sa.Column("movement_delta", sa.Integer(), nullable=False),
        sa.Column("delta_period", sa.String(length=20), nullable=False),
        sa.Column("reason_for_change", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("evidence_version", sa.String(length=160), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("score_percent >= 0 and score_percent <= 100", name="ck_score_snapshots_percent"),
        sa.CheckConstraint("confidence in ('low', 'medium', 'high')", name="ck_score_snapshots_confidence"),
        sa.CheckConstraint("movement in ('up', 'down', 'flat')", name="ck_score_snapshots_movement"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_score_snapshots_name", "score_snapshots", ["score_name"])
    op.create_index("ix_score_snapshots_generated_at", "score_snapshots", ["generated_at"])
    op.create_index("ix_score_snapshots_evidence_version", "score_snapshots", ["evidence_version"])


def downgrade() -> None:
    op.drop_index("ix_score_snapshots_evidence_version", table_name="score_snapshots")
    op.drop_index("ix_score_snapshots_generated_at", table_name="score_snapshots")
    op.drop_index("ix_score_snapshots_name", table_name="score_snapshots")
    op.drop_table("score_snapshots")
