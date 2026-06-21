from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


SEARCH_QUERY_TYPES = (
    "opportunity",
    "platform_signal",
    "niche_research",
    "competitor_research",
    "trend_monitoring",
    "validation",
    "notification_trigger",
    "coo_context",
)

SEARCH_QUERY_STATUSES = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "not_configured",
)

SEARCH_RESULT_SOURCE_TYPES = (
    "website",
    "news",
    "social_public",
    "forum_public",
    "unknown",
)

SEARCH_RESULT_EVIDENCE_STRENGTHS = ("weak", "medium", "strong")

SEARCH_RESULT_USED_FOR = (
    "opportunity",
    "notification",
    "coo_briefing",
    "validation",
    "research",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class ExternalSearchQuery(TimestampMixin, Base):
    __tablename__ = "external_search_queries"
    __table_args__ = (
        CheckConstraint(
            "query_type in ('opportunity', 'platform_signal', 'niche_research', 'competitor_research', "
            "'trend_monitoring', 'validation', 'notification_trigger', 'coo_context')",
            name="ck_external_search_queries_type",
        ),
        CheckConstraint(
            "status in ('pending', 'running', 'succeeded', 'failed', 'skipped', 'not_configured')",
            name="ck_external_search_queries_status",
        ),
        Index("ix_external_search_queries_provider", "provider"),
        Index("ix_external_search_queries_type", "query_type"),
        Index("ix_external_search_queries_status", "status"),
        Index("ix_external_search_queries_requested_at", "requested_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    query_text: Mapped[str] = mapped_column(Text(), nullable=False)
    query_type: Mapped[str] = mapped_column(String(60), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    safe_error_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    results: Mapped[list["ExternalSearchResult"]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ExternalSearchResult(TimestampMixin, Base):
    __tablename__ = "external_search_results"
    __table_args__ = (
        CheckConstraint(
            "source_type in ('website', 'news', 'social_public', 'forum_public', 'unknown')",
            name="ck_external_search_results_source_type",
        ),
        CheckConstraint(
            "evidence_strength in ('weak', 'medium', 'strong')",
            name="ck_external_search_results_strength",
        ),
        CheckConstraint(
            "used_for in ('opportunity', 'notification', 'coo_briefing', 'validation', 'research')",
            name="ck_external_search_results_used_for",
        ),
        CheckConstraint("relevance_score >= 0 and relevance_score <= 100", name="ck_external_search_results_relevance"),
        CheckConstraint("freshness_score >= 0 and freshness_score <= 100", name="ck_external_search_results_freshness"),
        CheckConstraint("credibility_score >= 0 and credibility_score <= 100", name="ck_external_search_results_credibility"),
        CheckConstraint("risk_score >= 0 and risk_score <= 100", name="ck_external_search_results_risk"),
        UniqueConstraint("provider", "result_hash", name="uq_external_search_results_provider_hash"),
        Index("ix_external_search_results_query", "query_id"),
        Index("ix_external_search_results_domain", "source_domain"),
        Index("ix_external_search_results_retrieved_at", "retrieved_at"),
        Index("ix_external_search_results_strength", "evidence_strength"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("external_search_queries.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    display_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snippet: Mapped[str] = mapped_column(Text(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    relevance_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credibility_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(20), default="weak", nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    used_for: Mapped[str] = mapped_column(String(40), default="research", nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    query: Mapped[ExternalSearchQuery] = relationship(back_populates="results")
