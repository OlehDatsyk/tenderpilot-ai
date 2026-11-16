export type TenderStatus =
  | "draft"
  | "under_review"
  | "bid_decision"
  | "in_preparation"
  | "internal_review"
  | "submitted"
  | "won"
  | "lost"
  | "withdrawn";
export type TenderType = "tender" | "rfp" | "rfq" | "rfi" | "procurement" | "questionnaire" | "other";
export type Priority = "low" | "medium" | "high" | "critical";
export type ResponseStatus = "not_started" | "in_progress" | "compliant" | "partially_compliant" | "non_compliant" | "needs_review";
export type Category =
  | "eligibility"
  | "mandatory"
  | "technical"
  | "commercial"
  | "certification"
  | "supporting_document"
  | "evaluation"
  | "submission"
  | "other";
export type TaskStatus = "todo" | "in_progress" | "blocked" | "done";
export type Decision = "bid" | "no_bid" | "needs_more_info";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  job_title: string | null;
  created_at: string;
  last_login_at: string | null;
  organization: { id: string; name: string; created_at: string };
  role: "owner" | "admin" | "member";
}

export interface Tender {
  id: string;
  title: string;
  buyer: string;
  reference: string;
  description: string;
  tender_type: TenderType;
  status: TenderStatus;
  priority: Priority;
  submission_deadline: string | null;
  estimated_value: string | null;
  currency: string;
  notes: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  created_by_id: string | null;
  document_count?: number;
  requirement_count?: number;
  compliance_percent?: number | null;
}

export interface ComplianceSummary {
  total: number;
  mandatory_total: number;
  by_status: Record<ResponseStatus, number>;
  addressed: number;
  percent_complete: number;
  mandatory_percent_complete: number;
}

export interface TenderDetail extends Tender {
  document_count: number;
  requirement_count: number;
  compliance: ComplianceSummary;
  open_task_count: number;
  latest_decision: Decision | null;
  created_by_name: string | null;
}

export interface DocumentItem {
  id: string;
  tender_id: string;
  original_filename: string;
  content_type: string;
  file_ext: string;
  size_bytes: number;
  status: "pending" | "processing" | "processed" | "needs_ocr" | "failed";
  status_message: string;
  page_count: number | null;
  char_count: number;
  processed_at: string | null;
  created_at: string;
}

export interface DocumentText {
  id: string;
  original_filename: string;
  status: string;
  pages: { page: number | null; label: string; text: string }[];
}

export interface SourcedItem {
  source_document: string | null;
  page: number | null;
  location: string | null;
  quote: string | null;
  verified: boolean;
}

export interface AnalysisResult {
  overview: {
    buyer: string | null;
    title: string | null;
    reference: string | null;
    submission_deadline: string | null;
    contract_duration: string | null;
    estimated_value: string | null;
    summary: string;
  };
  evaluation_criteria: (SourcedItem & { name: string; weight: string | null; description: string })[];
  important_dates: (SourcedItem & { label: string; date_text: string })[];
  risks: (SourcedItem & { description: string; severity: "low" | "medium" | "high" })[];
  submission_instructions: string[];
  missing_information: string[];
  requirements_extracted: number;
  requirements_created: number;
  requirements_verified: number;
  documents_analysed: string[];
  warnings: string[];
  is_demo: boolean;
}

export interface AnalysisRun {
  id: string;
  tender_id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  provider: string;
  model: string;
  is_demo: boolean;
  input_tokens: number | null;
  output_tokens: number | null;
  result: AnalysisResult | null;
  error_message: string;
  created_at: string;
  completed_at: string | null;
}

