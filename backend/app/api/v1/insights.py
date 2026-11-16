"""Dashboard, analytics and activity feed - every number is computed from stored records."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DB, Ctx
from app.models import ActivityEvent, AnalysisRun, BidAssessment, Document, Requirement, Task, Tender, User
from app.models.enums import ACTIVE_TENDER_STATUSES, DONE_RESPONSE_STATUSES, TENDER_STATUSES
from app.schemas.domain import ActivityOut
from app.services.compliance import percent_by_tender

router = APIRouter(tags=["insights"])


def _activity(db, org_id: uuid.UUID, limit: int, tender_id: uuid.UUID | None = None) -> list[ActivityOut]:
    stmt = (
        select(ActivityEvent, User.full_name, Tender.title)
        .outerjoin(User, User.id == ActivityEvent.actor_id)
        .outerjoin(Tender, Tender.id == ActivityEvent.tender_id)
        .where(ActivityEvent.organization_id == org_id)
    )
    if tender_id:
        stmt = stmt.where(ActivityEvent.tender_id == tender_id)
    rows = db.execute(stmt.order_by(ActivityEvent.created_at.desc()).limit(limit)).all()
    return [ActivityOut.model_validate(ev).model_copy(update={"actor_name": name, "tender_title": title}) for ev, name, title in rows]


@router.get("/activity", response_model=list[ActivityOut])
def activity(ctx: Ctx, db: DB, tender_id: uuid.UUID | None = None, limit: int = Query(30, ge=1, le=200)) -> list[ActivityOut]:
    return _activity(db, ctx.org_id, limit, tender_id)


def _latest_decisions(db, org_id: uuid.UUID) -> dict[uuid.UUID, BidAssessment]:
    latest: dict[uuid.UUID, BidAssessment] = {}
    for a in db.scalars(select(BidAssessment).where(BidAssessment.organization_id == org_id).order_by(BidAssessment.created_at)):
        latest[a.tender_id] = a
    return latest


@router.get("/dashboard")
def dashboard(ctx: Ctx, db: DB) -> dict:
    org = ctx.org_id
    now = datetime.now(UTC)
    tenders = list(db.scalars(select(Tender).where(Tender.organization_id == org, Tender.is_archived.is_(False))))
    status_counts = Counter(t.status for t in tenders)
    # (deadline, tender) pairs keep the deadline narrowed to a non-optional datetime.
    upcoming_pairs = sorted(
        (
            (t.submission_deadline, t)
            for t in tenders
            if t.submission_deadline and t.submission_deadline >= now and t.status not in ("submitted", "won", "lost", "withdrawn")
        ),
        key=lambda pair: pair[0],
    )
    won, lost = status_counts.get("won", 0), status_counts.get("lost", 0)
    decided = won + lost

    alerts: list[dict] = []
    for deadline, t in upcoming_pairs:
        days = (deadline - now).days
        if days <= 7:
            alerts.append(
                {"type": "deadline", "severity": "high" if days <= 2 else "medium", "tender_id": str(t.id), "message": f"'{t.title}' is due in {days} day(s)."}
            )
    overdue_deadlines = [t for t in tenders if t.submission_deadline and t.submission_deadline < now and t.status in ACTIVE_TENDER_STATUSES + ("draft",)]
    for t in overdue_deadlines:
        alerts.append(
            {
                "type": "deadline_passed",
                "severity": "high",
                "tender_id": str(t.id),
                "message": f"The deadline for '{t.title}' has passed but it is still '{t.status.replace('_', ' ')}'.",
            }
        )
    overdue_tasks = db.scalar(select(func.count()).where(Task.organization_id == org, Task.due_date < date.today(), Task.status != "done")) or 0
    if overdue_tasks:
        alerts.append({"type": "tasks_overdue", "severity": "medium", "tender_id": None, "message": f"{overdue_tasks} task(s) are overdue."})
    failed_docs = db.scalar(select(func.count()).where(Document.organization_id == org, Document.status.in_(["failed", "needs_ocr"]))) or 0
    if failed_docs:
        alerts.append(
            {
                "type": "documents",
                "severity": "low",
                "tender_id": None,
                "message": f"{failed_docs} document(s) could not be fully processed (failed or need OCR).",
            }
        )
    mand_open = (
        db.scalar(
            select(func.count())
            .select_from(Requirement)
            .join(Tender, Tender.id == Requirement.tender_id)
            .where(
                Requirement.organization_id == org,
                Requirement.is_mandatory.is_(True),
                Requirement.response_status == "non_compliant",
                Tender.status.in_(ACTIVE_TENDER_STATUSES),
            )
        )
        or 0
    )
    if mand_open:
        alerts.append(
            {
                "type": "compliance",
                "severity": "high",
                "tender_id": None,
                "message": f"{mand_open} mandatory requirement(s) on active tenders are marked non-compliant.",
            }
        )

    recent = sorted(tenders, key=lambda t: t.updated_at, reverse=True)[:6]
    return {
        "stats": {
            "total_tenders": len(tenders),
            "active_tenders": sum(status_counts.get(s, 0) for s in ACTIVE_TENDER_STATUSES),
            "awaiting_review": status_counts.get("under_review", 0) + status_counts.get("internal_review", 0),
            "upcoming_deadlines": sum(1 for deadline, _ in upcoming_pairs if (deadline - now).days <= 30),
            "completed_proposals": status_counts.get("submitted", 0) + won + lost,
            "won": won,
            "lost": lost,
            "win_rate": round(won / decided * 100, 1) if decided else None,
            "overdue_tasks": overdue_tasks,
        },
        "pipeline": [{"status": s, "count": status_counts.get(s, 0)} for s in TENDER_STATUSES],
        "upcoming": [
            {"id": str(t.id), "title": t.title, "buyer": t.buyer, "status": t.status, "submission_deadline": deadline.isoformat()}
            for deadline, t in upcoming_pairs[:6]
        ],
        "recent_tenders": [
            {
                "id": str(t.id),
                "title": t.title,
                "buyer": t.buyer,
                "status": t.status,
                "priority": t.priority,
                "updated_at": t.updated_at.isoformat(),
                "submission_deadline": t.submission_deadline.isoformat() if t.submission_deadline else None,
            }
            for t in recent
        ],
        "recent_activity": [a.model_dump(mode="json") for a in _activity(db, org, 10)],
        "alerts": alerts,
    }


@router.get("/analytics")
def analytics(ctx: Ctx, db: DB, months: int = Query(12, ge=1, le=36)) -> dict:
    org = ctx.org_id
    now = datetime.now(UTC)
    tenders = list(db.scalars(select(Tender).where(Tender.organization_id == org)))
    status_counts = Counter(t.status for t in tenders if not t.is_archived)

    latest = _latest_decisions(db, org)
    recommendation_counts = Counter(a.recommendation for a in latest.values())
    final_counts = Counter(a.final_decision for a in latest.values() if a.final_decision)
    overrides = sum(1 for a in latest.values() if a.final_decision and a.final_decision != a.recommendation)

    # Monthly activity: tenders created / submitted-or-closed per month (by updated_at for closed ones).
    month_keys = []
    y, m = now.year, now.month
    for _ in range(months):
        month_keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    month_keys.reverse()
    created = Counter(t.created_at.strftime("%Y-%m") for t in tenders)
    won_m = Counter(t.updated_at.strftime("%Y-%m") for t in tenders if t.status == "won")
    lost_m = Counter(t.updated_at.strftime("%Y-%m") for t in tenders if t.status == "lost")
    runs = (
        db.execute(select(AnalysisRun.created_at).where(AnalysisRun.organization_id == org, AnalysisRun.created_at >= now - timedelta(days=31 * months)))
        .scalars()
        .all()
    )
    runs_m = Counter(r.strftime("%Y-%m") for r in runs)

    active = [t for t in tenders if not t.is_archived and t.status not in ("won", "lost", "withdrawn")]
    comp = percent_by_tender(db, org, [t.id for t in active])
    compliance_rows = [
        {"tender_id": str(t.id), "title": t.title, "requirements": comp[t.id][0], "percent_complete": comp[t.id][1]} for t in active if t.id in comp
    ]
    compliance_rows.sort(key=lambda r: r["percent_complete"] or 0)
    total_reqs = db.scalar(select(func.count()).where(Requirement.organization_id == org)) or 0
    done_reqs = db.scalar(select(func.count()).where(Requirement.organization_id == org, Requirement.response_status.in_(DONE_RESPONSE_STATUSES))) or 0

    deadlines = sorted(
        (
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "submission_deadline": t.submission_deadline.isoformat(),
                "days_left": (t.submission_deadline - now).days,
            }
            for t in active
            if t.submission_deadline and t.submission_deadline >= now
        ),
        key=lambda d: str(d["submission_deadline"]),
    )[:15]

    won, lost = status_counts.get("won", 0), status_counts.get("lost", 0)
    value_by_status: dict[str, float] = {}
    for t in tenders:
        if t.estimated_value is not None and not t.is_archived:
            value_by_status.setdefault(f"{t.status}|{t.currency}", 0.0)
            value_by_status[f"{t.status}|{t.currency}"] += float(t.estimated_value)
    return {
        "pipeline": [{"status": s, "count": status_counts.get(s, 0)} for s in TENDER_STATUSES],
        "decisions": {
            "recommendations": dict(recommendation_counts),
            "final": dict(final_counts),
            "overrides": overrides,
            "assessed_tenders": len(latest),
        },
        "win_loss": {
            "won": won,
            "lost": lost,
            "withdrawn": status_counts.get("withdrawn", 0),
            "win_rate": round(won / (won + lost) * 100, 1) if won + lost else None,
        },
        "compliance": {
            "total_requirements": total_reqs,
            "addressed": done_reqs,
            "percent_complete": round(done_reqs / total_reqs * 100, 1) if total_reqs else None,
            "by_tender": compliance_rows[:15],
        },
        "upcoming_deadlines": deadlines,
        "monthly": [
            {"month": k, "created": created.get(k, 0), "won": won_m.get(k, 0), "lost": lost_m.get(k, 0), "ai_runs": runs_m.get(k, 0)} for k in month_keys
        ],
        "pipeline_value": [{"status": k.split("|")[0], "currency": k.split("|")[1], "value": round(v, 2)} for k, v in value_by_status.items()],
    }
