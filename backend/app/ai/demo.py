"""Deterministic, rule-based demo engine.

Used when AI_PROVIDER=demo (development, tests, evaluation). It never calls an AI model and its
outputs are always labelled as demo results. Quotes are literal sentences from the documents, so
source locations it reports are genuine - but its judgement is a simple keyword heuristic.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal, cast

from app.ai.prompts import PLACEHOLDER, DocBlock
from app.ai.schemas import (
    AssistantAnswerOutput,
    AssistantSource,
    BidAssessmentOutput,
    BidFactor,
    Category,
    EvaluationCriterion,
    ExtractedRequirement,
    ImportantDate,
    OutlineSection,
    Priority,
    ProposalOutlineOutput,
    Risk,
    SectionDraftOutput,
    TenderAnalysisOutput,
    TenderOverview,
)

DEMO_LABEL = "Demo mode — rule-based heuristic output. No AI model was used."

_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'])|\n+")
_REQ_RE = re.compile(
    r"\b(must|shall|is required|are required|required to|mandatory|should|need to|needs to|is expected to|are expected to|minimum of)\b",
    re.I,
)
_MANDATORY_RE = re.compile(r"\b(must|shall|mandatory|is required|are required|required to|minimum of)\b", re.I)
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_RE = re.compile(
    rf"\b(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\s+\d{{4}}|(?:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}})",
    re.I,
)
_CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("certification", re.compile(r"\b(ISO\s?\d+|certif\w*|accredit\w*|Cyber Essentials|SOC ?2)\b", re.I)),
    ("submission", re.compile(r"\b(submit\w*|submission|portal|format|copies|font|page limit|file name|sealed|envelope)\b", re.I)),
    ("supporting_document", re.compile(r"\b(attach\w*|enclose|provide (?:a )?cop(?:y|ies)|CVs?|evidence of|proof of|statement of|declaration)\b", re.I)),
    ("eligibility", re.compile(r"\b(eligib\w*|exclusion|registered|turnover|insolvency|convicted|years of experience|track record)\b", re.I)),
    ("commercial", re.compile(r"\b(price|pricing|payment|invoice|cost|fee|liabilit\w*|insurance|penalt\w*|discount|VAT|currency|financial)\b", re.I)),
    (
        "technical",
        re.compile(
            r"\b(system|software|integration|support|availability|SLA|security|data|hosting|platform|service level|interface|API|uptime|backup|accessib\w*|technical)\b",
            re.I,
        ),
    ),
]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if 12 <= len(s.strip()) <= 600]


def _category(sentence: str) -> str:
    for name, pattern in _CATEGORY_RULES:
        if pattern.search(sentence):
            return name
    return "mandatory" if _MANDATORY_RE.search(sentence) else "other"


def _first_match(blocks: list[DocBlock], pattern: re.Pattern[str]) -> tuple[str | None, DocBlock | None, str | None]:
    for b in blocks:
        for line in b.text.splitlines():
            m = pattern.search(line)
            if m:
                return m.group(1).strip(" .:;"), b, line.strip()
    return None, None, None


def _page(b: DocBlock | None) -> int | None:
    if b is None:
        return None
    m = re.fullmatch(r"Page (\d+)", b.label)
    return int(m.group(1)) if m else None


def analyze(blocks: list[DocBlock]) -> TenderAnalysisOutput:
    requirements: list[ExtractedRequirement] = []
    seen: set[str] = set()
    criteria: list[EvaluationCriterion] = []
    dates: list[ImportantDate] = []
    risks: list[Risk] = []
    instructions: list[str] = []

    for b in blocks:
        for s in _sentences(b.text):
            key = re.sub(r"\W+", " ", s.lower()).strip()
            if _REQ_RE.search(s) and key not in seen and len(requirements) < 150:
                seen.add(key)
                cat = _category(s)
                mandatory = bool(_MANDATORY_RE.search(s))
                priority = "critical" if mandatory and cat in ("eligibility", "certification") else "high" if mandatory else "medium"
                requirements.append(
                    ExtractedRequirement(
                        description=s[:600],
                        category=cast(Category, cat),
                        is_mandatory=mandatory,
                        priority=cast(Priority, priority),
                        source_document=b.name,
                        page=_page(b),
                        quote=s[:300],
                        confidence=0.4,
                    )
                )
                if cat == "submission" and len(instructions) < 20:
                    instructions.append(s[:300])
            if "%" in s and re.search(r"\b(quality|price|technical|criteri\w*|weight\w*|score\w*|evaluat\w*|cost)\b", s, re.I):
                pct = re.search(r"(\d{1,3}(?:\.\d+)?\s?%)", s)
                if len(criteria) < 30:
                    criteria.append(
                        EvaluationCriterion(
                            name=s[:120],
                            weight=pct.group(1) if pct else None,
                            description=s[:300],
                            source_document=b.name,
                            page=_page(b),
                            quote=s[:300],
                        )
                    )
            dm = _DATE_RE.search(s)
            if dm and len(dates) < 30:
                dates.append(ImportantDate(label=s[:150], date_text=dm.group(1), source_document=b.name, page=_page(b), quote=s[:300]))
            if re.search(r"\b(unlimited liability|liquidated damages|penalt\w*|termination for convenience|indemnif\w*)\b", s, re.I) and len(risks) < 20:
                risks.append(Risk(description=s[:300], severity="high", source_document=b.name, page=_page(b), quote=s[:300]))

    buyer, _, _ = _first_match(blocks, re.compile(r"(?:Contracting Authority|Buyer|Issued by|Purchaser|Client)\s*[:\-]\s*(.{3,120})", re.I))
    reference, _, _ = _first_match(
        blocks, re.compile(r"(?:Tender|Contract|RFP|RFQ)?\s*(?:Reference|Ref\.?|Number|No\.)\s*[:\-]\s*([A-Za-z0-9/_.\-]{3,60})", re.I)
    )
    # Most specific phrasing first, so e.g. a clarification-question cut-off is not taken as the tender deadline.
    deadline = None
    for phrase in (
        r"deadline for (?:receipt|submission) of (?:tenders|bids|proposals|responses)",
        r"(?:tenders|bids|proposals|responses) must be (?:received|submitted)",
        r"submission deadline|closing date",
        r"deadline",
    ):
        deadline, _, _ = _first_match(blocks, re.compile(rf"(?:{phrase})[^.\n]*?({_DATE_RE.pattern})", re.I))
        if deadline:
            break
    duration, _, _ = _first_match(blocks, re.compile(r"(?:contract (?:duration|period|term)|duration of the contract)\s*(?:is|of|:)?\s*([^.\n]{3,80})", re.I))
    value, _, _ = _first_match(blocks, re.compile(r"(?:estimated (?:contract )?value|budget|maximum value)\s*(?:is|of|:)?\s*([^.\n]{3,80})", re.I))

    missing = []
    if not deadline:
        missing.append("No submission deadline could be identified by the heuristic.")
    if not value:
        missing.append("No estimated contract value or budget was found.")
    if not criteria:
        missing.append("No weighted evaluation criteria were found.")
    if not requirements:
        missing.append("No requirement sentences (must/shall/required) were found.")

    return TenderAnalysisOutput(
        overview=TenderOverview(
            buyer=buyer,
            reference=reference,
            submission_deadline=deadline,
            contract_duration=duration,
            estimated_value=value,
            summary=f"{DEMO_LABEL} Scanned {len(blocks)} text block(s) and found {len(requirements)} candidate requirement sentence(s). Review every item before relying on it.",
        ),
        requirements=requirements,
        evaluation_criteria=criteria,
        important_dates=dates,
        submission_instructions=instructions,
        risks=risks,
        missing_information=missing,
    )


def bid_assessment(*, deadline: datetime | None, has_value: bool, requirement_stats: dict, profile: dict) -> BidAssessmentOutput:
    def has(field: str) -> bool:
        return bool((profile.get(field) or "").strip())

    factors: list[BidFactor] = []

    def add(name: str, score: int | None, text: str) -> None:
        if score is None:
            factors.append(BidFactor(name=name, rating="unknown", score=5, assessment=text))
        else:
            rating: Literal["strong", "adequate", "weak"] = "strong" if score >= 8 else "adequate" if score >= 5 else "weak"
            factors.append(BidFactor(name=name, rating=rating, score=score, assessment=text))

    total = requirement_stats.get("total", 0)
    non_compliant_mand = requirement_stats.get("mandatory_non_compliant", 0)
    compliant_ratio = requirement_stats.get("compliant_ratio", 0.0)

    if non_compliant_mand:
        add("Eligibility", 2, f"{non_compliant_mand} mandatory requirement(s) are marked non-compliant.")
    elif not has("overview"):
        add("Eligibility", None, "Company profile is incomplete, so eligibility cannot be judged.")
    else:
        add("Eligibility", 6, "No mandatory requirement is marked non-compliant yet.")
    add(
        "Technical capability",
        6 if has("capabilities") else None,
        "Capabilities are recorded in the company profile." if has("capabilities") else "No capabilities recorded in the company profile.",
    )
    add(
        "Relevant experience",
        6 if has("experience") else None,
        "Experience is recorded in the company profile." if has("experience") else "No verified experience recorded.",
    )
    add("Available resources", 6 if has("team") else None, "Team information is recorded." if has("team") else "No team/resource information recorded.")
    if deadline is None:
        add("Deadline feasibility", None, "No submission deadline set on the tender.")
    else:
        days = (deadline - datetime.now(UTC)).days
        score = 9 if days > 30 else 6 if days >= 14 else 4 if days >= 7 else 1
        add("Deadline feasibility", score, f"{days} day(s) remain until the submission deadline.")
    add("Commercial attractiveness", 6 if has_value else None, "An estimated contract value is recorded." if has_value else "No estimated value recorded.")
    if total == 0:
        add("Contract complexity", None, "No requirements have been extracted yet.")
    else:
        add("Contract complexity", 7 if total < 20 else 5 if total < 60 else 3, f"{total} requirement(s) recorded.")
    if total:
        add("Compliance risks", max(1, min(10, round(compliant_ratio * 10))), f"{round(compliant_ratio * 100)}% of requirements are marked compliant.")
    else:
        add("Compliance risks", None, "No compliance data yet.")
    cert_gap = requirement_stats.get("certification_open", 0)
    add(
        "Missing qualifications",
        None if not has("certifications") else (4 if cert_gap else 7),
        f"{cert_gap} certification requirement(s) not yet confirmed." if has("certifications") else "No certifications recorded in the company profile.",
    )

    known = [f for f in factors if f.rating != "unknown"]
    unknown = len(factors) - len(known)
    score = round(sum(f.score for f in factors) / len(factors) * 10)
    rec: Literal["bid", "no_bid", "needs_more_info"]
    if unknown >= 4:
        rec = "needs_more_info"
    elif non_compliant_mand:
        rec = "no_bid"
    elif score >= 60:
        rec = "bid"
    elif score < 40:
        rec = "no_bid"
    else:
        rec = "needs_more_info"
    missing = [f"{f.name}: {f.assessment}" for f in factors if f.rating == "unknown"]
    return BidAssessmentOutput(
        recommendation=rec,
        score=score,
        summary=f"{DEMO_LABEL} Score computed from recorded project data with fixed rules.",
        factors=factors,
        advantages=[f"{f.name}: {f.assessment}" for f in factors if f.rating == "strong"],
        risks=[f"{f.name}: {f.assessment}" for f in factors if f.rating == "weak"],
        missing_information=missing,
        next_steps=[
            "Complete the company profile with verified information.",
            "Review the compliance matrix and set a status for every mandatory requirement.",
            "Confirm resource availability for the delivery period.",
        ],
    )


def proposal_outline(requirements: list[dict]) -> ProposalOutlineOutput:
    sections = [
        OutlineSection(title="Executive Summary", guidance="Summarise the buyer's needs, your proposed solution and why you are a credible supplier."),
        OutlineSection(title="Understanding of Requirements", guidance="Restate the buyer's objectives and key constraints in your own words."),
        OutlineSection(title="Methodology and Delivery Approach", guidance="Describe phases, activities, deliverables and how you will manage delivery."),
        OutlineSection(title="Project Timeline", guidance="Provide milestones aligned with the tender's important dates."),
        OutlineSection(title="Team and Governance", guidance="Describe roles and governance. Use only verified staff information."),
        OutlineSection(title="Quality and Risk Management", guidance="Explain quality assurance and how key risks will be mitigated."),
    ]
    for i, r in enumerate(requirements, start=1):
        if r.get("is_mandatory") and len(sections) < 30:
            short = r["description"].strip().rstrip(".")
            title = f"Requirement {i}: {short[:70]}{'…' if len(short) > 70 else ''}"
            sections.append(OutlineSection(title=title, guidance=r["description"][:400], requirement_numbers=[i]))
    return ProposalOutlineOutput(sections=sections)


def section_draft(title: str, guidance: str, requirements: list[str], profile: dict) -> SectionDraftOutput:
    lines = [f"[DEMO DRAFT — template text, not AI-generated. Replace every {PLACEHOLDER} before submission.]", ""]
    if guidance:
        lines += [f"Purpose of this section: {guidance}", ""]
    if (profile.get("company_name") or "").strip():
        lines.append(f"{profile['company_name'].strip()} is pleased to respond to this section.")
    else:
        lines.append(f"{PLACEHOLDER}: company name is pleased to respond to this section.")
    if (profile.get("overview") or "").strip():
        lines += ["", "About us (from the verified company profile):", profile["overview"].strip()[:1200]]
    unanswered = []
    if requirements:
        lines += ["", "How we meet the requirements:"]
        for r in requirements:
            lines.append(f"- Requirement: {r}")
            lines.append(f"  Our response: {PLACEHOLDER}: describe how you meet this requirement and the evidence you hold.")
            unanswered.append(r)
    lines += ["", f"Relevant experience: {PLACEHOLDER}: add a verified, relevant project example."]
    return SectionDraftOutput(content="\n".join(lines), unanswered_points=unanswered or [f"{title}: content required"])


def assistant_answer(question: str, blocks: list[DocBlock]) -> AssistantAnswerOutput:
    words = {w for w in re.findall(r"[a-z]{4,}", question.lower())} - {
        "what",
        "which",
        "when",
        "where",
        "there",
        "their",
        "about",
        "should",
        "would",
        "could",
        "tender",
        "this",
    }
    scored: list[tuple[int, DocBlock, str]] = []
    for b in blocks:
        for s in _sentences(b.text):
            low = s.lower()
            score = sum(1 for w in words if w in low)
            if score:
                scored.append((score, b, s))
    scored.sort(key=lambda t: -t[0])
    top = scored[:4]
    if not top:
        return AssistantAnswerOutput(
            answer=f"{DEMO_LABEL} No passage in the uploaded documents matches the words in your question, so it cannot be answered from the documents.",
            supported=False,
        )
    answer = f"{DEMO_LABEL} These passages best match the words in your question:\n\n" + "\n".join(f'- "{s[:300]}" ({b.name}, {b.label})' for _, b, s in top)
    return AssistantAnswerOutput(
        answer=answer,
        supported=True,
        sources=[AssistantSource(document=b.name, location=b.label, quote=s[:300]) for _, b, s in top],
    )
