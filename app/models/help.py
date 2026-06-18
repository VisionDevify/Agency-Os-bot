from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

HELP_FEEDBACK_VALUES = ("helpful", "not_helpful", "still_confused")
UI_SELF_TEST_STATUSES = ("passed", "warning", "failed")


class HelpKnowledgeBase(TimestampMixin, Base):
    __tablename__ = "help_knowledge_base"
    __table_args__ = (
        Index("ix_help_knowledge_base_topic", "topic", unique=True),
        Index("ix_help_knowledge_base_role_scope", "role_scope"),
        Index("ix_help_knowledge_base_related_route", "related_route"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    role_scope: Mapped[str] = mapped_column(String(80), default="all", nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    related_route: Mapped[str | None] = mapped_column(String(160), nullable=True)


class HelpQuestionLog(Base):
    __tablename__ = "help_question_logs"
    __table_args__ = (
        CheckConstraint(
            "feedback is null or feedback in ('helpful', 'not_helpful', 'still_confused')",
            name="ck_help_question_logs_feedback",
        ),
        Index("ix_help_question_logs_user_id", "user_id"),
        Index("ix_help_question_logs_detected_intent", "detected_intent"),
        Index("ix_help_question_logs_feedback", "feedback"),
        Index("ix_help_question_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    question: Mapped[str] = mapped_column(Text(), nullable=False)
    detected_intent: Mapped[str] = mapped_column(String(120), nullable=False)
    answer_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    feedback: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class UISelfTestRun(Base):
    __tablename__ = "ui_self_test_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('passed', 'warning', 'failed')",
            name="ck_ui_self_test_runs_status",
        ),
        Index("ix_ui_self_test_runs_status", "status"),
        Index("ix_ui_self_test_runs_requested_by_user_id", "requested_by_user_id"),
        Index("ix_ui_self_test_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    screens_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
