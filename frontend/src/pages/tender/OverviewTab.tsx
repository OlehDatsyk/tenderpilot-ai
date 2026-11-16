import { useQuery } from "@tanstack/react-query";
import { CalendarClock, FileText, ListChecks, Scale } from "lucide-react";
import { DecisionBadge } from "@/components/badges";
import { Card, Progress, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { RESPONSE_STATUSES } from "@/lib/labels";
import type { Activity, TenderDetail } from "@/lib/types";
import { formatDateTime, formatMoney, relativeDeadline, timeAgo } from "@/lib/utils";

export function OverviewTab({ tender: t, onTab }: { tender: TenderDetail; onTab: (id: string) => void }) {
  const activity = useQuery({
    queryKey: ["activity", t.id],
    queryFn: () => api<Activity[]>(`/api/v1/activity?tender_id=${t.id}&limit=15`),
  });
  const c = t.compliance;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <button onClick={() => onTab("documents")} className="text-left">
          <Stat label="Documents" value={t.document_count} icon={<FileText className="h-4 w-4" />} />
        </button>
        <button onClick={() => onTab("compliance")} className="text-left">
          <Stat label="Requirements" value={t.requirement_count} icon={<ListChecks className="h-4 w-4" />} hint={`${c.mandatory_total} mandatory`} />
        </button>
        <button onClick={() => onTab("tasks")} className="text-left">
          <Stat label="Open tasks" value={t.open_task_count} icon={<CalendarClock className="h-4 w-4" />} />
        </button>
        <button onClick={() => onTab("bid")} className="text-left">
          <Stat label="Final decision" value={t.latest_decision ? <DecisionBadge decision={t.latest_decision} /> : <span className="text-base text-muted">Not recorded</span>} icon={<Scale className="h-4 w-4" />} />
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Project details" className="lg:col-span-2" description="User-provided information">
          <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted">Submission deadline</dt>
              <dd className="mt-0.5 font-medium">{formatDateTime(t.submission_deadline)}</dd>
              {t.submission_deadline && <dd className="text-xs text-muted">{relativeDeadline(t.submission_deadline)}</dd>}
            </div>
            <div>
              <dt className="text-xs text-muted">Estimated contract value</dt>
              <dd className="mt-0.5 font-medium">{formatMoney(t.estimated_value, t.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Created</dt>
              <dd className="mt-0.5">{formatDateTime(t.created_at)}{t.created_by_name ? ` by ${t.created_by_name}` : ""}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Last updated</dt>
              <dd className="mt-0.5">{formatDateTime(t.updated_at)}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-muted">Description</dt>
              <dd className="prose-plain mt-0.5">{t.description || <span className="text-muted">No description.</span>}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-muted">Internal notes</dt>
              <dd className="prose-plain mt-0.5">{t.notes || <span className="text-muted">No notes.</span>}</dd>
            </div>
          </dl>
        </Card>
        <Card title="Compliance progress">
          {c.total === 0 ? (
            <p className="text-sm text-muted">No requirements yet. Upload documents and run the AI analysis, or add requirements manually.</p>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="mb-1 flex justify-between text-sm"><span>All requirements</span><span className="font-medium tabular-nums">{c.percent_complete}%</span></div>
                <Progress value={c.percent_complete} />
              </div>
              <div>
                <div className="mb-1 flex justify-between text-sm"><span>Mandatory</span><span className="font-medium tabular-nums">{c.mandatory_percent_complete}%</span></div>
                <Progress value={c.mandatory_percent_complete} tone="navy" />
              </div>
              <ul className="space-y-1 text-xs text-muted">
                {RESPONSE_STATUSES.map((s) => (
                  <li key={s.value} className="flex justify-between"><span>{s.label}</span><span className="tabular-nums">{c.by_status[s.value] ?? 0}</span></li>
                ))}
              </ul>
              <p className="text-[11px] text-muted">Completion counts requirements marked Compliant, Partially Compliant or Non-Compliant.</p>
            </div>
          )}
        </Card>
      </div>

      <Card title="Activity">
        {activity.data?.length ? (
          <ul className="divide-y divide-line">
            {activity.data.map((a) => (
              <li key={a.id} className="flex items-baseline justify-between gap-4 py-2 text-sm">
                <span>{a.summary}</span>
                <span className="shrink-0 text-xs text-muted">{a.actor_name ?? "System"} · {timeAgo(a.created_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">{activity.isLoading ? "Loading…" : "No activity yet."}</p>
        )}
      </Card>
    </div>
  );
}
