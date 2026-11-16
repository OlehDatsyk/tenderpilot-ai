"""Compliance statistics computed from real requirement records."""

from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Requirement
from app.models.enums import DONE_RESPONSE_STATUSES, RESPONSE_STATUSES
from app.schemas.domain import ComplianceSummary


def summary_for_tender(db: Session, org_id: uuid.UUID, tender_id: uuid.UUID) -> ComplianceSummary:
    rows = db.execute(
        select(Requirement.response_status, Requirement.is_mandatory, func.count())
        .where(Requirement.tender_id == tender_id, Requirement.organization_id == org_id)
        .group_by(Requirement.response_status, Requirement.is_mandatory)
    ).all()
    by_status = dict.fromkeys(RESPONSE_STATUSES, 0)
    total = mandatory = addressed = mandatory_addressed = 0
    for status, is_mandatory, count in rows:
        by_status[status] = by_status.get(status, 0) + count
        total += count
        done = status in DONE_RESPONSE_STATUSES
        addressed += count if done else 0
        if is_mandatory:
            mandatory += count
            mandatory_addressed += count if done else 0
    return ComplianceSummary(
        total=total,
        mandatory_total=mandatory,
        by_status=by_status,
        addressed=addressed,
        percent_complete=round(addressed / total * 100, 1) if total else 0.0,
        mandatory_percent_complete=round(mandatory_addressed / mandatory * 100, 1) if mandatory else 0.0,
    )


def percent_by_tender(db: Session, org_id: uuid.UUID, tender_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, float | None]]:
    """Return {tender_id: (requirement_count, percent_complete or None)} in one query."""
    if not tender_ids:
        return {}
    done = func.sum(case((Requirement.response_status.in_(DONE_RESPONSE_STATUSES), 1), else_=0))
    rows = db.execute(
        select(Requirement.tender_id, func.count(), done)
        .where(Requirement.organization_id == org_id, Requirement.tender_id.in_(tender_ids))
        .group_by(Requirement.tender_id)
    ).all()
    out: dict[uuid.UUID, tuple[int, float | None]] = {}
    for tid, count, addressed in rows:
        out[tid] = (count, round((addressed or 0) / count * 100, 1) if count else None)
    return out
