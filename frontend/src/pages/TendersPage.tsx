import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowDownUp, Archive, ChevronLeft, ChevronRight, FilePlus2, FileStack, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { PriorityBadge, StatusBadge } from "@/components/badges";
import { TenderFormDialog } from "@/components/TenderForm";
import { Button, Card, EmptyState, ErrorState, Input, LoadingBlock, PageHeader, Progress, Select } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { PRIORITIES, TENDER_STATUSES, TENDER_TYPES, typeLabel } from "@/lib/labels";
import type { Page, Tender } from "@/lib/types";
import { cn, formatDate, formatMoney, relativeDeadline } from "@/lib/utils";

const SORTS = [
  { value: "updated_at", label: "Last updated" },
  { value: "submission_deadline", label: "Deadline" },
  { value: "created_at", label: "Created" },
  { value: "title", label: "Title" },
  { value: "priority", label: "Priority" },
  { value: "estimated_value", label: "Value" },
];

export default function TendersPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState(params.get("q") ?? "");

  const status = params.get("status") ?? "";
  const priority = params.get("priority") ?? "";
  const type = params.get("type") ?? "";
  const sort = params.get("sort") ?? "updated_at";
  const order = params.get("order") ?? (sort === "submission_deadline" || sort === "title" ? "asc" : "desc");
  const archived = params.get("archived") === "1";
  const page = Number(params.get("page") ?? "1");

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in patch)) next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => {
    const id = setTimeout(() => {
      if ((params.get("q") ?? "") !== search) update({ q: search });
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const query = useQuery({
    queryKey: ["tenders", { q: params.get("q"), status, priority, type, sort, order, archived, page }],
    queryFn: () =>
      api<Page<Tender>>(
        `/api/v1/tenders${qs({ q: params.get("q"), status: status || undefined, priority, tender_type: type, sort, order, archived, page, page_size: 15 })}`,
      ),
    placeholderData: keepPreviousData,
  });
  const data = query.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const filtered = !!(params.get("q") || status || priority || type);

  return (
    <>
      <PageHeader
        title={archived ? "Archived tenders" : "Tenders"}
        description="Search, filter and manage every tender project in your organisation."
        actions={
          <>
            <Button variant="outline" onClick={() => update({ archived: archived ? null : "1" })}>
              <Archive className="h-4 w-4" /> {archived ? "Show active" : "Archived"}
            </Button>
            <Button onClick={() => setCreating(true)}>
              <FilePlus2 className="h-4 w-4" /> New tender
            </Button>
          </>
        }
      />
      <TenderFormDialog open={creating} onOpenChange={setCreating} onSaved={(t) => navigate(`/tenders/${t.id}`)} />

      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-[1.6fr_1fr_1fr_1fr_1.2fr]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input aria-label="Search tenders" placeholder="Search title, buyer or reference" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter by status" value={status} onChange={(e) => update({ status: e.target.value })}>
            <option value="">All statuses</option>
            {TENDER_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
          <Select aria-label="Filter by priority" value={priority} onChange={(e) => update({ priority: e.target.value })}>
            <option value="">All priorities</option>
            {PRIORITIES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
          <Select aria-label="Filter by type" value={type} onChange={(e) => update({ type: e.target.value })}>
            <option value="">All types</option>
            {TENDER_TYPES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
          <div className="flex gap-2">
            <Select aria-label="Sort by" value={sort} onChange={(e) => update({ sort: e.target.value, order: null })}>
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </Select>
            <Button variant="outline" size="icon" className="h-[38px] w-[38px]" aria-label={`Sort ${order === "asc" ? "descending" : "ascending"}`} onClick={() => update({ order: order === "asc" ? "desc" : "asc" })}>
              <ArrowDownUp className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </Card>

      {query.isLoading ? (
        <LoadingBlock rows={6} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon={<FileStack className="h-5 w-5" />}
          title={filtered ? "No tenders match your filters" : archived ? "No archived tenders" : "No tenders yet"}
          description={filtered ? "Try a different search or clear the filters." : "Create a tender project to start tracking requirements, documents and decisions."}
          action={
            filtered ? (
              <Button variant="outline" onClick={() => { setSearch(""); setParams(new URLSearchParams(), { replace: true }); }}>Clear filters</Button>
            ) : (
              !archived && <Button onClick={() => setCreating(true)}><FilePlus2 className="h-4 w-4" /> New tender</Button>
            )
          }
        />
      ) : (
        <div className={cn("card overflow-hidden", query.isFetching && "opacity-80")}>
          <div className="overflow-x-auto">
            <table className="table-base min-w-[860px]">
              <thead>
                <tr>
                  <th>Tender</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Deadline</th>
                  <th>Value</th>
                  <th className="w-40">Compliance</th>
                </tr>
              </thead>
              <tbody>
                {data!.items.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-50/60">
                    <td className="max-w-[340px]">
                      <Link to={`/tenders/${t.id}`} className="font-medium text-ink hover:underline">{t.title}</Link>
                      <div className="mt-0.5 truncate text-xs text-muted">
                        {[t.buyer, t.reference, typeLabel(t.tender_type)].filter(Boolean).join(" · ")}
                      </div>
                    </td>
                    <td><StatusBadge status={t.status} /></td>
                    <td><PriorityBadge priority={t.priority} /></td>
                    <td className="whitespace-nowrap">
                      <div>{formatDate(t.submission_deadline)}</div>
                      {t.submission_deadline && !["submitted", "won", "lost", "withdrawn"].includes(t.status) && (
                        <div className="text-xs text-muted">{relativeDeadline(t.submission_deadline)}</div>
                      )}
                    </td>
                    <td className="whitespace-nowrap tabular-nums">{formatMoney(t.estimated_value, t.currency)}</td>
                    <td>
                      {t.requirement_count ? (
                        <div>
                          <Progress value={t.compliance_percent ?? 0} />
                          <div className="mt-1 text-xs text-muted">{t.compliance_percent ?? 0}% of {t.requirement_count}</div>
                        </div>
                      ) : (
                        <span className="text-xs text-muted">No requirements</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-muted">
            <span>{data!.total} tender{data!.total === 1 ? "" : "s"}</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })} aria-label="Previous page">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span>Page {page} of {pages}</span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })} aria-label="Next page">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
