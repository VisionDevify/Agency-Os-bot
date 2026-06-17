"""learning engine playbook memory

Revision ID: 0016_learning_engine
Revises: 0015_automation_builder
Create Date: 2026-06-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_learning_engine"
down_revision: str | None = "0015_automation_builder"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_OBJECT = sa.text("'{}'::json")
JSON_ARRAY = sa.text("'[]'::json")


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="info"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "source_type in ('task', 'incident', 'proxy', 'account', 'automation', 'recommendation', "
            "'opportunity', 'notification', 'system')",
            name="ck_learning_events_source_type",
        ),
        sa.CheckConstraint(
            "outcome in ('success', 'failure', 'partial', 'ignored', 'unknown')",
            name="ck_learning_events_outcome",
        ),
        sa.CheckConstraint(
            "severity in ('info', 'warning', 'critical')",
            name="ck_learning_events_severity",
        ),
        sa.CheckConstraint(
            "confidence_score is null or (confidence_score >= 0 and confidence_score <= 100)",
            name="ck_learning_events_confidence",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_events_type", "learning_events", ["event_type"])
    op.create_index("ix_learning_events_source", "learning_events", ["source_type", "source_id"])
    op.create_index("ix_learning_events_entity", "learning_events", ["entity_type", "entity_id"])
    op.create_index("ix_learning_events_outcome", "learning_events", ["outcome"])
    op.create_index("ix_learning_events_severity", "learning_events", ["severity"])
    op.create_index("ix_learning_events_created_by_user_id", "learning_events", ["created_by_user_id"])
    op.create_index("ix_learning_events_created_at", "learning_events", ["created_at"])

    op.create_table(
        "playbooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("trigger_summary", sa.Text(), nullable=False),
        sa.Column("diagnosis_steps_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
        sa.Column("resolution_steps_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
        sa.Column("verification_steps_json", sa.JSON(), nullable=False, server_default=JSON_ARRAY),
        sa.Column("rollback_steps_json", sa.JSON(), nullable=True),
        sa.Column("risk_level", sa.String(length=40), nullable=False, server_default="low"),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "category in ('proxy', 'account', 'task', 'incident', 'automation', 'notification', 'opportunity', 'system')",
            name="ck_playbooks_category",
        ),
        sa.CheckConstraint(
            "risk_level in ('low', 'medium', 'high', 'critical')",
            name="ck_playbooks_risk_level",
        ),
        sa.CheckConstraint(
            "status in ('draft', 'active', 'needs_review', 'retired')",
            name="ck_playbooks_status",
        ),
        sa.CheckConstraint("confidence_score >= 0 and confidence_score <= 100", name="ck_playbooks_confidence"),
        sa.CheckConstraint("success_count >= 0", name="ck_playbooks_success_count"),
        sa.CheckConstraint("failure_count >= 0", name="ck_playbooks_failure_count"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_playbooks_name"),
    )
    op.create_index("ix_playbooks_category", "playbooks", ["category"])
    op.create_index("ix_playbooks_risk_level", "playbooks", ["risk_level"])
    op.create_index("ix_playbooks_status", "playbooks", ["status"])
    op.create_index("ix_playbooks_confidence", "playbooks", ["confidence_score"])
    op.create_index("ix_playbooks_created_by_user_id", "playbooks", ["created_by_user_id"])

    op.create_table(
        "playbook_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playbook_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=True),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="suggested"),
        sa.Column("started_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confidence_before", sa.Integer(), nullable=True),
        sa.Column("confidence_after", sa.Integer(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("safe_metadata_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status in ('suggested', 'approved', 'running', 'succeeded', 'failed', 'skipped', 'rolled_back')",
            name="ck_playbook_runs_status",
        ),
        sa.CheckConstraint(
            "confidence_before is null or (confidence_before >= 0 and confidence_before <= 100)",
            name="ck_playbook_runs_confidence_before",
        ),
        sa.CheckConstraint(
            "confidence_after is null or (confidence_after >= 0 and confidence_after <= 100)",
            name="ck_playbook_runs_confidence_after",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_playbook_runs_playbook_id", "playbook_runs", ["playbook_id"])
    op.create_index("ix_playbook_runs_source", "playbook_runs", ["source_type", "source_id"])
    op.create_index("ix_playbook_runs_status", "playbook_runs", ["status"])
    op.create_index("ix_playbook_runs_started_by_user_id", "playbook_runs", ["started_by_user_id"])
    op.create_index("ix_playbook_runs_approved_by_user_id", "playbook_runs", ["approved_by_user_id"])
    op.create_index("ix_playbook_runs_created_at", "playbook_runs", ["created_at"])
    op.create_index("ix_playbook_runs_finished_at", "playbook_runs", ["finished_at"])

    op.create_table(
        "outcome_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("memory_key", sa.String(length=240), nullable=False),
        sa.Column("memory_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ignored_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_outcome", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "memory_type in ('proxy_failure', 'account_issue', 'incident_pattern', 'automation_result', "
            "'recommendation_result', 'opportunity_result', 'notification_failure', 'task_overdue', 'system_health')",
            name="ck_outcome_memory_type",
        ),
        sa.CheckConstraint(
            "last_outcome in ('success', 'failure', 'partial', 'ignored', 'unknown')",
            name="ck_outcome_memory_last_outcome",
        ),
        sa.CheckConstraint("occurrences >= 0", name="ck_outcome_memory_occurrences"),
        sa.CheckConstraint("success_count >= 0", name="ck_outcome_memory_success_count"),
        sa.CheckConstraint("failure_count >= 0", name="ck_outcome_memory_failure_count"),
        sa.CheckConstraint("partial_count >= 0", name="ck_outcome_memory_partial_count"),
        sa.CheckConstraint("ignored_count >= 0", name="ck_outcome_memory_ignored_count"),
        sa.CheckConstraint("success_rate >= 0 and success_rate <= 100", name="ck_outcome_memory_success_rate"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_key", name="uq_outcome_memory_key"),
    )
    op.create_index("ix_outcome_memory_type", "outcome_memory", ["memory_type"])
    op.create_index("ix_outcome_memory_entity", "outcome_memory", ["entity_type", "entity_id"])
    op.create_index("ix_outcome_memory_last_outcome", "outcome_memory", ["last_outcome"])
    op.create_index("ix_outcome_memory_success_rate", "outcome_memory", ["success_rate"])
    op.create_index("ix_outcome_memory_last_seen_at", "outcome_memory", ["last_seen_at"])

    op.create_table(
        "confidence_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=80), nullable=False),
        sa.Column("subject_id", sa.String(length=120), nullable=False),
        sa.Column("previous_score", sa.Integer(), nullable=True),
        sa.Column("new_score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=JSON_OBJECT),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "subject_type in ('recommendation', 'playbook', 'automation', 'proxy', 'opportunity', "
            "'intelligence_signal', 'issue_pattern')",
            name="ck_confidence_records_subject_type",
        ),
        sa.CheckConstraint(
            "previous_score is null or (previous_score >= 0 and previous_score <= 100)",
            name="ck_confidence_records_previous_score",
        ),
        sa.CheckConstraint("new_score >= 0 and new_score <= 100", name="ck_confidence_records_new_score"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_confidence_records_subject", "confidence_records", ["subject_type", "subject_id"])
    op.create_index("ix_confidence_records_created_at", "confidence_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_confidence_records_created_at", table_name="confidence_records")
    op.drop_index("ix_confidence_records_subject", table_name="confidence_records")
    op.drop_table("confidence_records")

    op.drop_index("ix_outcome_memory_last_seen_at", table_name="outcome_memory")
    op.drop_index("ix_outcome_memory_success_rate", table_name="outcome_memory")
    op.drop_index("ix_outcome_memory_last_outcome", table_name="outcome_memory")
    op.drop_index("ix_outcome_memory_entity", table_name="outcome_memory")
    op.drop_index("ix_outcome_memory_type", table_name="outcome_memory")
    op.drop_table("outcome_memory")

    op.drop_index("ix_playbook_runs_finished_at", table_name="playbook_runs")
    op.drop_index("ix_playbook_runs_created_at", table_name="playbook_runs")
    op.drop_index("ix_playbook_runs_approved_by_user_id", table_name="playbook_runs")
    op.drop_index("ix_playbook_runs_started_by_user_id", table_name="playbook_runs")
    op.drop_index("ix_playbook_runs_status", table_name="playbook_runs")
    op.drop_index("ix_playbook_runs_source", table_name="playbook_runs")
    op.drop_index("ix_playbook_runs_playbook_id", table_name="playbook_runs")
    op.drop_table("playbook_runs")

    op.drop_index("ix_playbooks_created_by_user_id", table_name="playbooks")
    op.drop_index("ix_playbooks_confidence", table_name="playbooks")
    op.drop_index("ix_playbooks_status", table_name="playbooks")
    op.drop_index("ix_playbooks_risk_level", table_name="playbooks")
    op.drop_index("ix_playbooks_category", table_name="playbooks")
    op.drop_table("playbooks")

    op.drop_index("ix_learning_events_created_at", table_name="learning_events")
    op.drop_index("ix_learning_events_created_by_user_id", table_name="learning_events")
    op.drop_index("ix_learning_events_severity", table_name="learning_events")
    op.drop_index("ix_learning_events_outcome", table_name="learning_events")
    op.drop_index("ix_learning_events_entity", table_name="learning_events")
    op.drop_index("ix_learning_events_source", table_name="learning_events")
    op.drop_index("ix_learning_events_type", table_name="learning_events")
    op.drop_table("learning_events")
