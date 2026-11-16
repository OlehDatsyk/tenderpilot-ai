"""Proposals, tasks, comments, assistant messages and activity events."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDMixin, utcnow


class ProposalDraft(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "proposal_drafts"

    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="draft")

    sections: Mapped[list[ProposalSection]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="ProposalSection.position",
        passive_deletes=True,
    )


class ProposalSection(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "proposal_sections"

    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposal_drafts.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requirements.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    guidance: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    last_ai_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True)

    proposal: Mapped[ProposalDraft] = relationship(back_populates="sections")


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_org_status_due", "organization_id", "status", "due_date"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    tender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=True, index=True)
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requirements.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="todo")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    comments: Mapped[list[TaskComment]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskComment.created_at", passive_deletes=True
    )


class TaskComment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "task_comments"

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text)

    task: Mapped[Task] = relationship(back_populates="comments")


class AssistantMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (Index("ix_assistant_tender_user", "tender_id", "user_id", "created_at"),)

    tender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    supported: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)


class ActivityEvent(UUIDMixin, Base):
    __tablename__ = "activity_events"
    __table_args__ = (Index("ix_activity_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    tender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
