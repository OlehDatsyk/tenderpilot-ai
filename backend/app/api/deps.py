"""Authentication / authorisation dependencies shared by all routers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Membership, User

bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]

_UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _UNAUTHORISED
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _UNAUTHORISED
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError:
        raise _UNAUTHORISED from None
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != payload.get("ver"):
        raise _UNAUTHORISED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass
class OrgContext:
    user: User
    membership: Membership

    @property
    def org_id(self) -> uuid.UUID:
        return self.membership.organization_id

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def is_admin(self) -> bool:
        return self.membership.role in ("owner", "admin")


def get_org_context(db: DB, user: CurrentUser) -> OrgContext:
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at).limit(1))
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of any organisation.")
    return OrgContext(user=user, membership=membership)


Ctx = Annotated[OrgContext, Depends(get_org_context)]


def require_admin(ctx: Ctx) -> OrgContext:
    if not ctx.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only organisation owners and admins can do this.")
    return ctx


AdminCtx = Annotated[OrgContext, Depends(require_admin)]
