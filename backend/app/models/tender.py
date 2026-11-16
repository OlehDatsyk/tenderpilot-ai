"""Tenders, documents, stored files, requirements, AI runs and bid assessments."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDMixin


class Tender(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tenders"
    __table_args__ = (
        Index("ix_tenders_org_status", "organization_id", "status"),
        Index("ix_tenders_org_deadline", "organization_id", "submission_deadline"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    buyer: Mapped[str] = mapped_column(String(300), default="")
    reference: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tender_type: Mapped[str] = mapped_column(String(30), default="tender")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    submission_deadline: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    documents: Mapped[list[Document]] = relationship(back_populates="tender", cascade="all, delete-orphan", passive_deletes=True)
    requirements: Mapped[list[Requirement]] = relationship(back_populates="tender", cascade="all, delete-orphan", passive_deletes=True)


class StoredFile(UUIDMixin, TimestampMixin, Base):
    """Binary blob storage in PostgreSQL (persistent on platforms with ephemeral disks)."""

    __tablename__ = "stored_files"

    key: Mapped[str] = mapped_column(String(255), unique=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    file_ext: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    status_message: Mapped[str] = mapped_column(Text, default="")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # [{"page": int|None, "label": str, "text": str}]
    pages: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    tender: Mapped[Tender] = relationship(back_populates="documents")


class AnalysisRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_tender_kind", "tender_id", "kind"),)

    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    provider: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Requirement(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "requirements"
    __table_args__ = (Index("ix_requirements_tender_status", "tender_id", "response_status"),)

    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="other")
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    source_document_name: Mapped[str] = mapped_column(String(255), default="")
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    origin: Mapped[str] = mapped_column(String(20), default="manual")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_status: Mapped[str] = mapped_column(String(30), default="not_started")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    comments: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    tender: Mapped[Tender] = relationship(back_populates="requirements")


class BidAssessment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bid_assessments"

    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation: Mapped[str] = mapped_column(String(20))
    score: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text, default="")
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    advantages: Mapped[list[str]] = mapped_column(JSON, default=list)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_information: Mapped[list[str]] = mapped_column(JSON, default=list)
    next_steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    final_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    final_reasoning: Mapped[str] = mapped_column(Text, default="")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
