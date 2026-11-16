import type { Category, Decision, Priority, ResponseStatus, TaskStatus, TenderStatus, TenderType } from "./types";

export const TENDER_STATUSES: { value: TenderStatus; label: string }[] = [
  { value: "draft", label: "Draft" },
  { value: "under_review", label: "Under Review" },
  { value: "bid_decision", label: "Bid Decision" },
  { value: "in_preparation", label: "In Preparation" },
  { value: "internal_review", label: "Internal Review" },
  { value: "submitted", label: "Submitted" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
  { value: "withdrawn", label: "Withdrawn" },
];
export const statusLabel = (s: TenderStatus) => TENDER_STATUSES.find((x) => x.value === s)?.label ?? s;

export const TENDER_TYPES: { value: TenderType; label: string }[] = [
  { value: "tender", label: "Tender" },
  { value: "rfp", label: "RFP" },
  { value: "rfq", label: "RFQ" },
  { value: "rfi", label: "RFI" },
  { value: "procurement", label: "Procurement" },
  { value: "questionnaire", label: "Supplier questionnaire" },
  { value: "other", label: "Other" },
];
export const typeLabel = (t: TenderType) => TENDER_TYPES.find((x) => x.value === t)?.label ?? t;

export const PRIORITIES: { value: Priority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

export const RESPONSE_STATUSES: { value: ResponseStatus; label: string }[] = [
  { value: "not_started", label: "Not Started" },
  { value: "in_progress", label: "In Progress" },
  { value: "compliant", label: "Compliant" },
  { value: "partially_compliant", label: "Partially Compliant" },
  { value: "non_compliant", label: "Non-Compliant" },
  { value: "needs_review", label: "Needs Review" },
];
export const responseLabel = (s: ResponseStatus) => RESPONSE_STATUSES.find((x) => x.value === s)?.label ?? s;

export const CATEGORIES: { value: Category; label: string }[] = [
  { value: "eligibility", label: "Eligibility" },
  { value: "mandatory", label: "Mandatory" },
  { value: "technical", label: "Technical" },
  { value: "commercial", label: "Commercial" },
  { value: "certification", label: "Certification" },
  { value: "supporting_document", label: "Supporting document" },
  { value: "evaluation", label: "Evaluation" },
  { value: "submission", label: "Submission" },
  { value: "other", label: "Other" },
];
export const categoryLabel = (c: Category) => CATEGORIES.find((x) => x.value === c)?.label ?? c;

export const TASK_STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "todo", label: "To do" },
  { value: "in_progress", label: "In progress" },
  { value: "blocked", label: "Blocked" },
  { value: "done", label: "Done" },
];

export const DECISIONS: { value: Decision; label: string }[] = [
  { value: "bid", label: "Bid" },
  { value: "no_bid", label: "No-Bid" },
  { value: "needs_more_info", label: "Needs More Information" },
];
export const decisionLabel = (d: Decision) => DECISIONS.find((x) => x.value === d)?.label ?? d;

export const PROVIDERS: { value: string; label: string }[] = [
  { value: "default", label: "Server default" },
  { value: "none", label: "Disabled" },
  { value: "demo", label: "Demo mode (rule-based, no AI)" },
  { value: "anthropic", label: "Anthropic Claude" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Google Gemini" },
];
