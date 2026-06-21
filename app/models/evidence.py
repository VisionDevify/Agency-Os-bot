from __future__ import annotations

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


EVIDENCE_TYPES = (
    "owner_note",
    "owner_validation",
    "system_record",
    "uploaded_reference",
    "operational_outcome",
)

EVIDENCE_STRENGTHS = ("weak", "medium", "strong")

OWNER_VALIDATION_OUTCOMES = (
    "correct",
    "incorrect",
    "partially_correct",
    "too_early",
    "add_evidence",
)

KNOWLEDGE_CONFIDENCE = ("low", "medium", "high")


class EvidenceRecord(TimestampMixin, Base):
    __tablename__ = "evidence_records"
    __table_args__ = (
        CheckConstraint(
            "evidence_type in ('owner_note', 'owner_validation', 'system_record', 'uploaded_reference', 'operational_outcome')",
            name="ck_evidence_records_type",
        ),
        CheckConstraint(
            "evidence_strength in ('weak', 'medium', 'strong')",
            name="ck_evidence_records_strength",
        ),
        Index("ix_evidence_records_type", "evidence_type"),
        Index("ix_evidence_records_category", "category"),
        Index("ix_evidence_records_prediction", "linked_prediction_id"),
        Index("ix_evidence_records_decision", "linked_decision_id"),
        Index("ix_evidence_records_recommendation", "linked_recommendation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    linked_prediction_id: Mapped[int | None] = mapped_column(
        ForeignKey("predictive_coo_predictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_decision_id: Mapped[str | None] = mapped_column(String(220), nullable=True)
    linked_recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    details: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evidence_strength: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class OwnerValidation(TimestampMixin, Base):
    __tablename__ = "owner_validations"
    __table_args__ = (
        CheckConstraint(
            "validation_outcome in ('correct', 'incorrect', 'partially_correct', 'too_early', 'add_evidence')",
            name="ck_owner_validations_outcome",
        ),
        Index("ix_owner_validations_prediction", "linked_prediction_id"),
        Index("ix_owner_validations_decision", "linked_decision_id"),
        Index("ix_owner_validations_recommendation", "linked_recommendation_id"),
        Index("ix_owner_validations_outcome", "validation_outcome"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    linked_prediction_id: Mapped[int | None] = mapped_column(
        ForeignKey("predictive_coo_predictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_decision_id: Mapped[str | None] = mapped_column(String(220), nullable=True)
    linked_recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    validation_outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class KnowledgeMemory(TimestampMixin, Base):
    __tablename__ = "knowledge_memory"
    __table_args__ = (
        CheckConstraint(
            "confidence in ('low', 'medium', 'high')",
            name="ck_knowledge_memory_confidence",
        ),
        Index("ix_knowledge_memory_category", "category"),
        Index("ix_knowledge_memory_confidence", "confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    lesson: Mapped[str] = mapped_column(Text(), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    evidence_record_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    source_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
