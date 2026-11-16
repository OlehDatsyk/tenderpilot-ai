import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, CheckCircle2, ClipboardList, FilePlus2, FileStack, Hourglass, Trophy } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PriorityBadge, StatusBadge } from "@/components/badges";
import { TenderFormDialog } from "@/components/TenderForm";
import { Button, Card, EmptyState, ErrorState, LoadingBlock, Notice, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAIStatus } from "@/lib/hooks";
import { statusLabel } from "@/lib/labels";
import type { Dashboard } from "@/lib/types";
import { cn, formatDate, relativeDeadline, timeAgo } from "@/lib/utils";

export function AIStatusNotice() {
  const { data } = useAIStatus();
  if (!data) return null;
  if (data.is_demo)
    return (
      <Notice tone="amber" className="mb-6">
        <strong>Demo mode is active.</strong> Analysis, bid assessments, drafts and assistant answers are produced by a simple rule-based heuristic — no AI model is used. Configure a provider in{" "}
        <Link className="underline" to="/settings?tab=ai">Settings → AI provider</Link>.
      </Notice>
    );
  if (!data.configured)
    return (
      <Notice tone="blue" className="mb-6">
        <strong>AI is not configured.</strong> Tender management, documents, compliance tracking, tasks and exports work normally. AI analysis and drafting require a provider —{" "}
        <Link className="underline" to="/settings?tab=ai">configure one in Settings</Link>.
      </Notice>
    );
  return null;
}

export default function DashboardPage() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/api/v1/dashboard") });

  const header = (
    <PageHeader
      title={`Welcome back${me ? `, ${me.full_name.split(" ")[0]}` : ""}`}
      description="Your tender pipeline at a glance. All figures are calculated from your organisation's records."
      actions={
        <Button onClick={() => setCreating(true)}>
          <FilePlus2 className="h-4 w-4" /> New tender
        </Button>
      }
    />
  );
  const dialog = <TenderFormDialog open={creating} onOpenChange={setCreating} onSaved={(t) => navigate(`/tenders/${t.id}`)} />;

  if (q.isLoading)
    return (
      <>
        {header}
        <LoadingBlock rows={6} />
      </>
    );
  if (q.isError)
    return (
      <>
        {header}
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      </>
    );
  const d = q.data!;
  const s = d.stats;
  const maxPipeline = Math.max(1, ...d.pipeline.map((p) => p.count));

  return (
    <>
      {header}
      {dialog}
      <AIStatusNotice />
      {s.total_tenders === 0 ? (
        <EmptyState
          icon={<FileStack className="h-5 w-5" />}
          title="No tender projects yet"
          description="Create your first tender project, upload the tender documents and let TenderPilot extract the requirements for your team to review."
          action={
            <Button onClick={() => setCreating(true)}>
              <FilePlus2 className="h-4 w-4" /> Create a tender
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Total tenders" value={s.total_tenders} icon={<FileStack className="h-4 w-4" />} />
            <Stat label="Active" value={s.active_tenders} icon={<ClipboardList className="h-4 w-4" />} hint="Review → internal review" />
            <Stat label="Awaiting review" value={s.awaiting_review} icon={<Hourglass className="h-4 w-4" />} />
            <Stat label="Deadlines ≤ 30 days" value={s.upcoming_deadlines} icon={<CalendarClock className="h-4 w-4" />} />
            <Stat label="Completed proposals" value={s.completed_proposals} icon={<CheckCircle2 className="h-4 w-4" />} hint="Submitted, won or lost" />
            <Stat label="Win rate" value={s.win_rate === null ? "—" : `${s.win_rate}%`} icon={<Trophy className="h-4 w-4" />} hint={`${s.won} won · ${s.lost} lost`} />
          </div>

          {d.alerts.length > 0 && (
            <Card title="Important alerts">
              <ul className="space-y-2">
                {d.alerts.map((a, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm">
                    <AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", a.severity === "high" ? "text-red-600" : a.severity === "medium" ? "text-amber-600" : "text-slate-400")} />
                    {a.tender_id ? (
                      <Link className="hover:underline" to={`/tenders/${a.tender_id}`}>
                        {a.message}
                      </Link>
                    ) : (
                      <span>{a.message}</span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="grid gap-6 xl:grid-cols-3">
            <Card title="Tender pipeline" className="xl:col-span-2" actions={<Link to="/analytics" className="text-xs font-medium text-accent-700 hover:underline">Analytics →</Link>}>
              <div className="space-y-2.5">
                {d.pipeline.map((p) => (
                  <Link key={p.status} to={`/tenders?status=${p.status}`} className="group flex items-center gap-3 text-sm">
                    <span className="w-32 shrink-0 text-muted group-hover:text-ink">{statusLabel(p.status)}</span>
                    <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <span className="block h-full rounded-full bg-navy-700" style={{ width: `${(p.count / maxPipeline) * 100}%` }} />
                    </span>
                    <span className="w-8 text-right tabular-nums">{p.count}</span>
                  </Link>
                ))}
              </div>
            </Card>
            <Card title="Upcoming deadlines">
              {d.upcoming.length === 0 ? (
                <p className="text-sm text-muted">No upcoming deadlines on open tenders.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {d.upcoming.map((t) => (
                    <li key={t.id} className="py-2.5 first:pt-0 last:pb-0">
                      <Link to={`/tenders/${t.id}`} className="block text-sm font-medium hover:underline">
                        {t.title}
                      </Link>
                      <div className="mt-0.5 flex items-center justify-between text-xs text-muted">
                        <span>{formatDate(t.submission_deadline)}</span>
                        <span className={cn((new Date(t.submission_deadline).getTime() - Date.now()) / 86400000 <= 7 && "font-medium text-red-600")}>{relativeDeadline(t.submission_deadline)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-3">
            <Card title="Recent projects" className="xl:col-span-2" actions={<Link to="/tenders" className="text-xs font-medium text-accent-700 hover:underline">All tenders →</Link>}>
              <div className="-mx-5 -my-5 overflow-x-auto">
                <table className="table-base min-w-[560px]">
                  <thead>
                    <tr>
                      <th>Tender</th>
                      <th>Status</th>
                      <th>Priority</th>
                      <th>Deadline</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.recent_tenders.map((t) => (
                      <tr key={t.id} className="hover:bg-slate-50/60">
                        <td>
                          <Link to={`/tenders/${t.id}`} className="font-medium hover:underline">
                            {t.title}
                          </Link>
                          <div className="text-xs text-muted">{t.buyer || "—"}</div>
                        </td>
                        <td><StatusBadge status={t.status} /></td>
                        <td><PriorityBadge priority={t.priority} /></td>
                        <td className="whitespace-nowrap text-muted">{formatDate(t.submission_deadline)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card title="Recent activity">
              {d.recent_activity.length === 0 ? (
                <p className="text-sm text-muted">No activity yet.</p>
              ) : (
                <ul className="space-y-3">
                  {d.recent_activity.map((a) => (
                    <li key={a.id} className="text-sm">
                      <div className="text-ink">{a.summary}</div>
                      <div className="mt-0.5 text-xs text-muted">
                        {a.actor_name ?? "System"} · {timeAgo(a.created_at)}
                        {a.tender_title && a.tender_id && (
                          <>
                            {" · "}
                            <Link to={`/tenders/${a.tender_id}`} className="hover:underline">{a.tender_title}</Link>
                          </>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
