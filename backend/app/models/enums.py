"""Allowed values for string-backed enumerations (validated in schemas, stored as strings)."""

from __future__ import annotations

TENDER_STATUSES = (
    "draft",
    "under_review",
    "bid_decision",
    "in_preparation",
    "internal_review",
    "submitted",
    "won",
    "lost",
    "withdrawn",
)
ACTIVE_TENDER_STATUSES = ("under_review", "bid_decision", "in_preparation", "internal_review")
CLOSED_TENDER_STATUSES = ("won", "lost", "withdrawn")
TENDER_TYPES = ("tender", "rfp", "rfq", "rfi", "procurement", "questionnaire", "other")
PRIORITIES = ("low", "medium", "high", "critical")

ROLES = ("owner", "admin", "member")

DOCUMENT_STATUSES = ("pending", "processing", "processed", "needs_ocr", "failed")
ALLOWED_EXTENSIONS = {
    "pdf": {"application/pdf"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "txt": {"text/plain"},
}

REQUIREMENT_CATEGORIES = (
    "eligibility",
    "mandatory",
    "technical",
    "commercial",
    "certification",
    "supporting_document",
    "evaluation",
    "submission",
    "other",
)
RESPONSE_STATUSES = (
    "not_started",
    "in_progress",
    "compliant",
    "partially_compliant",
    "non_compliant",
    "needs_review",
)
DONE_RESPONSE_STATUSES = ("compliant", "partially_compliant", "non_compliant")
REQUIREMENT_ORIGINS = ("ai", "demo", "manual")

ANALYSIS_KINDS = ("tender_analysis", "bid_assessment", "proposal_outline", "proposal_section", "assistant")
RUN_STATUSES = ("queued", "running", "succeeded", "failed")

BID_RECOMMENDATIONS = ("bid", "no_bid", "needs_more_info")

PROPOSAL_STATUSES = ("draft", "in_review", "final")
TASK_STATUSES = ("todo", "in_progress", "blocked", "done")
