"""Organisation profile, members, invitations, company profile and AI provider settings."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.ai.service import describe, resolve_config
from app.api.deps import DB, AdminCtx, Ctx
from app.core.config import get_settings
from app.core.security import (
    EncryptionUnavailableError,
    decrypt_secret,
    encrypt_secret,
    encryption_available,
    generate_opaque_token,
    hash_token,
    mask_secret,
)
from app.models import CompanyProfile, Invitation, Membership, Organization, OrganizationAISettings, User
from app.schemas.auth import (
    InvitationCreatedOut,
    InvitationIn,
    InvitationOut,
    MemberOut,
    MemberRoleIn,
    OrganizationOut,
    OrganizationUpdateIn,
)
from app.schemas.domain import AISettingsIn, AISettingsOut, CompanyProfileIn, CompanyProfileOut
from app.services.access import log_activity

router = APIRouter(prefix="/organization", tags=["organization"])

PROFILE_FIELDS = list(CompanyProfileIn.model_fields)


@router.get("", response_model=OrganizationOut)
def get_organization(ctx: Ctx, db: DB) -> Organization:
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    return org


@router.patch("", response_model=OrganizationOut)
def update_organization(body: OrganizationUpdateIn, ctx: AdminCtx, db: DB) -> Organization:
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    org.name = body.name.strip()
    log_activity(db, ctx.org_id, ctx.user.id, "organization.updated", f"Organisation renamed to '{org.name}'")
    db.commit()
    return org


@router.get("/members", response_model=list[MemberOut])
def list_members(ctx: Ctx, db: DB) -> list[MemberOut]:
    rows = db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.organization_id == ctx.org_id).order_by(User.full_name)
    ).all()
    return [MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, job_title=u.job_title, role=m.role, joined_at=m.created_at) for m, u in rows]


def _member(db, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    m = db.scalar(select(Membership).where(Membership.organization_id == org_id, Membership.user_id == user_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.")
    return m


@router.patch("/members/{user_id}", response_model=MemberOut)
def change_member_role(user_id: uuid.UUID, body: MemberRoleIn, ctx: AdminCtx, db: DB) -> MemberOut:
    m = _member(db, ctx.org_id, user_id)
    if m.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The owner's role cannot be changed.")
    m.role = body.role
    u = db.get(User, user_id)
    assert u is not None
    log_activity(db, ctx.org_id, ctx.user.id, "member.role_changed", f"{u.full_name} is now {body.role}")
    db.commit()
    return MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, job_title=u.job_title, role=m.role, joined_at=m.created_at)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: uuid.UUID, ctx: AdminCtx, db: DB) -> Response:
    m = _member(db, ctx.org_id, user_id)
    if m.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The organisation owner cannot be removed.")
    if user_id == ctx.user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot remove yourself.")
    u = db.get(User, user_id)
    db.delete(m)
    if u is not None:
        u.token_version += 1  # end their sessions immediately
        log_activity(db, ctx.org_id, ctx.user.id, "member.removed", f"{u.full_name} was removed from the organisation")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: AdminCtx, db: DB) -> list[Invitation]:
    return list(db.scalars(select(Invitation).where(Invitation.organization_id == ctx.org_id).order_by(Invitation.created_at.desc())))


@router.post("/invitations", response_model=InvitationCreatedOut, status_code=status.HTTP_201_CREATED)
def create_invitation(body: InvitationIn, ctx: AdminCtx, db: DB) -> InvitationCreatedOut:
    email = body.email.lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A user with this email already has an account. Multi-organisation accounts are not supported yet.",
        )
    token = generate_opaque_token()
    inv = Invitation(
        organization_id=ctx.org_id,
        email=email,
        role=body.role,
        token_hash=hash_token(token),
        created_by_id=ctx.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(inv)
    log_activity(db, ctx.org_id, ctx.user.id, "invitation.created", f"Invitation created for {email}")
    db.commit()
    return InvitationCreatedOut(**InvitationOut.model_validate(inv).model_dump(), token=token)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: uuid.UUID, ctx: AdminCtx, db: DB) -> Response:
    inv = db.scalar(select(Invitation).where(Invitation.id == invitation_id, Invitation.organization_id == ctx.org_id))
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found.")
    if inv.revoked_at is None and inv.accepted_at is None:
        inv.revoked_at = datetime.now(UTC)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- company profile


def _profile(db, org_id: uuid.UUID) -> CompanyProfile:
    p = db.scalar(select(CompanyProfile).where(CompanyProfile.organization_id == org_id))
    if p is None:
        p = CompanyProfile(organization_id=org_id)
        db.add(p)
        db.flush()
    return p


def profile_out(p: CompanyProfile) -> CompanyProfileOut:
    data = {f: getattr(p, f) or "" for f in PROFILE_FIELDS}
    filled = sum(1 for f in PROFILE_FIELDS if f != "website" and data[f].strip())
    return CompanyProfileOut(**data, updated_at=p.updated_at, completeness=round(filled / (len(PROFILE_FIELDS) - 1) * 100))


@router.get("/company-profile", response_model=CompanyProfileOut)
def get_company_profile(ctx: Ctx, db: DB) -> CompanyProfileOut:
    p = _profile(db, ctx.org_id)
    db.commit()
    return profile_out(p)


@router.put("/company-profile", response_model=CompanyProfileOut)
def update_company_profile(body: CompanyProfileIn, ctx: Ctx, db: DB) -> CompanyProfileOut:
    p = _profile(db, ctx.org_id)
    for f in PROFILE_FIELDS:
        setattr(p, f, getattr(body, f).strip())
    p.updated_by_id = ctx.user.id
    log_activity(db, ctx.org_id, ctx.user.id, "company_profile.updated", "Company profile updated")
    db.commit()
    db.refresh(p)
    return profile_out(p)


# ---------------------------------------------------------------- AI settings


def _ai_out(db, org_id: uuid.UUID) -> AISettingsOut:
    row = db.scalar(select(OrganizationAISettings).where(OrganizationAISettings.organization_id == org_id))
    hint = ""
    if row and row.encrypted_api_key:
        try:
            hint = mask_secret(decrypt_secret(row.encrypted_api_key))
        except EncryptionUnavailableError:
            hint = "(cannot be decrypted - check ENCRYPTION_KEY)"
    settings = get_settings()
    return AISettingsOut(
        provider=row.provider if row else "default",
        model=row.model if row else "",
        api_key_stored=bool(row and row.encrypted_api_key),
        api_key_hint=hint,
        effective=describe(resolve_config(db, org_id)),
        org_keys_allowed=settings.allow_org_ai_keys,
        encryption_available=encryption_available(),
        server_default_provider=settings.ai_provider,
    )


@router.get("/ai-settings", response_model=AISettingsOut)
def get_ai_settings(ctx: Ctx, db: DB) -> AISettingsOut:
    return _ai_out(db, ctx.org_id)


@router.put("/ai-settings", response_model=AISettingsOut)
def update_ai_settings(body: AISettingsIn, ctx: AdminCtx, db: DB) -> AISettingsOut:
    settings = get_settings()
    row = db.scalar(select(OrganizationAISettings).where(OrganizationAISettings.organization_id == ctx.org_id))
    if row is None:
        row = OrganizationAISettings(organization_id=ctx.org_id)
        db.add(row)
    row.provider = body.provider
    row.model = body.model.strip()
    if body.api_key is not None:
        key = body.api_key.strip()
        if key:
            if not settings.allow_org_ai_keys:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Storing organisation API keys is disabled on this server.")
            try:
                row.encrypted_api_key = encrypt_secret(key)
            except EncryptionUnavailableError as exc:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        else:
            row.encrypted_api_key = None
    row.updated_by_id = ctx.user.id
    log_activity(db, ctx.org_id, ctx.user.id, "ai_settings.updated", f"AI provider set to '{body.provider}'")
    db.commit()
    return _ai_out(db, ctx.org_id)
