"""Pydantic schemas that every AI output must validate against before it is stored."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
Priority = Literal["low", "medium", "high", "critical"]


class SourceRef(BaseModel):
    source_document: str | None = Field(None, description="Exact document name as given in the context, or null.")
    page: int | None = Field(None, description="Page number ONLY if the passage is inside a 'Page N' block, else null.")
    quote: str | None = Field(None, description="Short verbatim quote (max 300 chars) copied exactly from the document, or null.")

    @field_validator("quote")
    @classmethod
    def _trim_quote(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v[:500] or None


class ExtractedRequirement(SourceRef):
    description: str = Field(..., min_length=3, max_length=2000)
    category: Category = "other"
    is_mandatory: bool = False
    priority: Priority = "medium"
    confidence: float = Field(0.5, ge=0, le=1)


class EvaluationCriterion(SourceRef):
    name: str = Field(..., max_length=300)
    weight: str | None = Field(None, description="Weight exactly as stated, e.g. '40%'. null if not stated.")
    description: str = ""


class ImportantDate(SourceRef):
    label: str = Field(..., max_length=200)
    date_text: str = Field(..., description="The date exactly as written in the document.")


class Risk(SourceRef):
    description: str = Field(..., max_length=1000)
    severity: Literal["low", "medium", "high"] = "medium"


class TenderOverview(BaseModel):
    buyer: str | None = None
    title: str | None = None
    reference: str | None = None
    submission_deadline: str | None = Field(None, description="As written in the document; null if not stated.")
    contract_duration: str | None = None
    estimated_value: str | None = Field(None, description="As written in the document; null if not stated.")
    summary: str = Field("", max_length=3000)


class TenderAnalysisOutput(BaseModel):
    overview: TenderOverview
    requirements: list[ExtractedRequirement] = Field(default_factory=list, max_length=400)
    evaluation_criteria: list[EvaluationCriterion] = Field(default_factory=list, max_length=100)
    important_dates: list[ImportantDate] = Field(default_factory=list, max_length=100)
    submission_instructions: list[str] = Field(default_factory=list, max_length=100)
    risks: list[Risk] = Field(default_factory=list, max_length=100)
    missing_information: list[str] = Field(default_factory=list, max_length=100)


class BidFactor(BaseModel):
    name: str
    rating: Literal["strong", "adequate", "weak", "unknown"]
    score: int = Field(..., ge=0, le=10)
    assessment: str


class BidAssessmentOutput(BaseModel):
    recommendation: Literal["bid", "no_bid", "needs_more_info"]
    score: int = Field(..., ge=0, le=100)
    summary: str
    factors: list[BidFactor] = Field(default_factory=list, max_length=20)
    advantages: list[str] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=30)
    missing_information: list[str] = Field(default_factory=list, max_length=30)
    next_steps: list[str] = Field(default_factory=list, max_length=30)


class OutlineSection(BaseModel):
    title: str = Field(..., max_length=300)
    guidance: str = ""
    requirement_numbers: list[int] = Field(default_factory=list, description="Numbers of the requirements this section answers.")


class ProposalOutlineOutput(BaseModel):
    sections: list[OutlineSection] = Field(..., min_length=1, max_length=40)


class SectionDraftOutput(BaseModel):
    content: str
    unanswered_points: list[str] = Field(default_factory=list)


class AssistantSource(BaseModel):
    document: str
    location: str | None = None
    quote: str | None = None


class AssistantAnswerOutput(BaseModel):
    answer: str
    supported: bool = Field(..., description="false if the provided context does not support an answer")
    sources: list[AssistantSource] = Field(default_factory=list, max_length=20)
