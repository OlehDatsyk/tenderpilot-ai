import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleHelp, Loader2, Sparkles } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { DemoBadge } from "@/components/badges";
import { Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useAIStatus, useApiMutation } from "@/lib/hooks";
import type { AnalysisRun, SourcedItem } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function Source({ item }: { item: SourcedItem }) {
  if (!item.verified)
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted" title="The quoted text could not be found in the documents">
        <CircleHelp className="h-3 w-3" /> Source unavailable
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-700" title={item.quote ?? ""}>
      <CheckCircle2 className="h-3 w-3" /> {item.source_document}
      {item.location ? `, ${item.location}` : ""}
    </span>
  );
}

export function AIRequiredNotice() {
  const ai = useAIStatus();
  if (!ai.data || ai.data.configured) return null;
  return (
    <Notice tone="blue" icon={<Sparkles className="h-4 w-4" />}>
      AI is not configured, so this feature is unavailable. An admin can configure a provider (or enable demo mode) in{" "}
      <Link className="underline" to="/settings?tab=ai">Settings → AI provider</Link>.
    </Notice>
  );
}

export function AnalysisTab({ tenderId }: { tenderId: string }) {
  const qc = useQueryClient();
  const ai = useAIStatus();
  const latest = useQuery({
    queryKey: ["analysis-latest", tenderId],
    queryFn: () => api<AnalysisRun | null>(`/api/v1/tenders/${tenderId}/analysis/latest`),
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.status) ? 2500 : false),
  });
  const run = latest.data;
  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (prevStatus.current && prevStatus.current !== run?.status && run?.status === "succeeded") {
      qc.invalidateQueries({ queryKey: ["requirements", tenderId] });
      qc.invalidateQueries({ queryKey: ["tender", tenderId] });
      qc.invalidateQueries({ queryKey: ["compliance", tenderId] });
    }
    prevStatus.current = run?.status;
  }, [run?.status, qc, tenderId]);

  const start = useApiMutation(() => api<AnalysisRun>(`/api/v1/tenders/${tenderId}/analysis`, { method: "POST" }), {
    success: "Analysis started",
    invalidate: [["analysis-latest", tenderId]],
  });
  const busy = run && ["queued", "running"].includes(run.status);
  const r = run?.result;

  return (
    <div className="space-y-5">
      <AIRequiredNotice />
      <Card
        title="AI tender analysis"
        description="Extracts requirements, criteria, dates and risks from the processed documents. Results are suggestions that must be reviewed."
        actions={
          <Button variant="secondary" onClick={() => start.mutate(undefined)} loading={start.isPending || !!busy} disabled={!ai.data?.configured}>
            <Sparkles className="h-4 w-4" /> {run ? "Re-run analysis" : "Run analysis"}
          </Button>
        }
      >
        {latest.isLoading ? (
          <LoadingBlock rows={2} />
        ) : latest.isError ? (
          <ErrorState error={latest.error} onRetry={() => latest.refetch()} />
        ) : !run ? (
          <EmptyState icon={<Sparkles className="h-5 w-5" />} title="No analysis yet" description="Upload documents, then run the analysis. Re-running keeps requirements your team has already worked on." />
        ) : (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {busy && (
              <Badge tone="blue">
                <Loader2 className="h-3 w-3 animate-spin" /> {run.status === "queued" ? "Queued" : "Analysing documents…"}
              </Badge>
            )}
            {run.status === "succeeded" && <Badge tone="green">Completed</Badge>}
            {run.status === "failed" && <Badge tone="red">Failed</Badge>}
            {run.is_demo ? <DemoBadge /> : <Badge tone="violet"><Sparkles className="h-3 w-3" /> {run.provider} · {run.model}</Badge>}
            <span className="text-muted">Started {formatDateTime(run.created_at)}</span>
            {run.input_tokens != null && <span className="text-muted">· {run.input_tokens.toLocaleString()} in / {(run.output_tokens ?? 0).toLocaleString()} out tokens</span>}
            {run.status === "failed" && <Notice tone="red" className="w-full">{run.error_message}</Notice>}
          </div>
        )}
      </Card>

      {r && run?.status === "succeeded" && (
        <>
          {r.warnings.map((w, i) => (
            <Notice key={i} tone="amber" icon={<AlertTriangle className="h-4 w-4" />}>{w}</Notice>
          ))}
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Extracted overview" description="As stated in the documents. Empty values were not found.">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                {(
                  [
                    ["Buyer", r.overview.buyer],
                    ["Title", r.overview.title],
                    ["Reference", r.overview.reference],
                    ["Submission deadline", r.overview.submission_deadline],
                    ["Contract duration", r.overview.contract_duration],
                    ["Estimated value", r.overview.estimated_value],
                  ] as const
                ).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-muted">{k}</dt>
                    <dd className="mt-0.5">{v || <span className="italic text-muted">Not stated</span>}</dd>
                  </div>
                ))}
              </dl>
              {r.overview.summary && <p className="prose-plain mt-4 border-t border-line pt-3 text-muted">{r.overview.summary}</p>}
            </Card>
            <Card title="Requirements" description="Review them in the Compliance tab.">
              <div className="grid grid-cols-3 gap-3 text-center">
                <div><div className="text-2xl font-semibold">{r.requirements_extracted}</div><div className="text-xs text-muted">Extracted</div></div>
                <div><div className="text-2xl font-semibold">{r.requirements_created}</div><div className="text-xs text-muted">Added (new)</div></div>
                <div><div className="text-2xl font-semibold text-emerald-700">{r.requirements_verified}</div><div className="text-xs text-muted">Source verified</div></div>
              </div>
              <p className="mt-4 text-xs text-muted">"Source verified" means the quoted passage was found word-for-word in an uploaded document. Page numbers are only shown when verified. Documents analysed: {r.documents_analysed.join(", ")}</p>
            </Card>
          </div>

          <Card title="Evaluation criteria">
            {r.evaluation_criteria.length === 0 ? <p className="text-sm text-muted">None identified.</p> : (
              <ul className="divide-y divide-line">
                {r.evaluation_criteria.map((c, i) => (
                  <li key={i} className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-center sm:justify-between">
                    <span className="text-sm">{c.name}</span>
                    <span className="flex items-center gap-3">
                      <Badge tone="navy">{c.weight ?? "Weight not stated"}</Badge>
                      <Source item={c} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Important dates">
              {r.important_dates.length === 0 ? <p className="text-sm text-muted">None identified.</p> : (
                <ul className="space-y-2.5">
                  {r.important_dates.map((d, i) => (
                    <li key={i} className="text-sm">
                      <div className="font-medium">{d.date_text}</div>
                      <div className="text-muted">{d.label}</div>
                      <Source item={d} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Risks">
              {r.risks.length === 0 ? <p className="text-sm text-muted">None identified.</p> : (
                <ul className="space-y-2.5">
                  {r.risks.map((x, i) => (
                    <li key={i} className="text-sm">
                      <div className="flex items-start gap-2">
                        <Badge tone={x.severity === "high" ? "red" : x.severity === "medium" ? "amber" : "slate"}>{x.severity}</Badge>
                        <span>{x.description}</span>
                      </div>
                      <div className="mt-1 pl-1"><Source item={x} /></div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Submission instructions">
              {r.submission_instructions.length === 0 ? <p className="text-sm text-muted">None identified.</p> : (
                <ul className="list-disc space-y-1.5 pl-5 text-sm">{r.submission_instructions.map((s, i) => <li key={i}>{s}</li>)}</ul>
              )}
            </Card>
            <Card title="Missing information">
              {r.missing_information.length === 0 ? <p className="text-sm text-muted">Nothing flagged.</p> : (
                <ul className="list-disc space-y-1.5 pl-5 text-sm">{r.missing_information.map((s, i) => <li key={i}>{s}</li>)}</ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
