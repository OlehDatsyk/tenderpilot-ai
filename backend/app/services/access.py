"""Organisation-scoped loaders. Every lookup by ID is filtered by the caller's organisation, and
objects from another organisation are reported as 404 (indistinguishable from "does not exist")."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ActivityEvent,
    BidAssessment,
    Document,
    Membership,
    ProposalDraft,
    ProposalSection,
    Requirement,
    Task,
    Tender,
    User,
)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found.")


def get_tender(db: Session, org_id: uuid.UUID, tender_id: uuid.UUID) -> Tender:
    tender = db.scalar(select(Tender).where(Tender.id == tender_id, Tender.organization_id == org_id))
    if tender is None:
        raise _not_found("Tender")
    return tender


def get_document(db: Session, org_id: uuid.UUID, tender_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.tender_id == tender_id, Document.organization_id == org_id))
    if doc is None:
        raise _not_found("Document")
    return doc


def get_requirement(db: Session, org_id: uuid.UUID, requirement_id: uuid.UUID) -> Requirement:
    req = db.scalar(select(Requirement).where(Requirement.id == requirement_id, Requirement.organization_id == org_id))
    if req is None:
        raise _not_found("Requirement")
    return req


def get_assessment(db: Session, org_id: uuid.UUID, assessment_id: uuid.UUID) -> BidAssessment:
    a = db.scalar(select(BidAssessment).where(BidAssessment.id == assessment_id, BidAssessment.organization_id == org_id))
    if a is None:
        raise _not_found("Assessment")
    return a


def get_proposal(db: Session, org_id: uuid.UUID, proposal_id: uuid.UUID) -> ProposalDraft:
    p = db.scalar(select(ProposalDraft).where(ProposalDraft.id == proposal_id, ProposalDraft.organization_id == org_id))
    if p is None:
        raise _not_found("Proposal")
    return p


def get_section(db: Session, org_id: uuid.UUID, proposal_id: uuid.UUID, section_id: uuid.UUID) -> ProposalSection:
    s = db.scalar(
        select(ProposalSection)
        .join(ProposalDraft, ProposalDraft.id == ProposalSection.proposal_id)
        .where(
            ProposalSection.id == section_id,
            ProposalSection.proposal_id == proposal_id,
            ProposalDraft.organization_id == org_id,
        )
    )
    if s is None:
        raise _not_found("Section")
    return s


def get_task(db: Session, org_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    t = db.scalar(select(Task).where(Task.id == task_id, Task.organization_id == org_id))
    if t is None:
        raise _not_found("Task")
    return t


def ensure_member(db: Session, org_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
    """Validate that an assignee belongs to the same organisation."""
    if user_id is None:
        return
    exists = db.scalar(select(Membership.id).where(Membership.organization_id == org_id, Membership.user_id == user_id))
    if exists is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The assignee is not a member of your organisation.")


def user_names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID | None, str]:
    clean = {i for i in ids if i is not None}
    if not clean:
        return {}
    return {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(clean)))}


def log_activity(db: Session, org_id: uuid.UUID, actor_id: uuid.UUID | None, action: str, summary: str, tender_id: uuid.UUID | None = None) -> None:
    db.add(ActivityEvent(organization_id=org_id, actor_id=actor_id, action=action, summary=summary[:500], tender_id=tender_id))
