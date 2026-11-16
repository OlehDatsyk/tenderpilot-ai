"""Proposal drafts, editable sections, AI drafting and requirement coverage. Also the tender assistant."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select

from app.ai.base import AIError
from app.ai.prompts import PLACEHOLDER
from app.api.deps import DB, Ctx
from app.api.v1.intelligence import ai_http_error
from app.core.ratelimit import ai_rate_limit
from app.models import AssistantMessage, ProposalDraft, ProposalSection, Requirement
from app.schemas.domain import (
    AssistantMessageOut,
    AssistantQuestionIn,
    CoverageOut,
    ProposalCreate,
    ProposalDetail,
    ProposalOut,
    ProposalUpdate,
    RequirementOut,
    SectionCreate,
    SectionGenerateIn,
    SectionOut,
    SectionUpdate,
)
from app.services import ai_workflows
from app.services.access import get_proposal, get_requirement, get_section, get_tender, log_activity

router = APIRouter(tags=["proposals"])


def _detail(p: ProposalDraft) -> ProposalDetail:
    return ProposalDetail(
        **ProposalOut.model_validate(p).model_dump(exclude={"section_count"}),
        section_count=len(p.sections),
        sections=[SectionOut.model_validate(s) for s in p.sections],
    )


@router.get("/tenders/{tender_id}/proposals", response_model=list[ProposalOut])
def list_proposals(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> list[ProposalOut]:
    get_tender(db, ctx.org_id, tender_id)
    counts: dict[uuid.UUID, int] = {
        pid: n
        for pid, n in db.execute(
            select(ProposalSection.proposal_id, func.count())
            .join(ProposalDraft, ProposalDraft.id == ProposalSection.proposal_id)
            .where(ProposalDraft.tender_id == tender_id)
            .group_by(ProposalSection.proposal_id)
        )
    }
    rows = db.scalars(
        select(ProposalDraft).where(ProposalDraft.tender_id == tender_id, ProposalDraft.organization_id == ctx.org_id).order_by(ProposalDraft.updated_at.desc())
    )
    return [ProposalOut.model_validate(p).model_copy(update={"section_count": counts.get(p.id, 0)}) for p in rows]


@router.post("/tenders/{tender_id}/proposals", response_model=ProposalDetail, status_code=status.HTTP_201_CREATED)
def create_proposal(tender_id: uuid.UUID, body: ProposalCreate, request: Request, ctx: Ctx, db: DB) -> ProposalDetail:
    tender = get_tender(db, ctx.org_id, tender_id)
    if body.use_ai_outline:
        ai_rate_limit(request)
    proposal = ProposalDraft(tender_id=tender.id, organization_id=ctx.org_id, created_by_id=ctx.user.id, title=body.title.strip())
    db.add(proposal)
    db.flush()
    log_activity(db, ctx.org_id, ctx.user.id, "proposal.created", f"Proposal '{proposal.title}' created", tender.id)
    if body.use_ai_outline:
        try:
            ai_workflows.generate_outline(db, ctx.org_id, tender, proposal, ctx.user.id)
        except AIError as exc:
            raise ai_http_error(exc) from exc
    db.commit()
    db.refresh(proposal)
    return _detail(proposal)


@router.get("/proposals/{proposal_id}", response_model=ProposalDetail)
def get_proposal_detail(proposal_id: uuid.UUID, ctx: Ctx, db: DB) -> ProposalDetail:
    return _detail(get_proposal(db, ctx.org_id, proposal_id))


@router.patch("/proposals/{proposal_id}", response_model=ProposalDetail)
def update_proposal(proposal_id: uuid.UUID, body: ProposalUpdate, ctx: Ctx, db: DB) -> ProposalDetail:
    p = get_proposal(db, ctx.org_id, proposal_id)
    if body.title is not None:
        p.title = body.title.strip()
    if body.status is not None:
        p.status = body.status
    db.commit()
    db.refresh(p)
    return _detail(p)


@router.delete("/proposals/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal(proposal_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    p = get_proposal(db, ctx.org_id, proposal_id)
    log_activity(db, ctx.org_id, ctx.user.id, "proposal.deleted", f"Proposal '{p.title}' deleted", p.tender_id)
    db.delete(p)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/proposals/{proposal_id}/outline", response_model=ProposalDetail, dependencies=[Depends(ai_rate_limit)])
def add_outline(proposal_id: uuid.UUID, ctx: Ctx, db: DB) -> ProposalDetail:
    p = get_proposal(db, ctx.org_id, proposal_id)
    tender = get_tender(db, ctx.org_id, p.tender_id)
    try:
        ai_workflows.generate_outline(db, ctx.org_id, tender, p, ctx.user.id)
    except AIError as exc:
        raise ai_http_error(exc) from exc
    db.commit()
    db.refresh(p)
    return _detail(p)


@router.post("/proposals/{proposal_id}/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def add_section(proposal_id: uuid.UUID, body: SectionCreate, ctx: Ctx, db: DB) -> ProposalSection:
    p = get_proposal(db, ctx.org_id, proposal_id)
    if body.requirement_id is not None:
        req = get_requirement(db, ctx.org_id, body.requirement_id)
        if req.tender_id != p.tender_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The requirement belongs to a different tender.")
    position = (db.scalar(select(func.max(ProposalSection.position)).where(ProposalSection.proposal_id == p.id)) or 0) + 1
    s = ProposalSection(proposal_id=p.id, position=position, **body.model_dump())
    db.add(s)
    db.commit()
    return s


@router.patch("/proposals/{proposal_id}/sections/{section_id}", response_model=SectionOut)
def update_section(proposal_id: uuid.UUID, section_id: uuid.UUID, body: SectionUpdate, ctx: Ctx, db: DB) -> ProposalSection:
    s = get_section(db, ctx.org_id, proposal_id, section_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(s, key, value)
    db.commit()
    return s


@router.delete("/proposals/{proposal_id}/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(proposal_id: uuid.UUID, section_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    s = get_section(db, ctx.org_id, proposal_id, section_id)
    db.delete(s)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/proposals/{proposal_id}/sections/{section_id}/generate",
    response_model=dict,
    dependencies=[Depends(ai_rate_limit)],
)
def generate_section(proposal_id: uuid.UUID, section_id: uuid.UUID, body: SectionGenerateIn, ctx: Ctx, db: DB) -> dict:
    s = get_section(db, ctx.org_id, proposal_id, section_id)
    p = get_proposal(db, ctx.org_id, proposal_id)
    tender = get_tender(db, ctx.org_id, p.tender_id)
    if body.mode == "improve" and not s.content.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "There is no text to improve yet. Draft the section first.")
    try:
        unanswered = ai_workflows.generate_section(db, ctx.org_id, tender, s, ctx.user.id, body.mode, body.instructions)
    except AIError as exc:
        raise ai_http_error(exc) from exc
    db.refresh(s)
    return {"section": SectionOut.model_validate(s).model_dump(mode="json"), "unanswered_points": unanswered}


@router.get("/proposals/{proposal_id}/coverage", response_model=CoverageOut)
def coverage(proposal_id: uuid.UUID, ctx: Ctx, db: DB) -> CoverageOut:
    """Which requirements are not yet answered by a section with real (non-placeholder) content."""
    p = get_proposal(db, ctx.org_id, proposal_id)
    reqs = list(
        db.scalars(select(Requirement).where(Requirement.tender_id == p.tender_id, Requirement.organization_id == ctx.org_id).order_by(Requirement.position))
    )
    answered = {s.requirement_id for s in p.sections if s.requirement_id and s.content.strip() and PLACEHOLDER not in s.content}
    unanswered = [r for r in reqs if r.id not in answered]
    return CoverageOut(
        total_requirements=len(reqs),
        covered=len(reqs) - len(unanswered),
        unanswered=[RequirementOut.model_validate(r) for r in unanswered],
        placeholder_sections=[s.id for s in p.sections if PLACEHOLDER in s.content or not s.content.strip()],
    )


# ------------------------------------------------------------------ assistant (per tender, per user)


@router.get("/tenders/{tender_id}/assistant/messages", response_model=list[AssistantMessageOut])
def assistant_history(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> list[AssistantMessage]:
    get_tender(db, ctx.org_id, tender_id)
    return list(
        db.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.tender_id == tender_id, AssistantMessage.organization_id == ctx.org_id, AssistantMessage.user_id == ctx.user.id)
            .order_by(AssistantMessage.created_at)
            .limit(200)
        )
    )


@router.post(
    "/tenders/{tender_id}/assistant/messages",
    response_model=list[AssistantMessageOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ai_rate_limit)],
)
def ask(tender_id: uuid.UUID, body: AssistantQuestionIn, ctx: Ctx, db: DB) -> list[AssistantMessage]:
    tender = get_tender(db, ctx.org_id, tender_id)
    try:
        q, a = ai_workflows.ask_assistant(db, ctx.org_id, tender, ctx.user.id, body.question.strip())
    except AIError as exc:
        raise ai_http_error(exc) from exc
    return [q, a]


@router.delete("/tenders/{tender_id}/assistant/messages", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    get_tender(db, ctx.org_id, tender_id)
    db.execute(
        delete(AssistantMessage).where(
            AssistantMessage.tender_id == tender_id, AssistantMessage.organization_id == ctx.org_id, AssistantMessage.user_id == ctx.user.id
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
