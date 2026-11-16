from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

TenderStatus = Literal["draft", "under_review", "bid_decision", "in_preparation", "internal_review", "submitted", "won", "lost", "withdrawn"]
TenderType = Literal["tender", "rfp", "rfq", "rfi", "procurement", "questionnaire", "other"]
Priority = Literal["low", "medium", "high", "critical"]
Category = Literal[
    "eligibility",
    "mandatory",
    "technical",
    "commercial",
    "certification",
    "supporting_document",
    "evaluation",
    "submission",
    "other",
]
ResponseStatus = Literal["not_started", "in_progress", "compliant", "partially_compliant", "non_compliant", "needs_review"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done"]
Decision = Literal["bid", "no_bid", "needs_more_info"]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ tenders
class TenderBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    buyer: str = Field("", max_length=300)
    reference: str = Field("", max_length=120)
    description: str = Field("", max_length=20000)
    tender_type: TenderType = "tender"
    status: TenderStatus = "draft"
    priority: Priority = "medium"
    submission_deadline: datetime | None = None
    estimated_value: Decimal | None = Field(None, ge=0, le=Decimal("9999999999999999"), max_digits=18, decimal_places=2)
    currency: str = Field("EUR", min_length=3, max_length=3)
    notes: str = Field("", max_length=20000)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code.")
        return v.upper()

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title is required.")
        return v


class TenderCreate(TenderBase):
    pass


class TenderUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    buyer: str | None = Field(None, max_length=300)
    reference: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=20000)
    tender_type: TenderType | None = None
    status: TenderStatus | None = None
    priority: Priority | None = None
    submission_deadline: datetime | None = None
    estimated_value: Decimal | None = Field(None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(None, min_length=3, max_length=3)
    notes: str | None = Field(None, max_length=20000)
    is_archived: bool | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code.")
        return v.upper()


class TenderOut(Orm, TenderBase):
    id: uuid.UUID
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    created_by_id: uuid.UUID | None


class TenderListItem(TenderOut):
    document_count: int = 0
    requirement_count: int = 0
    compliance_percent: float | None = None


class TenderDetail(TenderOut):
    document_count: int
    requirement_count: int
    compliance: ComplianceSummary
    open_task_count: int
    latest_decision: str | None
    created_by_name: str | None


# ------------------------------------------------------------------ documents
class DocumentOut(Orm):
    id: uuid.UUID
    tender_id: uuid.UUID
    original_filename: str
    content_type: str
    file_ext: str
    size_bytes: int
    status: str
    status_message: str
    page_count: int | None
    char_count: int
    processed_at: datetime | None
    created_at: datetime


class DocumentTextOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    status: str
    pages: list[dict[str, Any]]


# ------------------------------------------------------------------ analysis
class AnalysisRunOut(Orm):
    id: uuid.UUID
    tender_id: uuid.UUID
    kind: str
    status: str
    provider: str
    model: str
    is_demo: bool
    input_tokens: int | None
    output_tokens: int | None
    result: dict[str, Any] | None
    error_message: str
    created_at: datetime
    completed_at: datetime | None


# ------------------------------------------------------------------ requirements / compliance
class RequirementCreate(BaseModel):
    description: str = Field(..., min_length=3, max_length=5000)
    category: Category = "other"
    is_mandatory: bool = False
    priority: Priority = "medium"
    source_document_name: str = Field("", max_length=255)
    source_page: int | None = Field(None, ge=1, le=100000)


class RequirementUpdate(BaseModel):
    description: str | None = Field(None, min_length=3, max_length=5000)
    category: Category | None = None
    is_mandatory: bool | None = None
    priority: Priority | None = None
    response_status: ResponseStatus | None = None
    assignee_id: uuid.UUID | None = None
    evidence: str | None = Field(None, max_length=20000)
    comments: str | None = Field(None, max_length=20000)
    clear_assignee: bool = False


class RequirementOut(Orm):
    id: uuid.UUID
    tender_id: uuid.UUID
    document_id: uuid.UUID | None
    analysis_run_id: uuid.UUID | None
    description: str
    category: str
    is_mandatory: bool
    priority: str
    source_document_name: str
    source_page: int | None
    source_quote: str | None
    source_verified: bool
    origin: str
    confidence: float | None
    response_status: str
    assignee_id: uuid.UUID | None
    assignee_name: str | None = None
    evidence: str
    comments: str
    position: int
    created_at: datetime
    updated_at: datetime


class ComplianceSummary(BaseModel):
    total: int
    mandatory_total: int
    by_status: dict[str, int]
    addressed: int
    percent_complete: float
    mandatory_percent_complete: float


# ------------------------------------------------------------------ bid / no-bid
class BidAssessmentOut(Orm):
    id: uuid.UUID
    tender_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    is_demo: bool
    recommendation: str
    score: int
    summary: str
    factors: list[dict[str, Any]]
    advantages: list[str]
    risks: list[str]
    missing_information: list[str]
    next_steps: list[str]
    final_decision: str | None
    final_reasoning: str
    decided_by_id: uuid.UUID | None
    decided_by_name: str | None = None
    decided_at: datetime | None
    created_at: datetime
    provider: str | None = None
    model: str | None = None


class BidDecisionIn(BaseModel):
    final_decision: Decision
    final_reasoning: str = Field(..., min_length=3, max_length=10000)


# ------------------------------------------------------------------ proposals / company
class ProposalCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    use_ai_outline: bool = False


class ProposalUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    status: Literal["draft", "in_review", "final"] | None = None


class SectionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    guidance: str = Field("", max_length=5000)
    content: str = Field("", max_length=100000)
    requirement_id: uuid.UUID | None = None


class SectionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    guidance: str | None = Field(None, max_length=5000)
    content: str | None = Field(None, max_length=100000)
    position: int | None = Field(None, ge=0, le=10000)


class SectionGenerateIn(BaseModel):
    mode: Literal["draft", "improve"] = "draft"
    instructions: str = Field("", max_length=4000)


class SectionOut(Orm):
    id: uuid.UUID
    proposal_id: uuid.UUID
    requirement_id: uuid.UUID | None
    title: str
    guidance: str
    content: str
    position: int
    ai_generated: bool
    is_demo: bool
    updated_at: datetime


class ProposalOut(Orm):
    id: uuid.UUID
    tender_id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    section_count: int = 0


class ProposalDetail(ProposalOut):
    sections: list[SectionOut]


class CoverageOut(BaseModel):
    total_requirements: int
    covered: int
    unanswered: list[RequirementOut]
    placeholder_sections: list[uuid.UUID]


class CompanyProfileIn(BaseModel):
    company_name: str = Field("", max_length=200)
    overview: str = Field("", max_length=20000)
    services: str = Field("", max_length=20000)
    capabilities: str = Field("", max_length=20000)
    experience: str = Field("", max_length=50000)
    certifications: str = Field("", max_length=20000)
    client_references: str = Field("", max_length=50000)
    team: str = Field("", max_length=50000)
    differentiators: str = Field("", max_length=20000)
    website: str = Field("", max_length=300)


class CompanyProfileOut(CompanyProfileIn):
    updated_at: datetime | None = None
    completeness: int = 0


# ------------------------------------------------------------------ assistant
class AssistantQuestionIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=4000)


