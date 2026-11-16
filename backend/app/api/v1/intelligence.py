"""AI analysis runs, requirements / compliance matrix and bid/no-bid assessments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select

from app.ai.base import AIError, AINotConfiguredError
from app.ai.service import describe, resolve_config
from app.api.deps import DB, Ctx
from app.core.ratelimit import ai_rate_limit
from app.models import AnalysisRun, BidAssessment, Requirement
from app.schemas.domain import (
    AnalysisRunOut,
    BidAssessmentOut,
    BidDecisionIn,
    ComplianceSummary,
    RequirementCreate,
    RequirementOut,
    RequirementUpdate,
)
from app.services import ai_workflows
from app.services.access import ensure_member, get_assessment, get_requirement, get_tender, log_activity, user_names
from app.services.compliance import summary_for_tender

router = APIRouter(tags=["analysis"])


def ai_http_error(exc: AIError) -> HTTPException:
    if isinstance(exc, AINotConfiguredError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.get("/ai/status")
def ai_status(ctx: Ctx, db: DB) -> dict:
    return describe(resolve_config(db, ctx.org_id))


# ------------------------------------------------------------------ analysis runs


@router.post(
    "/tenders/{tender_id}/analysis",
    response_model=AnalysisRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(ai_rate_limit)],
)
def start_analysis(tender_id: uuid.UUID, ctx: Ctx, db: DB, background: BackgroundTasks) -> AnalysisRun:
    tender = get_tender(db, ctx.org_id, tender_id)
    active = db.scalar(
        select(AnalysisRun.id).where(AnalysisRun.tender_id == tender.id, AnalysisRun.kind == "tender_analysis", AnalysisRun.status.in_(["queued", "running"]))
    )
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An analysis is already running for this tender.")
    try:
        run = ai_workflows.create_analysis_run(db, ctx.org_id, tender, ctx.user.id)
    except AIError as exc:
        raise ai_http_error(exc) from exc
    background.add_task(ai_workflows.execute_analysis_run, run.id)
    return run


@router.get("/tenders/{tender_id}/analysis/runs", response_model=list[AnalysisRunOut])
def list_runs(tender_id: uuid.UUID, ctx: Ctx, db: DB, kind: str | None = None, limit: int = Query(20, ge=1, le=100)) -> list[AnalysisRun]:
    get_tender(db, ctx.org_id, tender_id)
    stmt = select(AnalysisRun).where(AnalysisRun.tender_id == tender_id, AnalysisRun.organization_id == ctx.org_id)
    if kind:
        stmt = stmt.where(AnalysisRun.kind == kind)
    return list(db.scalars(stmt.order_by(AnalysisRun.created_at.desc()).limit(limit)))


@router.get("/tenders/{tender_id}/analysis/latest", response_model=AnalysisRunOut | None)
def latest_analysis(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> AnalysisRun | None:
    get_tender(db, ctx.org_id, tender_id)
    return db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.tender_id == tender_id, AnalysisRun.organization_id == ctx.org_id, AnalysisRun.kind == "tender_analysis")
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )


@router.get("/analysis/runs/{run_id}", response_model=AnalysisRunOut)
def get_run(run_id: uuid.UUID, ctx: Ctx, db: DB) -> AnalysisRun:
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.organization_id == ctx.org_id))
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis run not found.")
    return run


# ------------------------------------------------------------------ requirements / compliance


def _req_out(r: Requirement, names: dict) -> RequirementOut:
    return RequirementOut.model_validate(r).model_copy(update={"assignee_name": names.get(r.assignee_id)})


@router.get("/tenders/{tender_id}/requirements", response_model=list[RequirementOut])
def list_requirements(
    tender_id: uuid.UUID,
    ctx: Ctx,
    db: DB,
    mandatory: bool | None = None,
    response_status: str | None = Query(None, alias="status"),
    category: str | None = None,
    q: str | None = Query(None, max_length=200),
) -> list[RequirementOut]:
    get_tender(db, ctx.org_id, tender_id)
    stmt = select(Requirement).where(Requirement.tender_id == tender_id, Requirement.organization_id == ctx.org_id)
    if mandatory is not None:
        stmt = stmt.where(Requirement.is_mandatory == mandatory)
    if response_status:
        stmt = stmt.where(Requirement.response_status == response_status)
    if category:
        stmt = stmt.where(Requirement.category == category)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Requirement.description).like(like), func.lower(Requirement.evidence).like(like)))
    reqs = list(db.scalars(stmt.order_by(Requirement.position, Requirement.created_at)))
    names = user_names(db, {r.assignee_id for r in reqs})
    return [_req_out(r, names) for r in reqs]


@router.post("/tenders/{tender_id}/requirements", response_model=RequirementOut, status_code=status.HTTP_201_CREATED)
def create_requirement(tender_id: uuid.UUID, body: RequirementCreate, ctx: Ctx, db: DB) -> RequirementOut:
    tender = get_tender(db, ctx.org_id, tender_id)
    position = (db.scalar(select(func.max(Requirement.position)).where(Requirement.tender_id == tender.id)) or 0) + 1
    req = Requirement(
        tender_id=tender.id,
        organization_id=ctx.org_id,
        origin="manual",
        position=position,
        source_verified=False,
        **body.model_dump(),
    )
    db.add(req)
    log_activity(db, ctx.org_id, ctx.user.id, "requirement.created", "Requirement added manually", tender.id)
    db.commit()
    return _req_out(req, {})


@router.patch("/requirements/{requirement_id}", response_model=RequirementOut)
def update_requirement(requirement_id: uuid.UUID, body: RequirementUpdate, ctx: Ctx, db: DB) -> RequirementOut:
    req = get_requirement(db, ctx.org_id, requirement_id)
    changes = body.model_dump(exclude_unset=True, exclude={"clear_assignee"})
    if "assignee_id" in changes and changes["assignee_id"] is not None:
        ensure_member(db, ctx.org_id, changes["assignee_id"])
    if body.clear_assignee:
        changes["assignee_id"] = None
    old_status = req.response_status
    for key, value in changes.items():
        if value is None and key != "assignee_id":
            continue
        setattr(req, key, value)
    if req.response_status != old_status:
        log_activity(
            db,
            ctx.org_id,
            ctx.user.id,
            "requirement.status_changed",
            f"Requirement status: {old_status.replace('_', ' ')} → {req.response_status.replace('_', ' ')}",
            req.tender_id,
        )
    db.commit()
    db.refresh(req)
    return _req_out(req, user_names(db, {req.assignee_id}))


@router.delete("/requirements/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement(requirement_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    req = get_requirement(db, ctx.org_id, requirement_id)
    tender_id = req.tender_id
    db.delete(req)
    log_activity(db, ctx.org_id, ctx.user.id, "requirement.deleted", "Requirement deleted", tender_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tenders/{tender_id}/compliance", response_model=ComplianceSummary)
def compliance_summary(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> ComplianceSummary:
    get_tender(db, ctx.org_id, tender_id)
    return summary_for_tender(db, ctx.org_id, tender_id)


# ------------------------------------------------------------------ bid / no-bid


def _bid_out(db, a: BidAssessment) -> BidAssessmentOut:
    run = db.get(AnalysisRun, a.analysis_run_id) if a.analysis_run_id else None
    names = user_names(db, {a.decided_by_id})
    return BidAssessmentOut.model_validate(a).model_copy(
        update={"decided_by_name": names.get(a.decided_by_id), "provider": run.provider if run else None, "model": run.model if run else None}
    )


@router.get("/tenders/{tender_id}/bid-assessments", response_model=list[BidAssessmentOut])
def list_assessments(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> list[BidAssessmentOut]:
    get_tender(db, ctx.org_id, tender_id)
    rows = db.scalars(
        select(BidAssessment).where(BidAssessment.tender_id == tender_id, BidAssessment.organization_id == ctx.org_id).order_by(BidAssessment.created_at.desc())
    )
    return [_bid_out(db, a) for a in rows]


@router.post(
    "/tenders/{tender_id}/bid-assessments",
    response_model=BidAssessmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ai_rate_limit)],
)
def create_assessment(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> BidAssessmentOut:
    tender = get_tender(db, ctx.org_id, tender_id)
    try:
        a = ai_workflows.generate_bid_assessment(db, ctx.org_id, tender, ctx.user.id)
    except AIError as exc:
        raise ai_http_error(exc) from exc
    return _bid_out(db, a)


@router.post("/bid-assessments/{assessment_id}/decision", response_model=BidAssessmentOut)
def record_decision(assessment_id: uuid.UUID, body: BidDecisionIn, ctx: Ctx, db: DB) -> BidAssessmentOut:
    a = get_assessment(db, ctx.org_id, assessment_id)
    a.final_decision = body.final_decision
    a.final_reasoning = body.final_reasoning.strip()
    a.decided_by_id = ctx.user.id
    a.decided_at = datetime.now(UTC)
    overridden = body.final_decision != a.recommendation
    log_activity(
        db,
        ctx.org_id,
        ctx.user.id,
        "bid.decided",
        f"Final decision: {body.final_decision.replace('_', ' ')}{' (overrides recommendation)' if overridden else ''}",
        a.tender_id,
    )
    db.commit()
    return _bid_out(db, a)
