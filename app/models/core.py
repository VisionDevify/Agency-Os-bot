from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class NamedResource(TimestampMixin):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Account(NamedResource, Base):
    __tablename__ = "accounts"


class Proxy(NamedResource, Base):
    __tablename__ = "proxies"


class Task(NamedResource, Base):
    __tablename__ = "tasks"


class Incident(NamedResource, Base):
    __tablename__ = "incidents"


class Report(NamedResource, Base):
    __tablename__ = "reports"


class Automation(NamedResource, Base):
    __tablename__ = "automations"
