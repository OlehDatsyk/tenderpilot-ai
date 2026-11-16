import { useQuery } from "@tanstack/react-query";
import { Gavel, Info, Scale, Sparkles } from "lucide-react";
import { useState } from "react";
import { DecisionBadge, DemoBadge } from "@/components/badges";
import { Badge, Button, Card, EmptyState, ErrorState, Field, LoadingBlock, Notice, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAIStatus, useApiMutation } from "@/lib/hooks";
import { DECISIONS } from "@/lib/labels";
import type { BidAssessment, Decision, TenderDetail } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";
import { AIRequiredNotice } from "./AnalysisTab";

const ratingTone = { strong: "green", adequate: "blue", weak: "red", unknown: "slate" } as const;

function DecisionForm({ a, tenderId }: { a: BidAssessment; tenderId: string }) {
  const [decision, setDecision] = useState<Decision>(a.final_decision ?? a.recommendation);
  const [reasoning, setReasoning] = useState(a.final_reasoning);
  const save = useApiMutation(
    () => api<BidAssessment>(`/api/v1/bid-assessments/${a.id}/decision`, { method: "POST", body: { final_decision: decision, final_reasoning: reasoning } }),
    { success: "Decision recorded", invalidate: [["bids", tenderId], ["tender", tenderId], ["activity", tenderId]] },
  );
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
      className="space-y-3"
    >
      <Field label="Final decision" htmlFor="final-decision">
        <Select id="final-decision" value={decision} onChange={(e) => setDecision(e.target.value as Decision)}>
          {DECISIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </Select>
      </Field>
      {decision !== a.recommendation && <Notice tone="blue">You are overriding the recommendation ({DECISIONS.find((d) => d.value === a.recommendation)?.label}). Please record why.</Notice>}
      <Field label="Reasoning" htmlFor="final-reasoning" hint="Required. Recorded with your name and the time.">
        <Textarea id="final-reasoning" rows={4} value={reasoning} onChange={(e) => setReasoning(e.target.value)} />
      </Field>
      <Button type="submit" loading={save.isPending} disabled={reasoning.trim().length < 3}>
        <Gavel className="h-4 w-4" /> Record decision
      </Button>
      {a.decided_at && <p className="text-xs text-muted">Last recorded by {a.decided_by_name ?? "unknown"} on {formatDateTime(a.decided_at)}</p>}
    </form>
  );
}

export function BidTab({ tender }: { tender: TenderDetail }) {
  const ai = useAIStatus();
  const q = useQuery({ queryKey: ["bids", tender.id], queryFn: () => api<BidAssessment[]>(`/api/v1/tenders/${tender.id}/bid-assessments`) });
  const generate = useApiMutation(() => api<BidAssessment>(`/api/v1/tenders/${tender.id}/bid-assessments`, { method: "POST" }), {
    success: "Assessment generated",
    invalidate: [["bids", tender.id], ["activity", tender.id]],
  });
  const a = q.data?.[0];

  return (
    <div className="space-y-5">
      <AIRequiredNotice />
      <Notice tone="blue" icon={<Info className="h-4 w-4" />}>
        The score is an AI-assisted decision aid based on the documents, the compliance matrix and your verified company profile — it is not a guarantee of success. Your team makes the final decision.
      </Notice>
      <Card
        title="Bid / no-bid assessment"
        actions={
          <Button variant="secondary" onClick={() => generate.mutate(undefined)} loading={generate.isPending} disabled={!ai.data?.configured}>
            <Sparkles className="h-4 w-4" /> {a ? "Generate new assessment" : "Generate assessment"}
          </Button>
        }
      >
        {q.isLoading ? (
          <LoadingBlock />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !a ? (
          <EmptyState icon={<Scale className="h-5 w-5" />} title="No assessment yet" description="For better results, run the analysis and complete your company profile first." />
        ) : (
          <div className="space-y-6">
            <div className="flex flex-col gap-5 md:flex-row md:items-center">
              <div className="flex h-28 w-28 shrink-0 flex-col items-center justify-center rounded-full border-8 border-slate-100" style={{ borderTopColor: a.score >= 60 ? "#0d9488" : a.score >= 40 ? "#d97706" : "#dc2626" }}>
                <span className="text-3xl font-semibold tabular-nums">{a.score}</span>
                <span className="text-[11px] text-muted">/ 100</span>
              </div>
              <div className="min-w-0 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-muted">Recommendation:</span>
                  <DecisionBadge decision={a.recommendation} />
                  {a.is_demo ? <DemoBadge /> : <Badge tone="violet"><Sparkles className="h-3 w-3" /> AI-assisted · {a.model}</Badge>}
                </div>
                <p className="prose-plain text-muted">{a.summary}</p>
                <p className="text-xs text-muted">Generated {formatDateTime(a.created_at)}</p>
              </div>
            </div>
            <div className="-mx-5 overflow-x-auto">
              <table className="table-base min-w-[640px]">
                <thead><tr><th>Factor</th><th>Rating</th><th>Score</th><th>Assessment</th></tr></thead>
                <tbody>
                  {a.factors.map((f) => (
                    <tr key={f.name}>
                      <td className="font-medium">{f.name}</td>
                      <td><Badge tone={ratingTone[f.rating]}>{f.rating}</Badge></td>
                      <td className="tabular-nums">{f.rating === "unknown" ? "—" : `${f.score}/10`}</td>
                      <td className="text-muted">{f.assessment}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid gap-5 md:grid-cols-2">
              {(
                [
                  ["Main advantages", a.advantages, "text-emerald-700"],
                  ["Main risks", a.risks, "text-red-700"],
                  ["Missing information", a.missing_information, "text-amber-700"],
                  ["Recommended next steps", a.next_steps, "text-navy-700"],
                ] as const
              ).map(([title, items, color]) => (
                <div key={title}>
                  <h3 className={cn("mb-2 text-sm font-semibold", color)}>{title}</h3>
                  {items.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="text-sm text-muted">None listed.</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
      {a && (
        <Card title="Final decision" description="Record the team's decision. You may override the recommendation.">
          <DecisionForm key={a.id} a={a} tenderId={tender.id} />
        </Card>
      )}
      {q.data && q.data.length > 1 && (
        <Card title="Assessment history">
          <ul className="divide-y divide-line text-sm">
            {q.data.slice(1).map((x) => (
              <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="flex items-center gap-2"><DecisionBadge decision={x.recommendation} /> {x.score}/100 {x.is_demo && <DemoBadge />}</span>
                <span className="text-xs text-muted">{formatDateTime(x.created_at)}{x.final_decision ? ` · final: ${x.final_decision.replace("_", " ")}` : ""}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
