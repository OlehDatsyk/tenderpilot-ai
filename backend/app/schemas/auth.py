from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _strip(v: str) -> str:
    return v.strip()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=200)
    organization_name: str | None = Field(None, max_length=200)
    invitation_token: str | None = Field(None, max_length=200)

    _s = field_validator("full_name")(_strip)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(..., min_length=10, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str
    job_title: str | None
    created_at: datetime
    last_login_at: datetime | None


class MeOut(UserOut):
    organization: OrganizationOut
    role: str


class ProfileUpdateIn(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    job_title: str | None = Field(None, max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)


class OrganizationUpdateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    job_title: str | None
    role: str
    joined_at: datetime


class MemberRoleIn(BaseModel):
    role: Literal["admin", "member"]


class InvitationIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationCreatedOut(InvitationOut):
    token: str = Field(..., description="Shown once. Share the invite link with the invitee securely.")


class InvitationPreviewOut(BaseModel):
    organization_name: str
    email: str
    role: str