export interface Requirement {
  id: string;
  tender_id: string;
  document_id: string | null;
  analysis_run_id: string | null;
  description: string;
  category: Category;
  is_mandatory: boolean;
  priority: Priority;
  source_document_name: string;
  source_page: number | null;
  source_quote: string | null;
  source_verified: boolean;
  origin: "ai" | "demo" | "manual";
  confidence: number | null;
  response_status: ResponseStatus;
  assignee_id: string | null;
  assignee_name: string | null;
  evidence: string;
  comments: string;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface BidFactor {
  name: string;
  rating: "strong" | "adequate" | "weak" | "unknown";
  score: number;
  assessment: string;
}

export interface BidAssessment {
  id: string;
  tender_id: string;
  is_demo: boolean;
  recommendation: Decision;
  score: number;
  summary: string;
  factors: BidFactor[];
  advantages: string[];
  risks: string[];
  missing_information: string[];
  next_steps: string[];
  final_decision: Decision | null;
  final_reasoning: string;
  decided_by_name: string | null;
  decided_at: string | null;
  created_at: string;
  provider: string | null;
  model: string | null;
}

export interface ProposalSection {
  id: string;
  proposal_id: string;
  requirement_id: string | null;
  title: string;
  guidance: string;
  content: string;
  position: number;
  ai_generated: boolean;
  is_demo: boolean;
  updated_at: string;
}

export interface Proposal {
  id: string;
  tender_id: string;
  title: string;
  status: "draft" | "in_review" | "final";
  created_at: string;
  updated_at: string;
  section_count: number;
}

export interface ProposalDetail extends Proposal {
  sections: ProposalSection[];
}

export interface Coverage {
  total_requirements: number;
  covered: number;
  unanswered: Requirement[];
  placeholder_sections: string[];
}

export interface CompanyProfile {
  company_name: string;
  overview: string;
  services: string;
  capabilities: string;
  experience: string;
  certifications: string;
  client_references: string;
  team: string;
  differentiators: string;
  website: string;
  updated_at: string | null;
  completeness: number;
}

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  is_demo: boolean;
  provider: string;
  model: string;
  supported: boolean | null;
  sources: { document: string; location: string | null; quote: string | null }[] | null;
  created_at: string;
}

export interface Task {
  id: string;
  tender_id: string | null;
  tender_title: string | null;
  requirement_id: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  created_by_id: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  due_date: string | null;
  completed_at: string | null;
  is_overdue: boolean;
  comment_count: number;
  created_at: string;
  updated_at: string;
}

export interface TaskComment {
  id: string;
  author_id: string | null;
  author_name: string | null;
  body: string;
  created_at: string;
}

export interface TaskDetail extends Task {
  comments: TaskComment[];
}

export interface Member {
  user_id: string;
  email: string;
  full_name: string;
  job_title: string | null;
  role: "owner" | "admin" | "member";
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  token?: string;
}

export interface Activity {
  id: string;
  tender_id: string | null;
  tender_title: string | null;
  actor_name: string | null;
  action: string;
  summary: string;
  created_at: string;
}

export interface AIStatus {
  provider: string;
  model: string;
  source: string;
  configured: boolean;
  is_demo: boolean;
  api_key_set: boolean;
  message: string | null;
}

export interface AISettings {
  provider: string;
  model: string;
  api_key_stored: boolean;
  api_key_hint: string;
  effective: AIStatus;
  org_keys_allowed: boolean;
  encryption_available: boolean;
  server_default_provider: string;
}

export interface Dashboard {
  stats: {
    total_tenders: number;
    active_tenders: number;
    awaiting_review: number;
    upcoming_deadlines: number;
    completed_proposals: number;
    won: number;
    lost: number;
    win_rate: number | null;
    overdue_tasks: number;
  };
  pipeline: { status: TenderStatus; count: number }[];
  upcoming: { id: string; title: string; buyer: string; status: TenderStatus; submission_deadline: string }[];
  recent_tenders: {
    id: string;
    title: string;
    buyer: string;
    status: TenderStatus;
    priority: Priority;
    updated_at: string;
    submission_deadline: string | null;
  }[];
  recent_activity: Activity[];
  alerts: { type: string; severity: "low" | "medium" | "high"; tender_id: string | null; message: string }[];
}

export interface Analytics {
  pipeline: { status: TenderStatus; count: number }[];
  decisions: {
    recommendations: Partial<Record<Decision, number>>;
    final: Partial<Record<Decision, number>>;
    overrides: number;
    assessed_tenders: number;
  };
  win_loss: { won: number; lost: number; withdrawn: number; win_rate: number | null };
  compliance: {
    total_requirements: number;
    addressed: number;
    percent_complete: number | null;
    by_tender: { tender_id: string; title: string; requirements: number; percent_complete: number | null }[];
  };
  upcoming_deadlines: { id: string; title: string; status: TenderStatus; submission_deadline: string; days_left: number }[];
  monthly: { month: string; created: number; won: number; lost: number; ai_runs: number }[];
  pipeline_value: { status: TenderStatus; currency: string; value: number }[];
}
