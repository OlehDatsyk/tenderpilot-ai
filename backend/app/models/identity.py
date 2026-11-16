"""Users, organisations, memberships, invitations, refresh tokens and org-level settings."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDMixin


class Organization(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))

    memberships: Mapped[list[Membership]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    memberships: Mapped[list[Membership]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Invitation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20), default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class RefreshToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class OrganizationAISettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organization_ai_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    # "default" = use the server's environment configuration.
    provider: Mapped[str] = mapped_column(String(20), default="default")
    model: Mapped[str] = mapped_column(String(100), default="")
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class CompanyProfile(UUIDMixin, TimestampMixin, Base):
    """Verified company information - the ONLY source of factual claims in generated proposals."""

    __tablename__ = "company_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    overview: Mapped[str] = mapped_column(Text, default="")
    services: Mapped[str] = mapped_column(Text, default="")
    capabilities: Mapped[str] = mapped_column(Text, default="")
    experience: Mapped[str] = mapped_column(Text, default="")
    certifications: Mapped[str] = mapped_column(Text, default="")
    client_references: Mapped[str] = mapped_column(Text, default="")
    team: Mapped[str] = mapped_column(Text, default="")
    differentiators: Mapped[str] = mapped_column(Text, default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
