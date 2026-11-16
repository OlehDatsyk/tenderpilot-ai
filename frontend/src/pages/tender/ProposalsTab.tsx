import { useQuery } from "@tanstack/react-query";
import { FilePenLine, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Dialog } from "@/components/dialog";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, LoadingBlock, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useAIStatus, useApiMutation } from "@/lib/hooks";
import type { Proposal, ProposalDetail } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export function ProposalsTab({ tenderId }: { tenderId: string }) {
  const navigate = useNavigate();
  const ai = useAIStatus();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("Proposal response");
  const [useAI, setUseAI] = useState(true);
  const q = useQuery({ queryKey: ["proposals", tenderId], queryFn: () => api<Proposal[]>(`/api/v1/tenders/${tenderId}/proposals`) });
  const create = useApiMutation(
    () => api<ProposalDetail>(`/api/v1/tenders/${tenderId}/proposals`, { method: "POST", body: { title, use_ai_outline: useAI && !!ai.data?.configured } }),
    { success: "Proposal created", invalidate: [["proposals", tenderId]], onSuccess: (p) => navigate(`/tenders/${tenderId}/proposals/${p.id}`) },
  );

  return (
    <div className="space-y-5">
      <Notice tone="teal">
        Generated drafts only use facts from your <Link to="/company" className="underline">company profile</Link> and the compliance evidence you record. Missing facts are marked <code className="rounded bg-white/60 px-1">[COMPANY INFORMATION REQUIRED]</code>.
      </Notice>
      <Card title="Proposal drafts" actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New proposal</Button>}>
        {q.isLoading ? (
          <LoadingBlock />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data!.length === 0 ? (
          <EmptyState icon={<FilePenLine className="h-5 w-5" />} title="No proposal drafts" description="Create a draft to start writing your response section by section." />
        ) : (
          <ul className="divide-y divide-line">
            {q.data!.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <Link to={`/tenders/${tenderId}/proposals/${p.id}`} className="font-medium hover:underline">{p.title}</Link>
                  <div className="text-xs text-muted">{p.section_count} sections · updated {formatDateTime(p.updated_at)}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={p.status === "final" ? "green" : p.status === "in_review" ? "amber" : "slate"}>{p.status.replace("_", " ")}</Badge>
                  <Link to={`/tenders/${tenderId}/proposals/${p.id}`}><Button size="sm" variant="outline">Open editor</Button></Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="New proposal draft"
        footer={
          <>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={create.isPending} disabled={!title.trim()} onClick={() => create.mutate(undefined)}>Create</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Title" htmlFor="p-title">
            <Input id="p-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 h-4 w-4" checked={useAI && !!ai.data?.configured} disabled={!ai.data?.configured} onChange={(e) => setUseAI(e.target.checked)} />
            <span>
              Generate an outline from the requirements and evaluation criteria
              {ai.data?.is_demo && <span className="block text-xs text-amber-700">Demo mode: a fixed template outline will be used.</span>}
              {!ai.data?.configured && <span className="block text-xs text-muted">Requires an AI provider. You can add sections manually.</span>}
            </span>
          </label>
        </div>
      </Dialog>
    </div>
  );
}
