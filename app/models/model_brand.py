from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.user import User

MODEL_BRAND_STATUSES = ("active", "warning", "disabled", "archived")
MODEL_BRAND_RELATIONSHIP_TYPES = (
    "manager",
    "chatter_manager",
    "senior_chatter",
    "chatter",
    "va",
    "viewer",
)


class ModelBrand(TimestampMixin, Base):
    __tablename__ = "model_brands"
    __table_args__ = (
        CheckConstraint(
            "status in ('active', 'warning', 'disabled', 'archived')",
            name="ck_model_brands_status",
        ),
        Index("ix_model_brands_display_name", "display_name"),
        Index("ix_model_brands_stage_name", "stage_name"),
        Index("ix_model_brands_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    stage_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    members: Mapped[list["ModelBrandMember"]] = relationship(
        back_populates="model_brand",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ModelBrandMember(Base):
    __tablename__ = "model_brand_members"
    __table_args__ = (
        CheckConstraint(
            "relationship_type in "
            "('manager', 'chatter_manager', 'senior_chatter', 'chatter', 'va', 'viewer')",
            name="ck_model_brand_members_relationship_type",
        ),
        UniqueConstraint(
            "model_brand_id",
            "user_id",
            "relationship_type",
            name="uq_model_brand_members_model_user_type",
        ),
        Index("ix_model_brand_members_model_brand_id", "model_brand_id"),
        Index("ix_model_brand_members_user_id", "user_id"),
        Index("ix_model_brand_members_relationship_type", "relationship_type"),
    )

    model_brand_id: Mapped[int] = mapped_column(
        ForeignKey("model_brands.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_brand: Mapped[ModelBrand] = relationship(back_populates="members", lazy="selectin")
    user: Mapped[User] = relationship(lazy="selectin")
