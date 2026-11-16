import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StatusBadge } from "@/components/badges";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Progress, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { decisionLabel, statusLabel } from "@/lib/labels";
import type { Analytics, Decision } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";

const COLORS = ["#0f1f3d", "#0d9488", "#3b82f6", "#d97706", "#7c3aed", "#64748b", "#16a34a", "#dc2626", "#94a3b8"];
const DECISION_COLORS: Record<Decision, string> = { bid: "#16a34a", no_bid: "#dc2626", needs_more_info: "#d97706" };

export default function AnalyticsPage() {
  const q = useQuery({ queryKey: ["analytics"], queryFn: () => api<Analytics>("/api/v1/analytics") });
  const header = <PageHeader title="Analytics" description="Calculated from your organisation's stored records — no sample data." />;
  if (q.isLoading) return <>{header}<LoadingBlock rows={8} /></>;
  if (q.isError) return <>{header}<ErrorState error={q.error} onRetry={() => q.refetch()} /></>;
  const a = q.data!;
  const totalTenders = a.pipeline.reduce((s, p) => s + p.count, 0);
  if (totalTenders === 0)
    return (
      <>
        {header}
        <EmptyState icon={<BarChart3 className="h-5 w-5" />} title="No data yet" description="Analytics appear once you create tender projects." />
      </>
    );
  const pipeline = a.pipeline.map((p) => ({ name: statusLabel(p.status), count: p.count }));
  const recs = (Object.entries(a.decisions.recommendations) as [Decision, number][]).map(([k, v]) => ({ name: decisionLabel(k), key: k, value: v }));
  const finals = (Object.entries(a.decisions.final) as [Decision, number][]).map(([k, v]) => ({ name: decisionLabel(k), key: k, value: v }));
  const monthly = a.monthly.map((m) => ({ ...m, label: new Date(`${m.month}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "2-digit" }) }));

  return (
    <>
      {header}
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Tenders (not archived)" value={totalTenders} />
          <Stat label="Win rate" value={a.win_loss.win_rate === null ? "—" : `${a.win_loss.win_rate}%`} hint={`${a.win_loss.won} won · ${a.win_loss.lost} lost · ${a.win_loss.withdrawn} withdrawn`} />
          <Stat label="Compliance completion" value={a.compliance.percent_complete === null ? "—" : `${a.compliance.percent_complete}%`} hint={`${a.compliance.addressed} of ${a.compliance.total_requirements} requirements`} />
          <Stat label="Assessed tenders" value={a.decisions.assessed_tenders} hint={`${a.decisions.overrides} recommendation override(s)`} />
        </div>

        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Tender pipeline by status">
            <div className="h-72">
              <ResponsiveContainer>
                <BarChart data={pipeline} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e3e7ef" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-25} textAnchor="end" height={60} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" name="Tenders" fill="#0f1f3d" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Monthly activity" description="Tenders created, won and lost (by last update), and AI runs per month.">
            <div className="h-72">
              <ResponsiveContainer>
                <LineChart data={monthly} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e3e7ef" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="created" name="Created" stroke="#0f1f3d" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="won" name="Won" stroke="#16a34a" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="lost" name="Lost" stroke="#dc2626" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="ai_runs" name="AI runs" stroke="#0d9488" strokeDasharray="4 3" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        <div className="grid gap-6 xl:grid-cols-3">
          <Card title="Bid / no-bid decisions" description="Latest assessment per tender">
            {recs.length === 0 ? (
              <p className="text-sm text-muted">No assessments yet.</p>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {[{ title: "Recommended", data: recs }, { title: "Final", data: finals }].map(({ title, data }) => (
                  <div key={title}>
                    <p className="text-center text-xs font-medium text-muted">{title}</p>
                    <div className="h-40">
                      {data.length ? (
                        <ResponsiveContainer>
                          <PieChart>
                            <Pie data={data} dataKey="value" nameKey="name" innerRadius={30} outerRadius={55} paddingAngle={2}>
                              {data.map((d) => <Cell key={d.key} fill={DECISION_COLORS[d.key]} />)}
                            </Pie>
                            <Tooltip />
                          </PieChart>
                        </ResponsiveContainer>
                      ) : (
                        <p className="pt-12 text-center text-xs text-muted">None recorded</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="Compliance completion by tender" className="xl:col-span-2" description="Active tenders, least complete first">
            {a.compliance.by_tender.length === 0 ? (
              <p className="text-sm text-muted">No active tenders with requirements.</p>
            ) : (
              <ul className="space-y-3">
                {a.compliance.by_tender.map((t) => (
                  <li key={t.tender_id}>
                    <div className="mb-1 flex justify-between gap-3 text-sm">
                      <Link to={`/tenders/${t.tender_id}?tab=compliance`} className="truncate hover:underline">{t.title}</Link>
                      <span className="shrink-0 tabular-nums text-muted">{t.percent_complete ?? 0}% of {t.requirements}</span>
                    </div>
                    <Progress value={t.percent_complete ?? 0} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Upcoming deadlines">
            {a.upcoming_deadlines.length === 0 ? (
              <p className="text-sm text-muted">No upcoming deadlines.</p>
            ) : (
              <div className="-mx-5 -my-5 overflow-x-auto">
                <table className="table-base min-w-[480px]">
                  <thead><tr><th>Tender</th><th>Status</th><th>Deadline</th><th>Days left</th></tr></thead>
                  <tbody>
                    {a.upcoming_deadlines.map((d) => (
                      <tr key={d.id}>
                        <td><Link to={`/tenders/${d.id}`} className="hover:underline">{d.title}</Link></td>
                        <td><StatusBadge status={d.status} /></td>
                        <td className="whitespace-nowrap">{formatDate(d.submission_deadline)}</td>
                        <td className={d.days_left <= 7 ? "font-medium text-red-600" : ""}>{d.days_left}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card title="Pipeline value by status" description="Sum of estimated values entered on tenders">
            {a.pipeline_value.length === 0 ? (
              <p className="text-sm text-muted">No estimated values recorded.</p>
            ) : (
              <ul className="divide-y divide-line">
                {a.pipeline_value.map((v, i) => (
                  <li key={i} className="flex items-center justify-between py-2 text-sm">
                    <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} /><StatusBadge status={v.status} /></span>
                    <span className="font-medium tabular-nums">{formatMoney(v.value, v.currency)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
