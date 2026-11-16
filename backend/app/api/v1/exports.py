"""Export centre: tender summary, analysis report, compliance matrix, bid report and proposal drafts."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import DB, Ctx
from app.api.v1.tenders import STATUS_LABELS
from app.models import AnalysisRun, BidAssessment, Document, Requirement, Tender
from app.services.access import get_proposal, get_tender, log_activity, user_names
from app.services.compliance import summary_for_tender
from app.services.exports import Report, generated_stamp, render_csv, render_docx, render_pdf, slugify

router = APIRouter(tags=["exports"])

ExportKind = Literal["summary", "analysis", "compliance", "bid", "proposal"]
ExportFormat = Literal["pdf", "docx", "csv"]
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv; charset=utf-8",
}
REQ_HEADERS = ["#", "Requirement", "Category", "Mandatory", "Priority", "Source", "Source verified", "Origin", "Status", "Assignee", "Evidence", "Comments"]


def _label(v: str | None) -> str:
    return (v or "").replace("_", " ").capitalize()


def _source(r: Requirement) -> str:
    if not r.source_document_name:
        return "Not available"
    loc = f", page {r.source_page}" if r.source_page else ""
    return f"{r.source_document_name}{loc}"


def _requirement_rows(db, reqs: list[Requirement]) -> list[list[str]]:
    names = user_names(db, {r.assignee_id for r in reqs})
    return [
        [
            str(i),
            r.description,
            _label(r.category),
            "Yes" if r.is_mandatory else "No",
            _label(r.priority),
            _source(r),
            "Yes" if r.source_verified else "No",
            {"ai": "AI-extracted", "demo": "Demo heuristic", "manual": "User-entered"}.get(r.origin, r.origin),
            _label(r.response_status),
            names.get(r.assignee_id, ""),
            r.evidence,
            r.comments,
        ]
        for i, r in enumerate(reqs, start=1)
    ]


def _overview(report: Report, t: Tender) -> None:
    report.kv(
        [
            ("Buyer", t.buyer),
            ("Reference", t.reference),
            ("Type", t.tender_type.upper()),
            ("Status", STATUS_LABELS[t.status]),
            ("Priority", _label(t.priority)),
            ("Submission deadline", t.submission_deadline.strftime("%d %b %Y %H:%M UTC") if t.submission_deadline else "Not set"),
            ("Estimated value", f"{t.estimated_value:,.2f} {t.currency}" if t.estimated_value is not None else "Not set"),
        ]
    )


def _ai_notice(run_like, is_demo: bool) -> str:
    if is_demo:
        return "DEMO MODE: this content was produced by a rule-based heuristic, not by an AI model. Verify everything before use."
    model = f" ({run_like.provider} / {run_like.model})" if run_like is not None else ""
    return f"AI-GENERATED CONTENT{model}: this is a draft decision aid. Verify all information against the source documents."


@router.get("/tenders/{tender_id}/exports/{kind}")
def export(
    tender_id: uuid.UUID,
    kind: ExportKind,
    ctx: Ctx,
    db: DB,
    fmt: ExportFormat = Query("pdf", alias="format"),
    proposal_id: uuid.UUID | None = None,
) -> Response:
    t = get_tender(db, ctx.org_id, tender_id)
    subtitle = f"{t.title} · {generated_stamp()}"
    reqs = list(db.scalars(select(Requirement).where(Requirement.tender_id == t.id, Requirement.organization_id == ctx.org_id).order_by(Requirement.position)))

    if fmt == "csv" and kind != "compliance":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "CSV export is available for the compliance matrix only.")

    if kind == "compliance":
        rows = _requirement_rows(db, reqs)
        if fmt == "csv":
            body = render_csv(REQ_HEADERS, rows)
        else:
            comp = summary_for_tender(db, ctx.org_id, t.id)
            report = Report("Compliance Matrix", subtitle)
            report.notice(
                "Requirement descriptions marked 'AI-extracted' or 'Demo heuristic' were generated automatically and must be checked against the source documents. 'Source verified' means the quoted text was found in the uploaded document."
            )
            report.kv(
                [
                    ("Requirements", str(comp.total)),
                    ("Mandatory", str(comp.mandatory_total)),
                    ("Completion", f"{comp.percent_complete}%"),
                    ("Mandatory completion", f"{comp.mandatory_percent_complete}%"),
                ]
            )
            report.h("Requirements")
            report.table(["#", "Requirement", "Mand.", "Source", "Status", "Evidence"], [[r[0], r[1], r[3], r[5], r[8], r[10]] for r in rows])
            body = render_pdf(report) if fmt == "pdf" else render_docx(report)

    elif kind == "summary":
        comp = summary_for_tender(db, ctx.org_id, t.id)
        docs = list(db.scalars(select(Document).where(Document.tender_id == t.id).order_by(Document.created_at)))
        latest = db.scalar(select(BidAssessment).where(BidAssessment.tender_id == t.id).order_by(BidAssessment.created_at.desc()).limit(1))
        report = Report("Tender Summary", subtitle)
        report.h("Overview")
        _overview(report, t)
        if t.description:
            report.h("Description")
            report.p(t.description)
        report.h("Compliance")
        report.kv(
            [("Requirements", str(comp.total)), ("Completion", f"{comp.percent_complete}%"), ("Mandatory completion", f"{comp.mandatory_percent_complete}%")]
        )
        report.h("Documents")
        report.table(["File", "Status", "Pages"], [[d.original_filename, _label(d.status), str(d.page_count or "-")] for d in docs])
        report.h("Bid decision")
        if latest:
            report.kv(
                [
                    ("Recommendation" + (" (demo)" if latest.is_demo else " (AI-assisted)"), f"{_label(latest.recommendation)} - {latest.score}/100"),
                    ("Final decision", _label(latest.final_decision) if latest.final_decision else "Not recorded"),
                    ("Reasoning", latest.final_reasoning),
                ]
            )
        else:
            report.p("No bid/no-bid assessment recorded.")
        if t.notes:
            report.h("Internal notes")
            report.p(t.notes)
        body = render_pdf(report) if fmt == "pdf" else render_docx(report)

    elif kind == "analysis":
        run = db.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.tender_id == t.id, AnalysisRun.kind == "tender_analysis", AnalysisRun.status == "succeeded")
            .order_by(AnalysisRun.created_at.desc())
            .limit(1)
        )
        if run is None or not run.result:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No completed analysis exists for this tender.")
        res = run.result
        report = Report("Tender Analysis Report", subtitle)
        report.notice(_ai_notice(run, run.is_demo))
        for w in res.get("warnings", []):
            report.notice(w)
        ov = res.get("overview", {})
        report.h("Extracted overview")
        report.kv(
            [
                (k.replace("_", " ").capitalize(), ov.get(k) or "Not stated in the documents")
                for k in ("buyer", "title", "reference", "submission_deadline", "contract_duration", "estimated_value")
            ]
        )
        report.p(ov.get("summary", ""))

        def loc(item: dict) -> str:
            if not item.get("verified"):
                return "Source unavailable / unverified"
            return f"{item.get('source_document')}, {item.get('location') or ''}".strip(", ")

        report.h("Evaluation criteria")
        report.table(
            ["Criterion", "Weight", "Source"], [[c.get("name", ""), c.get("weight") or "Not stated", loc(c)] for c in res.get("evaluation_criteria", [])]
        )
        report.h("Important dates")
        report.table(["Date", "Event", "Source"], [[d.get("date_text", ""), d.get("label", ""), loc(d)] for d in res.get("important_dates", [])])
        report.h("Submission instructions")
        report.bullets(res.get("submission_instructions", []) or ["None identified."])
        report.h("Risks")
        report.table(["Risk", "Severity", "Source"], [[r.get("description", ""), _label(r.get("severity")), loc(r)] for r in res.get("risks", [])])
        report.h("Missing information")
        report.bullets(res.get("missing_information", []) or ["None identified."])
        report.h("Requirements")
        rows = _requirement_rows(db, reqs)
        report.table(["#", "Requirement", "Category", "Mand.", "Source", "Verified"], [[r[0], r[1], r[2], r[3], r[5], r[6]] for r in rows])
        body = render_pdf(report) if fmt == "pdf" else render_docx(report)

    elif kind == "bid":
        a = db.scalar(
            select(BidAssessment)
            .where(BidAssessment.tender_id == t.id, BidAssessment.organization_id == ctx.org_id)
            .order_by(BidAssessment.created_at.desc())
            .limit(1)
        )
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No bid/no-bid assessment exists for this tender.")
        run = db.get(AnalysisRun, a.analysis_run_id) if a.analysis_run_id else None
        names = user_names(db, {a.decided_by_id})
        report = Report("Bid / No-Bid Report", subtitle)
        report.notice(_ai_notice(run, a.is_demo) + " The score is a decision aid, not a guarantee of success.")
        _overview(report, t)
        report.h("Recommendation")
        report.kv(
            [
                ("Recommendation", _label(a.recommendation)),
                ("Score", f"{a.score}/100"),
                ("Final decision", _label(a.final_decision) if a.final_decision else "Not yet recorded"),
                ("Decided by", names.get(a.decided_by_id, "")),
                ("Reasoning", a.final_reasoning),
            ]
        )
        report.p(a.summary)
        report.h("Factor assessment")
        report.table(
            ["Factor", "Rating", "Score", "Assessment"],
            [[f.get("name", ""), _label(f.get("rating")), str(f.get("score", "")), f.get("assessment", "")] for f in a.factors],
        )
        for title_, items in (
            ("Advantages", a.advantages),
            ("Risks", a.risks),
            ("Missing information", a.missing_information),
            ("Recommended next steps", a.next_steps),
        ):
            report.h(title_)
            report.bullets(items or ["None listed."])
        body = render_pdf(report) if fmt == "pdf" else render_docx(report)

    else:  # proposal
        if proposal_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "proposal_id is required for proposal exports.")
        p = get_proposal(db, ctx.org_id, proposal_id)
        if p.tender_id != t.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found.")
        report = Report(p.title, f"Proposal draft ({_label(p.status)}) for {t.title} · {generated_stamp()}")
        if any(s.is_demo for s in p.sections):
            report.notice("DRAFT - contains demo-mode template text. Replace every [COMPANY INFORMATION REQUIRED] placeholder before submission.")
        elif any(s.ai_generated for s in p.sections):
            report.notice(
                "DRAFT - contains AI-generated text. Review all content and replace every [COMPANY INFORMATION REQUIRED] placeholder before submission."
            )
        else:
            report.notice("DRAFT proposal.")
        for s in p.sections:
            report.h(s.title)
            report.p(s.content or "[Section not yet written]")
        body = render_pdf(report) if fmt == "pdf" else render_docx(report)
        log_activity(db, ctx.org_id, ctx.user.id, "export.created", f"Exported proposal '{p.title}' ({fmt.upper()})", t.id)
        db.commit()
        return Response(body, media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{slugify(p.title)}.{fmt}"'})

    log_activity(db, ctx.org_id, ctx.user.id, "export.created", f"Exported {kind} ({fmt.upper()})", t.id)
    db.commit()
    return Response(body, media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{slugify(t.title)}-{kind}.{fmt}"'})
