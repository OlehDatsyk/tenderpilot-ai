"""Tender workspace CRUD with search, filtering, sorting and pagination."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import case, func, or_, select

from app.api.deps import DB, Ctx
from app.models import BidAssessment, Document, Task, Tender, User
from app.schemas.domain import Page, TenderCreate, TenderDetail, TenderListItem, TenderOut, TenderStatus, TenderUpdate
from app.services import storage
from app.services.access import get_tender, log_activity
from app.services.compliance import percent_by_tender, summary_for_tender

router = APIRouter(prefix="/tenders", tags=["tenders"])

STATUS_LABELS = {
    "draft": "Draft",
    "under_review": "Under Review",
    "bid_decision": "Bid Decision",
    "in_preparation": "In Preparation",
    "internal_review": "Internal Review",
    "submitted": "Submitted",
    "won": "Won",
    "lost": "Lost",
    "withdrawn": "Withdrawn",
}
_PRIORITY_ORDER = case({"low": 1, "medium": 2, "high": 3, "critical": 4}, value=Tender.priority, else_=0)


@router.get("", response_model=Page[TenderListItem])
def list_tenders(
    ctx: Ctx,
    db: DB,
    q: str | None = Query(None, max_length=200, description="Search title, buyer, reference"),
    status_: list[TenderStatus] | None = Query(None, alias="status"),
    priority: str | None = Query(None, pattern="^(low|medium|high|critical)$"),
    tender_type: str | None = Query(None, pattern="^(tender|rfp|rfq|rfi|procurement|questionnaire|other)$"),
    archived: bool = False,
    sort: Literal["updated_at", "created_at", "submission_deadline", "title", "priority", "estimated_value"] = "updated_at",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[TenderListItem]:
    stmt = select(Tender).where(Tender.organization_id == ctx.org_id, Tender.is_archived == archived)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Tender.title).like(like), func.lower(Tender.buyer).like(like), func.lower(Tender.reference).like(like)))
    if status_:
        stmt = stmt.where(Tender.status.in_(status_))
    if priority:
        stmt = stmt.where(Tender.priority == priority)
    if tender_type:
        stmt = stmt.where(Tender.tender_type == tender_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = _PRIORITY_ORDER if sort == "priority" else getattr(Tender, sort)
    ordering = col.asc() if order == "asc" else col.desc()
    if sort == "submission_deadline":
        ordering = ordering.nulls_last()
    tenders = list(db.scalars(stmt.order_by(ordering, Tender.id).offset((page - 1) * page_size).limit(page_size)))

    ids = [t.id for t in tenders]
    doc_counts: dict[uuid.UUID, int] = (
        {tid: n for tid, n in db.execute(select(Document.tender_id, func.count()).where(Document.tender_id.in_(ids)).group_by(Document.tender_id))}
        if ids
        else {}
    )
    compliance = percent_by_tender(db, ctx.org_id, ids)
    items = []
    for t in tenders:
        req_count, pct = compliance.get(t.id, (0, None))
        items.append(
            TenderListItem.model_validate(t).model_copy(
                update={"document_count": doc_counts.get(t.id, 0), "requirement_count": req_count, "compliance_percent": pct}
            )
        )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=TenderOut, status_code=status.HTTP_201_CREATED)
def create_tender(body: TenderCreate, ctx: Ctx, db: DB) -> Tender:
    tender = Tender(organization_id=ctx.org_id, created_by_id=ctx.user.id, **body.model_dump())
    db.add(tender)
    db.flush()
    log_activity(db, ctx.org_id, ctx.user.id, "tender.created", f"Tender '{tender.title}' created", tender.id)
    db.commit()
    return tender


def _detail(db, ctx, tender: Tender) -> TenderDetail:
    doc_count = db.scalar(select(func.count()).where(Document.tender_id == tender.id)) or 0
    open_tasks = db.scalar(select(func.count()).where(Task.tender_id == tender.id, Task.status != "done")) or 0
    latest = db.scalar(select(BidAssessment).where(BidAssessment.tender_id == tender.id).order_by(BidAssessment.created_at.desc()).limit(1))
    creator = db.get(User, tender.created_by_id) if tender.created_by_id else None
    comp = summary_for_tender(db, ctx.org_id, tender.id)
    return TenderDetail(
        **TenderOut.model_validate(tender).model_dump(),
        document_count=doc_count,
        requirement_count=comp.total,
        compliance=comp,
        open_task_count=open_tasks,
        latest_decision=(latest.final_decision or None) if latest else None,
        created_by_name=creator.full_name if creator else None,
    )


@router.get("/{tender_id}", response_model=TenderDetail)
def get_tender_detail(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> TenderDetail:
    return _detail(db, ctx, get_tender(db, ctx.org_id, tender_id))


@router.patch("/{tender_id}", response_model=TenderDetail)
def update_tender(tender_id: uuid.UUID, body: TenderUpdate, ctx: Ctx, db: DB) -> TenderDetail:
    tender = get_tender(db, ctx.org_id, tender_id)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    old_status = tender.status
    for key, value in changes.items():
        if value is None and key in ("title", "tender_type", "status", "priority", "currency", "is_archived"):
            continue  # required columns cannot be nulled
        if value is None and key in ("buyer", "reference", "description", "notes"):
            value = ""
        setattr(tender, key, value)
    if tender.status != old_status:
        log_activity(
            db,
            ctx.org_id,
            ctx.user.id,
            "tender.status_changed",
            f"'{tender.title}' moved from {STATUS_LABELS[old_status]} to {STATUS_LABELS[tender.status]}",
            tender.id,
        )
    elif "is_archived" in changes and changes["is_archived"] is not None:
        log_activity(
            db,
            ctx.org_id,
            ctx.user.id,
            "tender.archived" if tender.is_archived else "tender.restored",
            f"'{tender.title}' {'archived' if tender.is_archived else 'restored'}",
            tender.id,
        )
    else:
        log_activity(db, ctx.org_id, ctx.user.id, "tender.updated", f"'{tender.title}' updated", tender.id)
    db.commit()
    db.refresh(tender)
    return _detail(db, ctx, tender)


@router.delete("/{tender_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tender(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    tender = get_tender(db, ctx.org_id, tender_id)
    keys = list(db.scalars(select(Document.storage_key).where(Document.tender_id == tender.id)))
    for key in keys:
        storage.remove(db, key)
    title = tender.title
    db.delete(tender)
    log_activity(db, ctx.org_id, ctx.user.id, "tender.deleted", f"Tender '{title}' deleted")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
