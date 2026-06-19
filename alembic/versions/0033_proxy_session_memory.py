"""proxy session memory

Revision ID: 0033_proxy_session_memory
Revises: 0032_social_opp_intel
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0033_proxy_session_memory"
down_revision: str | None = "0032_social_opp_intel"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "proxy_session_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proxy_id", sa.Integer(), nullable=False),
        sa.Column("session_suffix_hash", sa.String(length=128), nullable=False),
        sa.Column("session_suffix_masked", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source in ('created', 'imported', 'rotated', 'rollback')",
            name="ck_proxy_session_memory_source",
        ),
        sa.ForeignKeyConstraint(["proxy_id"], ["proxies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proxy_session_memory_proxy_id", "proxy_session_memory", ["proxy_id"])
    op.create_index("ix_proxy_session_memory_suffix_hash", "proxy_session_memory", ["session_suffix_hash"])
    op.create_index("ix_proxy_session_memory_used_at", "proxy_session_memory", ["used_at"])
    op.create_index("ix_proxy_session_memory_proxy_used", "proxy_session_memory", ["proxy_id", "used_at"])


def downgrade() -> None:
    op.drop_index("ix_proxy_session_memory_proxy_used", table_name="proxy_session_memory")
    op.drop_index("ix_proxy_session_memory_used_at", table_name="proxy_session_memory")
    op.drop_index("ix_proxy_session_memory_suffix_hash", table_name="proxy_session_memory")
    op.drop_index("ix_proxy_session_memory_proxy_id", table_name="proxy_session_memory")
    op.drop_table("proxy_session_memory")
