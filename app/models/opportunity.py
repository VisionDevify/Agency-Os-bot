from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

OPPORTUNITY_PLATFORMS = ("x", "instagram", "reddit", "other")
OPPORTUNITY_STATUSES = ("discovered", "reviewing", "approved", "assigned", "completed", "rejected", "archived")
OPPORTUNITY_RESULT_STATUSES = ("not_posted", "posted", "skipped", "failed")


class OpportunitySource(TimestampMixin, Base):
    __tablename__ = "opportunity_sources"
    __table_args__ = (
        CheckConstraint(
            "platform in ('x', 'instagram', 'reddit', 'other')",
            name="ck_opportunity_sources_platform",
        ),
        Index("ix_opportunity_sources_platform", "platform"),
        Index("ix_opportunity_sources_name", "name"),
        Index("ix_opportunity_sources_niche", "niche"),
        Index("ix_opportunity_sources_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opportunities: Mapped[list["Opportunity"]] = relationship(
        back_populates="source",
        lazy="selectin",
    )


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "platform in ('x', 'instagram', 'reddit', 'other')",
            name="ck_opportunities_platform",
        ),
        CheckConstraint("score >= 0 and score <= 100", name="ck_opportunities_score"),
        CheckConstraint(
            "status in ('discovered', 'reviewing', 'approved', 'assigned', 'completed', 'rejected', 'archived')",
            name="ck_opportunities_status",
        ),
        Index("ix_opportunities_source_id", "source_id"),
        Index("ix_opportunities_platform", "platform"),
        Index("ix_opportunities_model_brand_id", "model_brand_id"),
        Index("ix_opportunities_assigned_to_user_id", "assigned_to_user_id"),
        Index("ix_opportunities_status", "status"),
        Index("ix_opportunities_score", "score"),
        Index("ix_opportunities_niche", "niche"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("opportunity_sources.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_brand_id: Mapped[int | None] = mapped_column(ForeignKey("model_brands.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="discovered", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    suggested_angle: Mapped[str | None] = mapped_column(Text(), nullable=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[OpportunitySource | None] = relationship(back_populates="opportunities", lazy="selectin")
    model_brand: Mapped["ModelBrand | None"] = relationship("ModelBrand", lazy="selectin")
    assigned_to: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_to_user_id], lazy="selectin")


class OpportunityResult(TimestampMixin, Base):
    __tablename__ = "opportunity_results"
    __table_args__ = (
        CheckConstraint(
            "status in ('not_posted', 'posted', 'skipped', 'failed')",
            name="ck_opportunity_results_status",
        ),
        Index("ix_opportunity_results_opportunity_id", "opportunity_id"),
        Index("ix_opportunity_results_posted_by_user_id", "posted_by_user_id"),
        Index("ix_opportunity_results_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="not_posted", nullable=False)
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    opportunity: Mapped[Opportunity] = relationship(lazy="selectin")
    posted_by: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id], lazy="selectin")
