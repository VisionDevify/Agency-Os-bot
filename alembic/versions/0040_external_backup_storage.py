"""External backup storage configuration evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_external_backup_storage"
down_revision: str | None = "0039_full_start_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TARGET_TYPES = (
    "local_runtime",
    "manual_export",
    "s3_compatible",
    "backblaze_b2",
    "google_drive",
    "cloudflare_r2",
    "azure_blob",
)


def upgrade() -> None:
    op.drop_constraint("ck_backup_storage_targets_type", "backup_storage_targets", type_="check")
    op.create_check_constraint(
        "ck_backup_storage_targets_type",
        "backup_storage_targets",
        f"target_type in {TARGET_TYPES!r}",
    )
    op.add_column("backup_storage_targets", sa.Column("encrypted_config_json", sa.Text(), nullable=True))
    op.add_column(
        "backup_storage_targets",
        sa.Column("masked_config_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "backup_storage_targets",
        sa.Column("connection_status", sa.String(length=40), server_default="not_configured", nullable=False),
    )
    op.add_column(
        "backup_storage_targets",
        sa.Column("provider_available", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("backup_storage_targets", sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backup_storage_targets", sa.Column("last_test_status", sa.String(length=40), nullable=True))
    op.add_column("backup_storage_targets", sa.Column("last_test_summary", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_backup_storage_targets_connection_status",
        "backup_storage_targets",
        "connection_status in ('not_configured', 'pending', 'active', 'failed', 'disabled')",
    )
    op.create_index(
        "ix_backup_storage_targets_connection_status",
        "backup_storage_targets",
        ["connection_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_backup_storage_targets_connection_status", table_name="backup_storage_targets")
    op.drop_constraint(
        "ck_backup_storage_targets_connection_status",
        "backup_storage_targets",
        type_="check",
    )
    op.drop_column("backup_storage_targets", "last_test_summary")
    op.drop_column("backup_storage_targets", "last_test_status")
    op.drop_column("backup_storage_targets", "last_test_at")
    op.drop_column("backup_storage_targets", "provider_available")
    op.drop_column("backup_storage_targets", "connection_status")
    op.drop_column("backup_storage_targets", "masked_config_json")
    op.drop_column("backup_storage_targets", "encrypted_config_json")
    op.drop_constraint("ck_backup_storage_targets_type", "backup_storage_targets", type_="check")
    op.create_check_constraint(
        "ck_backup_storage_targets_type",
        "backup_storage_targets",
        "target_type in ('local_runtime', 'manual_export', 's3_compatible', 'backblaze_b2', 'google_drive')",
    )
