"""AI-assisted workflows: tender analysis, bid/no-bid, proposal drafting and the research assistant.

Every workflow:
* reads only data belonging to the caller's organisation and the selected tender,
* wraps document text as untrusted data (see app.ai.prompts),
* validates model output with Pydantic before anything is stored,
* records provider/model/token usage on an AnalysisRun row, and
* labels demo-mode output as such.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai import demo
from app.ai.base import AIConfig, AIError
from app.ai.prompts import (
    ANALYSIS_SYSTEM,
    ASSISTANT_SYSTEM,
    BID_SYSTEM,
    OUTLINE_SYSTEM,
    SECTION_SYSTEM,
    DocBlock,
    build_document_context,
    sanitize,
)
from app.ai.schemas import (
    AssistantAnswerOutput,
    BidAssessmentOutput,
    ProposalOutlineOutput,
    SectionDraftOutput,
    TenderAnalysisOutput,
)
from app.ai.service import call_structured, require_configured, resolve_config
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    AnalysisRun,
    AssistantMessage,
    BidAssessment,
    CompanyProfile,
    Document,
    ProposalDraft,
    ProposalSection,
    Requirement,
    Tender,
)
from app.models.enums import DONE_RESPONSE_STATUSES
from app.services.access import log_activity

logger = logging.getLogger("tenderpilot.workflows")


# ----------------------------------------------------------------- helpers


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[‘’“”]", "'", text)
    text = re.sub(r"[^\w%€$£]+", " ", text)
    return " ".join(text.split())


def document_blocks(db: Session, org_id: uuid.UUID, tender_id: uuid.UUID) -> tuple[list[DocBlock], list[Document]]:
    docs = list(
        db.scalars(
            select(Document)
            .where(
                Document.tender_id == tender_id,
                Document.organization_id == org_id,
                Document.status.in_(["processed", "needs_ocr"]),
            )
            .order_by(Document.created_at)
        )
    )
    blocks = [DocBlock(d.original_filename, p.get("label") or "Section", p.get("text") or "") for d in docs for p in (d.pages or [])]
    return [b for b in blocks if b.text.strip()], docs


class SourceVerifier:
    """Checks AI-reported quotes against the actual extracted text. Never trusts model-reported pages."""

    def __init__(self, docs: list[Document]):
        self.docs = docs
        self._by_name = {d.original_filename.lower(): d for d in docs}
        self._norm_pages = {d.id: [(p.get("page"), p.get("label"), _norm(p.get("text", ""))) for p in (d.pages or [])] for d in docs}

    def verify(self, source_document: str | None, quote: str | None) -> dict[str, Any]:
        doc = self._by_name.get((source_document or "").strip().lower())
        result: dict[str, Any] = {
            "document_id": None,
            "source_document": doc.original_filename if doc else (source_document or ""),
            "page": None,
            "location": None,
            "quote": None,
            "verified": False,
        }
        if doc is not None:
            result["document_id"] = doc.id
        nq = _norm(quote or "")
        if len(nq) < 8:
            return result
        candidates = [doc] if doc is not None else self.docs
        for d in candidates:
            for page, label, text in self._norm_pages[d.id]:
                if nq in text:
                    result.update(document_id=d.id, source_document=d.original_filename, page=page, location=label, quote=quote, verified=True)
                    return result
        return result


def _start_run(db: Session, org_id: uuid.UUID, tender_id: uuid.UUID, user_id: uuid.UUID | None, kind: str, config: AIConfig) -> AnalysisRun:
    run = AnalysisRun(
        tender_id=tender_id,
        organization_id=org_id,
        created_by_id=user_id,
        kind=kind,
        status="running",
        provider=config.provider,
        model=config.model,
        is_demo=config.is_demo,
    )
    db.add(run)
    db.flush()
    return run


def _finish(run: AnalysisRun, result: dict[str, Any], in_tok: int | None = None, out_tok: int | None = None) -> None:
    run.status = "succeeded"
    run.result = result
    run.input_tokens = in_tok
    run.output_tokens = out_tok
    run.completed_at = datetime.now(UTC)


def _fail(run: AnalysisRun, message: str) -> None:
    run.status = "failed"
    run.error_message = message[:2000]
    run.completed_at = datetime.now(UTC)


def _profile_dict(db: Session, org_id: uuid.UUID) -> dict[str, str]:
    p = db.scalar(select(CompanyProfile).where(CompanyProfile.organization_id == org_id))
    fields = ["company_name", "overview", "services", "capabilities", "experience", "certifications", "client_references", "team", "differentiators", "website"]
    return {f: (getattr(p, f) if p else "") or "" for f in fields}


def _profile_block(profile: dict[str, str]) -> str:
    lines = [f"{k}: {sanitize(v)}" for k, v in profile.items() if v.strip()]
    body = "\n".join(lines) if lines else "(The company profile is empty - no verified company information is available.)"
    return f"<company_profile>\n{body}\n</company_profile>"


def _tender_block(t: Tender) -> str:
    return (
        "<project_data>\n"
        f"title: {sanitize(t.title)}\nbuyer: {sanitize(t.buyer)}\nreference: {sanitize(t.reference)}\n"
        f"type: {t.tender_type}\nstatus: {t.status}\n"
        f"submission_deadline: {t.submission_deadline.isoformat() if t.submission_deadline else 'not set'}\n"
        f"estimated_value: {f'{t.estimated_value} {t.currency}' if t.estimated_value is not None else 'not set'}\n"
        f"description: {sanitize(t.description)[:4000]}\n"
        "</project_data>"
    )


# ----------------------------------------------------------------- tender analysis


def create_analysis_run(db: Session, org_id: uuid.UUID, tender: Tender, user_id: uuid.UUID) -> AnalysisRun:
    config = resolve_config(db, org_id)
    require_configured(config)
    run = AnalysisRun(
        tender_id=tender.id,
        organization_id=org_id,
        created_by_id=user_id,
        kind="tender_analysis",
        status="queued",
        provider=config.provider,
        model=config.model,
        is_demo=config.is_demo,
    )
    db.add(run)
    log_activity(db, org_id, user_id, "analysis.started", f"Tender analysis started{' (demo mode)' if config.is_demo else ''}", tender.id)
    db.commit()
    return run


def execute_analysis_run(run_id: uuid.UUID) -> None:
    """Background job. Uses its own DB session."""
    db = SessionLocal()
    try:
        run = db.get(AnalysisRun, run_id)
        if run is None or run.status not in ("queued", "running"):
            return
        run.status = "running"
        db.commit()
        try:
            _do_analysis(db, run)
        except AIError as exc:
            db.rollback()
            run = db.get(AnalysisRun, run_id)
            assert run is not None
            _fail(run, str(exc))
        except Exception:  # noqa: BLE001 - background job must always record a final state
            logger.exception("Analysis run %s failed", run_id)
            db.rollback()
            run = db.get(AnalysisRun, run_id)
            assert run is not None
            _fail(run, "An unexpected error occurred during analysis.")
        db.commit()
    finally:
        db.close()


def _do_analysis(db: Session, run: AnalysisRun) -> None:
    tender = db.get(Tender, run.tender_id)
    assert tender is not None
    blocks, docs = document_blocks(db, run.organization_id, run.tender_id)
    if not blocks:
        _fail(run, "No processed documents with extractable text. Upload PDF, DOCX or TXT documents first.")
        return
    config = resolve_config(db, run.organization_id)
    warnings: list[str] = []
    in_tok = out_tok = None
    if config.is_demo:
        output = demo.analyze(blocks)
        warnings.append(demo.DEMO_LABEL)
    else:
        ctx = build_document_context(blocks, get_settings().ai_max_context_chars)
        if ctx.truncated:
            warnings.append(
                f"The documents were too long to analyse completely: {ctx.included_chars:,} of {ctx.total_chars:,} "
                "characters were included. Requirements in the remaining text were NOT analysed."
            )
        user = f"{_tender_block(tender)}\n\nTender documents:\n{ctx.text}"
        res = call_structured(config, ANALYSIS_SYSTEM, user, TenderAnalysisOutput, max_tokens=32000)
        output, in_tok, out_tok = res.data, res.input_tokens, res.output_tokens
        run.provider, run.model = res.provider, res.model

    verifier = SourceVerifier(docs)
    origin = "demo" if config.is_demo else "ai"

    # Replace previous AI/demo requirements the team has not touched; keep everything users worked on.
    untouched = select(Requirement.id).where(
        Requirement.tender_id == tender.id,
        Requirement.origin.in_(["ai", "demo"]),
        Requirement.response_status == "not_started",
        Requirement.evidence == "",
        Requirement.comments == "",
        Requirement.assignee_id.is_(None),
    )
    db.execute(delete(Requirement).where(Requirement.id.in_(untouched)).execution_options(synchronize_session=False))
    existing = {_norm(d) for d in db.scalars(select(Requirement.description).where(Requirement.tender_id == tender.id))}
    position = (db.scalar(select(func.max(Requirement.position)).where(Requirement.tender_id == tender.id)) or 0) + 1

    created = verified = 0
    for item in output.requirements:
        key = _norm(item.description)
        if not key or key in existing:
            continue
        existing.add(key)
        src = verifier.verify(item.source_document, item.quote)
        db.add(
            Requirement(
                tender_id=tender.id,
                organization_id=run.organization_id,
                analysis_run_id=run.id,
                document_id=src["document_id"],
                description=item.description.strip(),
                category=item.category,
                is_mandatory=item.is_mandatory,
                priority=item.priority,
                source_document_name=(src["source_document"] or "")[:255],
                source_page=src["page"],
                source_quote=src["quote"],
                source_verified=src["verified"],
                origin=origin,
                confidence=item.confidence,
                position=position,
            )
        )
        position += 1
        created += 1
        verified += 1 if src["verified"] else 0

    def _verified_list(items: list[Any]) -> list[dict[str, Any]]:
        out = []
        for it in items:
            d = it.model_dump()
            src = verifier.verify(d.get("source_document"), d.get("quote"))
            d.update(
                source_document=src["source_document"] or None,
                page=src["page"],
                location=src["location"],
                quote=src["quote"],
                verified=src["verified"],
            )
            d.pop("document_id", None)
            out.append(d)
        return out

    result = {
        "overview": output.overview.model_dump(),
        "evaluation_criteria": _verified_list(output.evaluation_criteria),
        "important_dates": _verified_list(output.important_dates),
        "risks": _verified_list(output.risks),
        "submission_instructions": output.submission_instructions,
        "missing_information": output.missing_information,
        "requirements_extracted": len(output.requirements),
        "requirements_created": created,
        "requirements_verified": verified,
        "documents_analysed": [d.original_filename for d in docs],
        "warnings": warnings,
        "is_demo": config.is_demo,
    }
    _finish(run, result, in_tok, out_tok)
    log_activity(
        db,
        run.organization_id,
        run.created_by_id,
        "analysis.completed",
        f"Analysis completed: {created} requirement(s) added, {verified} with verified source",
        tender.id,
    )


# ----------------------------------------------------------------- bid / no-bid


def _requirement_stats(db: Session, org_id: uuid.UUID, tender_id: uuid.UUID) -> tuple[dict[str, Any], list[Requirement]]:
    reqs = list(db.scalars(select(Requirement).where(Requirement.tender_id == tender_id, Requirement.organization_id == org_id).order_by(Requirement.position)))
    total = len(reqs)
    stats = {
        "total": total,
        "mandatory": sum(r.is_mandatory for r in reqs),
        "mandatory_non_compliant": sum(1 for r in reqs if r.is_mandatory and r.response_status == "non_compliant"),
        "compliant_ratio": (sum(1 for r in reqs if r.response_status == "compliant") / total) if total else 0.0,
        "certification_open": sum(1 for r in reqs if r.category == "certification" and r.response_status not in DONE_RESPONSE_STATUSES),
    }
    return stats, reqs


def generate_bid_assessment(db: Session, org_id: uuid.UUID, tender: Tender, user_id: uuid.UUID) -> BidAssessment:
    config = resolve_config(db, org_id)
    require_configured(config)
    run = _start_run(db, org_id, tender.id, user_id, "bid_assessment", config)
    stats, reqs = _requirement_stats(db, org_id, tender.id)
    profile = _profile_dict(db, org_id)
    try:
        if config.is_demo:
            out = demo.bid_assessment(
                deadline=tender.submission_deadline,
                has_value=tender.estimated_value is not None,
                requirement_stats=stats,
                profile=profile,
            )
            in_tok = out_tok = None
        else:
            req_lines = "\n".join(
                f"{i}. [{r.category}{', MANDATORY' if r.is_mandatory else ''}] status={r.response_status}: {sanitize(r.description)[:400]}"
                + (f" | evidence: {sanitize(r.evidence)[:300]}" if r.evidence else "")
                for i, r in enumerate(reqs[:250], start=1)
            )
            blocks, _ = document_blocks(db, org_id, tender.id)
            ctx = build_document_context(blocks, min(get_settings().ai_max_context_chars, 150_000))
            user = (
                f"Today's date: {datetime.now(UTC).date().isoformat()}\n{_tender_block(tender)}\n\n"
                f"{_profile_block(profile)}\n\n<project_data>\nRequirements and compliance status:\n{req_lines or '(none extracted yet)'}\n</project_data>\n\n"
                f"Tender document excerpts:\n{ctx.text}"
            )
            res = call_structured(config, BID_SYSTEM, user, BidAssessmentOutput)
            out, in_tok, out_tok = res.data, res.input_tokens, res.output_tokens
    except AIError as exc:
        _fail(run, str(exc))
        db.commit()
        raise
    assessment = BidAssessment(
        tender_id=tender.id,
        organization_id=org_id,
        analysis_run_id=run.id,
        created_by_id=user_id,
        is_demo=config.is_demo,
        recommendation=out.recommendation,
        score=out.score,
        summary=out.summary,
        factors=[f.model_dump() for f in out.factors],
        advantages=out.advantages,
        risks=out.risks,
        missing_information=out.missing_information,
        next_steps=out.next_steps,
    )
    db.add(assessment)
    _finish(run, {"recommendation": out.recommendation, "score": out.score, "is_demo": config.is_demo}, in_tok, out_tok)
    log_activity(db, org_id, user_id, "bid.assessed", f"Bid/no-bid assessment: {out.recommendation.replace('_', ' ')} ({out.score}/100)", tender.id)
    db.commit()
    return assessment


# ----------------------------------------------------------------- proposals


def generate_outline(db: Session, org_id: uuid.UUID, tender: Tender, proposal: ProposalDraft, user_id: uuid.UUID) -> None:
    config = resolve_config(db, org_id)
    require_configured(config)
    run = _start_run(db, org_id, tender.id, user_id, "proposal_outline", config)
    _, reqs = _requirement_stats(db, org_id, tender.id)
    req_dicts = [{"description": r.description, "is_mandatory": r.is_mandatory, "category": r.category} for r in reqs]
    try:
        if config.is_demo:
            out = demo.proposal_outline(req_dicts)
            in_tok = out_tok = None
        else:
            req_lines = "\n".join(
                f"{i}. [{r['category']}{', MANDATORY' if r['is_mandatory'] else ''}] {sanitize(str(r['description']))[:400]}"
                for i, r in enumerate(req_dicts[:250], start=1)
            )
            run_row = db.scalar(
                select(AnalysisRun)
                .where(AnalysisRun.tender_id == tender.id, AnalysisRun.kind == "tender_analysis", AnalysisRun.status == "succeeded")
                .order_by(AnalysisRun.created_at.desc())
                .limit(1)
            )
            criteria = (run_row.result or {}).get("evaluation_criteria", []) if run_row else []
            crit = "\n".join(f"- {sanitize(str(c.get('name')))} ({c.get('weight') or 'weight not stated'})" for c in criteria)
            user = f"{_tender_block(tender)}\n\n<project_data>\nEvaluation criteria:\n{crit or '(not available)'}\n\nRequirements:\n{req_lines or '(none extracted yet)'}\n</project_data>"
            res = call_structured(config, OUTLINE_SYSTEM, user, ProposalOutlineOutput)
            out, in_tok, out_tok = res.data, res.input_tokens, res.output_tokens
    except AIError as exc:
        _fail(run, str(exc))
        db.commit()
        raise
    start = len(proposal.sections)
    for i, s in enumerate(out.sections):
        req_id = None
        nums = [n for n in s.requirement_numbers if 1 <= n <= len(reqs)]
        if len(nums) == 1:
            req_id = reqs[nums[0] - 1].id
        guidance = s.guidance
        if nums:
            guidance += "\n\nAnswers requirement(s): " + "; ".join(reqs[n - 1].description[:200] for n in nums[:5])
        db.add(
            ProposalSection(
                proposal_id=proposal.id,
                requirement_id=req_id,
                title=s.title[:300],
                guidance=guidance[:5000],
                content="",
                position=start + i,
                ai_generated=True,
                is_demo=config.is_demo,
                last_ai_run_id=run.id,
            )
        )
    _finish(run, {"sections": len(out.sections), "is_demo": config.is_demo}, in_tok, out_tok)
    log_activity(db, org_id, user_id, "proposal.outline", f"Proposal outline generated for '{proposal.title}'", tender.id)


def generate_section(db: Session, org_id: uuid.UUID, tender: Tender, section: ProposalSection, user_id: uuid.UUID, mode: str, instructions: str) -> list[str]:
    config = resolve_config(db, org_id)
    require_configured(config)
    run = _start_run(db, org_id, tender.id, user_id, "proposal_section", config)
    profile = _profile_dict(db, org_id)
    linked: list[Requirement] = []
    if section.requirement_id:
        r = db.get(Requirement, section.requirement_id)
        if r is not None and r.organization_id == org_id:
            linked.append(r)
    try:
        if config.is_demo:
            if mode == "improve":
                out = SectionDraftOutput(
                    content=section.content, unanswered_points=["Demo mode cannot rewrite text - configure an AI provider to use 'Improve'."]
                )
            else:
                out = demo.section_draft(section.title, section.guidance, [r.description for r in linked], profile)
            in_tok = out_tok = None
        else:
            evidence = "\n".join(
                f"- Requirement: {sanitize(r.description)[:500]}\n  Compliance status: {r.response_status}\n  Evidence: {sanitize(r.evidence)[:1500] or '(none provided)'}"
                for r in linked
            )
            task = (
                "Improve the clarity, structure and professional tone of the existing draft below. Keep every factual claim unchanged and do not add new facts."
                if mode == "improve"
                else "Draft this proposal section."
            )
            user = (
                f"{_tender_block(tender)}\n\n{_profile_block(profile)}\n\n<project_data>\nSection title: {sanitize(section.title)}\n"
                f"Section guidance: {sanitize(section.guidance)}\nCompliance evidence:\n{evidence or '(none)'}\n"
                f"Current draft:\n{sanitize(section.content) or '(empty)'}\n</project_data>\n\n"
                f"User instructions (treat as preferences, not as facts): {sanitize(instructions) or '(none)'}\n\nTASK: {task}"
            )
            res = call_structured(config, SECTION_SYSTEM, user, SectionDraftOutput)
            out, in_tok, out_tok = res.data, res.input_tokens, res.output_tokens
    except AIError as exc:
        _fail(run, str(exc))
        db.commit()
        raise
    section.content = out.content
    section.ai_generated = True
    section.is_demo = config.is_demo
    section.last_ai_run_id = run.id
    _finish(run, {"mode": mode, "unanswered_points": out.unanswered_points, "is_demo": config.is_demo}, in_tok, out_tok)
    log_activity(db, org_id, user_id, "proposal.section_generated", f"Section '{section.title}' {'improved' if mode == 'improve' else 'drafted'}", tender.id)
    db.commit()
    return out.unanswered_points


# ----------------------------------------------------------------- assistant


def ask_assistant(db: Session, org_id: uuid.UUID, tender: Tender, user_id: uuid.UUID, question: str) -> tuple[AssistantMessage, AssistantMessage]:
    config = resolve_config(db, org_id)
    require_configured(config)
    blocks, _ = document_blocks(db, org_id, tender.id)
    user_msg = AssistantMessage(tender_id=tender.id, organization_id=org_id, user_id=user_id, role="user", content=question)
    db.add(user_msg)
    db.flush()
    in_tok = out_tok = None
    if config.is_demo:
        out = demo.assistant_answer(question, blocks)
    else:
        stats, reqs = _requirement_stats(db, org_id, tender.id)
        req_lines = "\n".join(
            f"- [{r.category}{', MANDATORY' if r.is_mandatory else ''}] status={r.response_status}: {sanitize(r.description)[:300]}" for r in reqs[:200]
        )
        history = list(
            db.scalars(
                select(AssistantMessage)
                .where(AssistantMessage.tender_id == tender.id, AssistantMessage.user_id == user_id, AssistantMessage.id != user_msg.id)
                .order_by(AssistantMessage.created_at.desc())
                .limit(6)
            )
        )[::-1]
        hist = "\n".join(f"{m.role}: {sanitize(m.content)[:1500]}" for m in history)
        ctx = build_document_context(blocks, min(get_settings().ai_max_context_chars, 250_000))
        user = (
            f"{_tender_block(tender)}\n\n<project_data>\nCompliance matrix ({stats['total']} requirements):\n{req_lines or '(none)'}\n"
            f"Previous conversation:\n{hist or '(none)'}\n</project_data>\n\nTender documents:\n{ctx.text or '(no processed documents)'}\n\n"
            f"Question: {sanitize(question)}"
        )
        try:
            res = call_structured(config, ASSISTANT_SYSTEM, user, AssistantAnswerOutput, max_tokens=8000)
        except AIError:
            db.rollback()
            raise
        out, in_tok, out_tok = res.data, res.input_tokens, res.output_tokens
        if ctx.truncated:
            out.answer += "\n\nNote: the documents were too long to include completely; parts were not considered."
    run = _start_run(db, org_id, tender.id, user_id, "assistant", config)
    _finish(run, {"supported": out.supported, "is_demo": config.is_demo}, in_tok, out_tok)
    reply = AssistantMessage(
        tender_id=tender.id,
        organization_id=org_id,
        user_id=user_id,
        role="assistant",
        content=out.answer,
        is_demo=config.is_demo,
        provider=config.provider,
        model=config.model,
        supported=out.supported,
        sources=[s.model_dump() for s in out.sources],
    )
    db.add(reply)
    db.commit()
    return user_msg, reply


def recover_interrupted_runs() -> int:
    """Mark runs left running by a previous process as failed (called on startup)."""
    db = SessionLocal()
    try:
        runs = list(db.scalars(select(AnalysisRun).where(AnalysisRun.status.in_(["queued", "running"]))))
        for r in runs:
            _fail(r, "Interrupted by a server restart. Please run the analysis again.")
        db.commit()
        return len(runs)
    finally:
        db.close()
