"""Registration, login, token refresh/rotation, logout, profile and password management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import DB, Ctx, CurrentUser
from app.core.config import get_settings
from app.core.ratelimit import auth_rate_limit
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.models import CompanyProfile, Invitation, Membership, Organization, RefreshToken, User
from app.schemas.auth import (
    InvitationPreviewOut,
    LoginIn,
    MeOut,
    OrganizationOut,
    PasswordChangeIn,
    ProfileUpdateIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
)
from app.services.access import log_activity

router = APIRouter(prefix="/auth", tags=["auth"])

# Used to keep login timing similar whether or not the account exists.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password-1")


def _issue_tokens(db: Session, user: User, family_id: uuid.UUID | None = None) -> TokenOut:
    access, expires_in = create_access_token(user.id, user.token_version)
    refresh = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            family_id=family_id or uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_expire_days),
        )
    )
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=expires_in)


def _find_invitation(db: Session, token: str) -> Invitation | None:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at < datetime.now(UTC):
        return None
    return inv


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_rate_limit)])
def register(body: RegisterIn, db: DB) -> TokenOut:
    email = body.email.lower()
    if (err := validate_password_strength(body.password)) is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, err)

    invitation = None
    if body.invitation_token:
        invitation = _find_invitation(db, body.invitation_token)
        if invitation is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The invitation is invalid or has expired.")
        if invitation.email.lower() != email:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invitation was issued for a different email address.")
    elif not get_settings().registration_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Public registration is disabled. Ask an administrator for an invitation.")

    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")

    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password), last_login_at=datetime.now(UTC))
    db.add(user)
    db.flush()
    if invitation is not None:
        db.add(Membership(user_id=user.id, organization_id=invitation.organization_id, role=invitation.role))
        invitation.accepted_at = datetime.now(UTC)
        log_activity(db, invitation.organization_id, user.id, "member.joined", f"{user.full_name} joined the organisation")
    else:
        org_name = (body.organization_name or "").strip() or f"{body.full_name}'s organisation"
        org = Organization(name=org_name[:200])
        db.add(org)
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
        db.add(CompanyProfile(organization_id=org.id))
        log_activity(db, org.id, user.id, "organization.created", f"Organisation '{org.name}' created")
    tokens = _issue_tokens(db, user)
    db.commit()
    return tokens


@router.post("/login", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def login(body: LoginIn, db: DB) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    tokens = _issue_tokens(db, user)
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def refresh(body: RefreshIn, db: DB) -> TokenOut:
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
    if token is None:
        raise invalid
    now = datetime.now(UTC)
    if token.revoked_at is not None or token.rotated_at is not None:
        # Reuse of an already-rotated token: assume theft and revoke the whole family.
        db.execute(update(RefreshToken).where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        db.commit()
        raise invalid
    if token.expires_at < now:
        raise invalid
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise invalid
    token.rotated_at = now
    tokens = _issue_tokens(db, user, family_id=token.family_id)
    db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: DB) -> Response:
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
    if token is not None:
        db.execute(
            update(RefreshToken).where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC))
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _me(ctx_user: User, membership: Membership, org: Organization) -> MeOut:
    return MeOut(
        id=ctx_user.id,
        email=ctx_user.email,
        full_name=ctx_user.full_name,
        job_title=ctx_user.job_title,
        created_at=ctx_user.created_at,
        last_login_at=ctx_user.last_login_at,
        organization=OrganizationOut.model_validate(org),
        role=membership.role,
    )


@router.get("/me", response_model=MeOut)
def me(ctx: Ctx, db: DB) -> MeOut:
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    return _me(ctx.user, ctx.membership, org)


@router.patch("/me", response_model=MeOut)
def update_me(body: ProfileUpdateIn, ctx: Ctx, db: DB) -> MeOut:
    user = ctx.user
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.job_title is not None:
        user.job_title = body.job_title.strip() or None
    db.commit()
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    return _me(user, ctx.membership, org)


@router.post("/change-password", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def change_password(body: PasswordChangeIn, user: CurrentUser, db: DB) -> TokenOut:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The current password is incorrect.")
    if (err := validate_password_strength(body.new_password)) is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, err)
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The new password must be different.")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # invalidates all existing access tokens
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC)))
    tokens = _issue_tokens(db, user)
    db.commit()
    return tokens


@router.get("/invitations/{token}", response_model=InvitationPreviewOut, dependencies=[Depends(auth_rate_limit)])
def preview_invitation(token: str, db: DB) -> InvitationPreviewOut:
    inv = _find_invitation(db, token)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The invitation is invalid or has expired.")
    org = db.get(Organization, inv.organization_id)
    assert org is not None
    return InvitationPreviewOut(organization_name=org.name, email=inv.email, role=inv.role)
