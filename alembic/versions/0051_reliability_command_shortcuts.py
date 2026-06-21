"""reliability instrumentation and command shortcuts

Revision ID: 0051_reliability_command_shortcuts
Revises: 0050_agency_awareness
Create Date: 2026-06-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0051_reliability_command_shortcuts"
down_revision = "0050_agency_awareness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "callback_latency_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("callback_route", sa.String(length=220), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("render_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("render_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edit_or_send_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("ack_latency_ms", sa.Integer(), nullable=True),
        sa.Column("render_latency_ms", sa.Integer(), nullable=True),
        sa.Column("db_latency_ms", sa.Integer(), nullable=True),
        sa.Column("ai_latency_ms", sa.Integer(), nullable=True),
        sa.Column("search_latency_ms", sa.Integer(), nullable=True),
        sa.Column("backup_latency_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("latency_label", sa.String(length=20), nullable=False),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "result in ('succeeded', 'fallback_used', 'failed_safe', 'timed_out', 'stale', 'duplicate')",
            name="ck_callback_latency_records_result",
        ),
        sa.CheckConstraint(
            "latency_label in ('excellent', 'good', 'slow', 'bad', 'dead')",
            name="ck_callback_latency_records_label",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_callback_latency_records_route", "callback_latency_records", ["callback_route"])
    op.create_index("ix_callback_latency_records_result", "callback_latency_records", ["result"])
    op.create_index("ix_callback_latency_records_label", "callback_latency_records", ["latency_label"])
    op.create_index("ix_callback_latency_records_received_at", "callback_latency_records", ["received_at"])

    op.create_table(
        "reliability_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=120), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("current_step", sa.String(length=160), nullable=False),
        sa.Column("related_chat_id", sa.String(length=80), nullable=True),
        sa.Column("related_message_id", sa.String(length=80), nullable=True),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'checking', 'uploading', 'verifying', 'summarizing', "
            "'completed', 'failed', 'timed_out', 'cancelled')",
            name="ck_reliability_jobs_status",
        ),
        sa.CheckConstraint(
            "progress_percent is null or (progress_percent >= 0 and progress_percent <= 100)",
            name="ck_reliability_jobs_progress",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_reliability_jobs_job_id", "reliability_jobs", ["job_id"], unique=True)
    op.create_index("ix_reliability_jobs_type", "reliability_jobs", ["job_type"])
    op.create_index("ix_reliability_jobs_status", "reliability_jobs", ["status"])
    op.create_index("ix_reliability_jobs_started_at", "reliability_jobs", ["started_at"])

    op.create_table(
        "response_cache_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cache_key", sa.String(length=180), nullable=False),
        sa.Column("evidence_version", sa.String(length=120), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_commit", sa.String(length=80), nullable=True),
        sa.Column("safe_summary", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("contains_sensitive_data", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index("ix_response_cache_entries_key", "response_cache_entries", ["cache_key"], unique=True)
    op.create_index("ix_response_cache_entries_expires", "response_cache_entries", ["expires_at"])
    op.create_index("ix_response_cache_entries_source_commit", "response_cache_entries", ["source_commit"])


def downgrade() -> None:
    op.drop_index("ix_response_cache_entries_source_commit", table_name="response_cache_entries")
    op.drop_index("ix_response_cache_entries_expires", table_name="response_cache_entries")
    op.drop_index("ix_response_cache_entries_key", table_name="response_cache_entries")
    op.drop_table("response_cache_entries")
    op.drop_index("ix_reliability_jobs_started_at", table_name="reliability_jobs")
    op.drop_index("ix_reliability_jobs_status", table_name="reliability_jobs")
    op.drop_index("ix_reliability_jobs_type", table_name="reliability_jobs")
    op.drop_index("ix_reliability_jobs_job_id", table_name="reliability_jobs")
    op.drop_table("reliability_jobs")
    op.drop_index("ix_callback_latency_records_received_at", table_name="callback_latency_records")
    op.drop_index("ix_callback_latency_records_label", table_name="callback_latency_records")
    op.drop_index("ix_callback_latency_records_result", table_name="callback_latency_records")
    op.drop_index("ix_callback_latency_records_route", table_name="callback_latency_records")
    op.drop_table("callback_latency_records")
