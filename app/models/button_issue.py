from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


BUTTON_ISSUE_TYPES = (
    "missing_handler",
    "renderer_error",
    "bad_back_target",
    "missing_back",
    "missing_home",
    "confusing_label",
    "dead_end",
    "raw_internal_label",
)
BUTTON_ISSUE_SEVERITIES = ("low", "medium", "high", "critical")
BUTTON_ISSUE_STATUSES = ("open", "resolved", "ignored")


class ButtonIssue(Base):
    __tablename__ = "button_issues"
    __table_args__ = (
        CheckConstraint(
            "issue_type in ('missing_handler', 'renderer_error', 'bad_back_target', 'missing_back', "
            "'missing_home', 'confusing_label', 'dead_end', 'raw_internal_label')",
            name="ck_button_issues_type",
        ),
        CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_button_issues_severity",
        ),
        CheckConstraint(
            "status in ('open', 'resolved', 'ignored')",
            name="ck_button_issues_status",
        ),
        Index("ix_button_issues_screen", "screen"),
        Index("ix_button_issues_status", "status"),
        Index("ix_button_issues_severity", "severity"),
        Index("ix_button_issues_detected_at", "detected_at"),
        Index("ix_button_issues_lookup", "screen", "button_label", "callback_data", "issue_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    screen: Mapped[str] = mapped_column(String(160), nullable=False)
    button_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    callback_data: Mapped[str | None] = mapped_column(String(260), nullable=True)
    issue_type: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    recommended_fix: Mapped[str] = mapped_column(Text(), nullable=False)
