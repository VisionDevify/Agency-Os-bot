from datetime import datetime

from sqlalchemy import DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemHeartbeat(Base):
    __tablename__ = "system_heartbeats"
    __table_args__ = (
        Index("ix_system_heartbeats_service_name", "service_name", unique=True),
        Index("ix_system_heartbeats_status", "status"),
        Index("ix_system_heartbeats_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
