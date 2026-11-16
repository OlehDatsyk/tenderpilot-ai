import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ChevronRight, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PriorityBadge, StatusBadge } from "@/components/badges";
import { ConfirmButton } from "@/components/dialog";
import { TenderFormDialog } from "@/components/TenderForm";
import { Button, ErrorState, LoadingBlock } from "@/components/ui";
import { api } from "@/lib/api";
import { useApiMutation } from "@/lib/hooks";
import type { TenderDetail } from "@/lib/types";
import { typeLabel } from "@/lib/labels";
import { AnalysisTab } from "./tender/AnalysisTab";
import { AssistantTab } from "./tender/AssistantTab";
import { BidTab } from "./tender/BidTab";
import { ComplianceTab } from "./tender/ComplianceTab";
import { DocumentsTab } from "./tender/DocumentsTab";
import { ExportsPanel } from "./tender/ExportsPanel";
import { OverviewTab } from "./tender/OverviewTab";
import { ProposalsTab } from "./tender/ProposalsTab";
import { TaskList } from "./TasksPage";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "documents", label: "Documents" },
  { id: "analysis", label: "AI Analysis" },
  { id: "compliance", label: "Compliance" },
  { id: "bid", label: "Bid / No-Bid" },
  { id: "proposals", label: "Proposals" },
  { id: "assistant", label: "Assistant" },
  { id: "tasks", label: "Tasks" },
  { id: "exports", label: "Exports" },
];

export default function TenderDetailPage() {
  const { tenderId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const tab = params.get("tab") ?? "overview";

  const q = useQuery({ queryKey: ["tender", tenderId], queryFn: () => api<TenderDetail>(`/api/v1/tenders/${tenderId}`) });
  const archive = useApiMutation((archived: boolean) => api(`/api/v1/tenders/${tenderId}`, { method: "PATCH", body: { is_archived: archived } }), {
    success: (_) => "Tender updated",
    invalidate: [["tender", tenderId], ["tenders"], ["dashboard"]],
  });
  const remove = useApiMutation(() => api(`/api/v1/tenders/${tenderId}`, { method: "DELETE" }), {
    success: "Tender deleted",
    invalidate: [["tenders"], ["dashboard"]],
    onSuccess: () => navigate("/tenders"),
  });

  if (q.isLoading) return <LoadingBlock rows={8} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const t = q.data!;

  return (
    <>
      <nav className="mb-3 flex items-center gap-1 text-xs text-muted" aria-label="Breadcrumb">
        <Link to="/tenders" className="hover:text-ink">Tenders</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="truncate text-ink">{t.title}</span>
      </nav>
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold sm:text-[22px]">{t.title}</h1>
            {t.is_archived && <span className="rounded bg-slate-200 px-2 py-0.5 text-xs text-slate-700">Archived</span>}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
            <StatusBadge status={t.status} />
            <PriorityBadge priority={t.priority} />
            <span>{typeLabel(t.tender_type)}</span>
            {t.buyer && <span>· {t.buyer}</span>}
            {t.reference && <span>· Ref {t.reference}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" /> Edit
          </Button>
          <Button variant="outline" loading={archive.isPending} onClick={() => archive.mutate(!t.is_archived)}>
            {t.is_archived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
            {t.is_archived ? "Restore" : "Archive"}
          </Button>
          <ConfirmButton
            title="Delete this tender?"
            description={`"${t.title}" and all of its documents, requirements, assessments, proposals and tasks will be permanently deleted.`}
            onConfirm={() => remove.mutateAsync(undefined)}
            trigger={(open) => (
              <Button variant="outline" className="text-red-600 hover:bg-red-50" onClick={open}>
                <Trash2 className="h-4 w-4" /> Delete
              </Button>
            )}
          />
        </div>
      </div>
      <TenderFormDialog open={editing} onOpenChange={setEditing} tender={t} />

      <Tabs.Root value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <Tabs.List className="mb-5 flex gap-1 overflow-x-auto border-b border-line" aria-label="Tender sections">
          {TABS.map((x) => (
            <Tabs.Trigger
              key={x.id}
              value={x.id}
              className="-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2.5 text-sm font-medium text-muted transition-colors hover:text-ink data-[state=active]:border-accent-600 data-[state=active]:text-ink"
            >
              {x.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="overview"><OverviewTab tender={t} onTab={(id) => setParams({ tab: id }, { replace: true })} /></Tabs.Content>
        <Tabs.Content value="documents"><DocumentsTab tenderId={t.id} /></Tabs.Content>
        <Tabs.Content value="analysis"><AnalysisTab tenderId={t.id} /></Tabs.Content>
        <Tabs.Content value="compliance"><ComplianceTab tenderId={t.id} /></Tabs.Content>
        <Tabs.Content value="bid"><BidTab tender={t} /></Tabs.Content>
        <Tabs.Content value="proposals"><ProposalsTab tenderId={t.id} /></Tabs.Content>
        <Tabs.Content value="assistant"><AssistantTab tenderId={t.id} /></Tabs.Content>
        <Tabs.Content value="tasks"><TaskList tenderId={t.id} /></Tabs.Content>
        <Tabs.Content value="exports"><ExportsPanel tenderId={t.id} tenderTitle={t.title} /></Tabs.Content>
      </Tabs.Root>
    </>
  );
}