class AssistantMessageOut(Orm):
    id: uuid.UUID
    role: str
    content: str
    is_demo: bool
    provider: str
    model: str
    supported: bool | None
    sources: list[dict[str, Any]] | None
    created_at: datetime


# ------------------------------------------------------------------ tasks
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field("", max_length=20000)
    tender_id: uuid.UUID | None = None
    requirement_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    status: TaskStatus = "todo"
    priority: Priority = "medium"
    due_date: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=20000)
    assignee_id: uuid.UUID | None = None
    clear_assignee: bool = False
    status: TaskStatus | None = None
    priority: Priority | None = None
    due_date: date | None = None
    clear_due_date: bool = False


class CommentIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


class CommentOut(Orm):
    id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str | None = None
    body: str
    created_at: datetime


class TaskOut(Orm):
    id: uuid.UUID
    tender_id: uuid.UUID | None
    tender_title: str | None = None
    requirement_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    assignee_name: str | None = None
    created_by_id: uuid.UUID | None
    title: str
    description: str
    status: str
    priority: str
    due_date: date | None
    completed_at: datetime | None
    is_overdue: bool = False
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime


class TaskDetail(TaskOut):
    comments: list[CommentOut]


# ------------------------------------------------------------------ activity / settings
class ActivityOut(Orm):
    id: uuid.UUID
    tender_id: uuid.UUID | None
    tender_title: str | None = None
    actor_name: str | None = None
    action: str
    summary: str
    created_at: datetime


class AISettingsIn(BaseModel):
    provider: Literal["default", "none", "demo", "openai", "anthropic", "gemini"]
    model: str = Field("", max_length=100)
    api_key: str | None = Field(None, max_length=500, description="Write-only. Empty string clears the stored key.")


class AISettingsOut(BaseModel):
    provider: str
    model: str
    api_key_stored: bool
    api_key_hint: str
    effective: dict[str, Any]
    org_keys_allowed: bool
    encryption_available: bool
    server_default_provider: str


TenderDetail.model_rebuild()
