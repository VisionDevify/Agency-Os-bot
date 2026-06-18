from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

FRICTION_SEVERITIES = ("low", "medium", "high", "critical")


class FrictionItem(Base):
    __tablename__ = "friction_items"
    __table_args__ = (
        CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_friction_items_severity",
        ),
        Index("ix_friction_items_screen", "screen"),
        Index("ix_friction_items_severity", "severity"),
        Index("ix_friction_items_discovered_at", "discovered_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    screen: Mapped[str] = mapped_column(String(120), nullable=False)
    issue: Mapped[str] = mapped_column(Text(), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="medium", nullable=False)
    fix_recommendation: Mapped[str] = mapped_column(Text(), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
