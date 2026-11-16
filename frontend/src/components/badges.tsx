import { CheckCircle2, CircleHelp, FlaskConical, Sparkles, User } from "lucide-react";
import { categoryLabel, decisionLabel, responseLabel, statusLabel } from "@/lib/labels";
import type { Category, Decision, Priority, ResponseStatus, TenderStatus } from "@/lib/types";
import { Badge, type Tone } from "./ui";

const statusTone: Record<TenderStatus, Tone> = {
  draft: "slate",
  under_review: "blue",
  bid_decision: "violet",
  in_preparation: "teal",
  internal_review: "amber",
  submitted: "navy",
  won: "green",
  lost: "red",
  withdrawn: "slate",
};
export function StatusBadge({ status }: { status: TenderStatus }) {
  return <Badge tone={statusTone[status]}>{statusLabel(status)}</Badge>;
}

const priorityTone: Record<Priority, Tone> = { low: "slate", medium: "blue", high: "amber", critical: "red" };
export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge tone={priorityTone[priority]}>{priority[0].toUpperCase() + priority.slice(1)}</Badge>;
}

const responseTone: Record<ResponseStatus, Tone> = {
  not_started: "slate",
  in_progress: "blue",
  compliant: "green",
  partially_compliant: "amber",
  non_compliant: "red",
  needs_review: "violet",
};
export function ResponseBadge({ status }: { status: ResponseStatus }) {
  return <Badge tone={responseTone[status]}>{responseLabel(status)}</Badge>;
}

export function CategoryBadge({ category }: { category: Category }) {
  return <Badge tone="slate">{categoryLabel(category)}</Badge>;
}

const decisionTone: Record<Decision, Tone> = { bid: "green", no_bid: "red", needs_more_info: "amber" };
export function DecisionBadge({ decision }: { decision: Decision }) {
  return <Badge tone={decisionTone[decision]}>{decisionLabel(decision)}</Badge>;
}

/** Distinguishes AI suggestions, demo heuristics and user-provided information. */
export function OriginBadge({ origin }: { origin: "ai" | "demo" | "manual" }) {
  if (origin === "ai")
    return (
      <Badge tone="violet" title="Extracted by an AI model - verify against the source document">
        <Sparkles className="h-3 w-3" /> AI-extracted
      </Badge>
    );
  if (origin === "demo")
    return (
      <Badge tone="amber" title="Produced by the rule-based demo heuristic - no AI model was used">
        <FlaskConical className="h-3 w-3" /> Demo
      </Badge>
    );
  return (
    <Badge tone="slate" title="Entered by a team member">
      <User className="h-3 w-3" /> User-entered
    </Badge>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <Badge tone="green" title="The quoted text was found in the uploaded document">
      <CheckCircle2 className="h-3 w-3" /> Source verified
    </Badge>
  ) : (
    <Badge tone="slate" title="No quote could be matched in the documents - source location unavailable">
      <CircleHelp className="h-3 w-3" /> Unverified
    </Badge>
  );
}

export function DemoBadge() {
  return (
    <Badge tone="amber" title="Rule-based demo output - no AI model was used">
      <FlaskConical className="h-3 w-3" /> Demo mode
    </Badge>
  );
}
