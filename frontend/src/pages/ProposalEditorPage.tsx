import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronRight, FileDown, ListPlus, Plus, Save, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { DemoBadge } from "@/components/badges";
import { ConfirmButton, Dialog } from "@/components/dialog";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, LoadingBlock, Notice, Select, Textarea } from "@/components/ui";
import { api, downloadFile } from "@/lib/api";
import { useAIStatus, useApiMutation } from "@/lib/hooks";
import type { Coverage, ProposalDetail, ProposalSection } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

const PLACEHOLDER = "[COMPANY INFORMATION REQUIRED]";

function SectionEditor({ proposalId, section, onDeleted }: { proposalId: string; section: ProposalSection; onDeleted: () => void }) {
  const qc = useQueryClient();
  const ai = useAIStatus();
  const [title, setTitle] = useState(section.title);
  const [content, setContent] = useState(section.content);
  const [instructions, setInstructions] = useState("");
  const [unanswered, setUnanswered] = useState<string[]>([]);
  useEffect(() => {
    setTitle(section.title);
    setContent(section.content);
    setUnanswered([]);
  }, [section.id, section.title, section.content]);
  const dirty = title !== section.title || content !== section.content;
  const invalidate = [["proposal", proposalId], ["coverage", proposalId]];

  const save = useApiMutation(() => api(`/api/v1/proposals/${proposalId}/sections/${section.id}`, { method: "PATCH", body: { title, content } }), {
    success: "Section saved",
    invalidate,
  });
  const generate = useApiMutation(
    (mode: "draft" | "improve") =>
      api<{ section: ProposalSection; unanswered_points: string[] }>(`/api/v1/proposals/${proposalId}/sections/${section.id}/generate`, {
        method: "POST",
        body: { mode, instructions },
      }),
    {
      success: (r) => (r.section.is_demo ? "Demo template inserted" : "Draft generated — review before use"),
      invalidate,
      onSuccess: (r) => setUnanswered(r.unanswered_points),
    },
  );
  const remove = useApiMutation(() => api(`/api/v1/proposals/${proposalId}/sections/${section.id}`, { method: "DELETE" }), {
    success: "Section deleted",
    invalidate,
    onSuccess: onDeleted,
  });
  const placeholders = (content.match(/\[COMPANY INFORMATION REQUIRED\]/g) ?? []).length;

  const runGenerate = (mode: "draft" | "improve") => {
    if (dirty && !window.confirm("You have unsaved changes. Generating will replace the section text. Continue?")) return;
    if (mode === "draft" && section.content.trim() && !window.confirm("Replace the existing text with a new draft?")) return;
    generate.mutate(mode);
    qc.invalidateQueries({ queryKey: ["proposal", proposalId] });
  };

  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          Section editor
          {section.ai_generated && (section.is_demo ? <DemoBadge /> : <Badge tone="violet"><Sparkles className="h-3 w-3" /> AI-generated draft</Badge>)}
        </span>
      }
      description={`Last saved ${timeAgo(section.updated_at)}`}
      actions={
        <>
          <ConfirmButton title="Delete section?" description={`"${section.title}" will be removed from this proposal.`} onConfirm={() => remove.mutateAsync(undefined)} trigger={(open) => (
            <Button variant="ghost" size="sm" className="text-red-600 hover:bg-red-50" onClick={open}><Trash2 className="h-4 w-4" /> Delete</Button>
          )} />
          <Button size="sm" onClick={() => save.mutate(undefined)} loading={save.isPending} disabled={!dirty || !title.trim()}>
            <Save className="h-4 w-4" /> {dirty ? "Save" : "Saved"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Section title" htmlFor="s-title">
          <Input id="s-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        {section.guidance && (
          <div className="rounded-lg bg-slate-50 p-3 text-xs text-muted">
            <span className="font-semibold text-ink">Guidance: </span>
            <span className="whitespace-pre-wrap">{section.guidance}</span>
          </div>
        )}
        <Field label="Content" htmlFor="s-content" hint="Plain text / markdown. Replace every placeholder with verified information before submission.">
          <Textarea id="s-content" rows={16} className="font-[450]" value={content} onChange={(e) => setContent(e.target.value)} placeholder="Write the section, or generate a draft." />
        </Field>
        {placeholders > 0 && (
          <Notice tone="amber" icon={<AlertTriangle className="h-4 w-4" />}>
            {placeholders} × <code>{PLACEHOLDER}</code> — company information is needed before this section is complete.
          </Notice>
        )}
        {unanswered.length > 0 && (
          <Notice tone="blue">
            <strong>Points not addressed in the draft:</strong>
            <ul className="mt-1 list-disc pl-5">{unanswered.map((u, i) => <li key={i}>{u}</li>)}</ul>
          </Notice>
        )}
        <div className="rounded-lg border border-line p-3">
          <Field label="Writing instructions (optional)" htmlFor="s-instr" hint="e.g. 'focus on social value', 'max 300 words'. Instructions are preferences, not facts.">
            <Input id="s-instr" value={instructions} onChange={(e) => setInstructions(e.target.value)} disabled={!ai.data?.configured} />
          </Field>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" loading={generate.isPending && generate.variables === "draft"} disabled={!ai.data?.configured || generate.isPending} onClick={() => runGenerate("draft")}>
              <Sparkles className="h-4 w-4" /> Draft with AI
            </Button>
            <Button variant="outline" size="sm" loading={generate.isPending && generate.variables === "improve"} disabled={!ai.data?.configured || generate.isPending || !section.content.trim() || ai.data?.is_demo} onClick={() => runGenerate("improve")} title={ai.data?.is_demo ? "Not available in demo mode" : undefined}>
              <Wand2 className="h-4 w-4" /> Improve clarity & tone
            </Button>
            {!ai.data?.configured && <span className="self-center text-xs text-muted">AI is not configured.</span>}
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function ProposalEditorPage() {
  const { tenderId = "", proposalId = "" } = useParams();
  const navigate = useNavigate();
  const ai = useAIStatus();
  const [selected, setSelected] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const q = useQuery({ queryKey: ["proposal", proposalId], queryFn: () => api<ProposalDetail>(`/api/v1/proposals/${proposalId}`) });
  const coverage = useQuery({ queryKey: ["coverage", proposalId], queryFn: () => api<Coverage>(`/api/v1/proposals/${proposalId}/coverage`) });
  const p = q.data;
  const current = useMemo(() => p?.sections.find((s) => s.id === selected) ?? p?.sections[0], [p, selected]);

  const updateMeta = useApiMutation((body: Record<string, string>) => api(`/api/v1/proposals/${proposalId}`, { method: "PATCH", body }), {
    success: "Proposal updated",
    invalidate: [["proposal", proposalId], ["proposals", tenderId]],
  });
  const addSection = useApiMutation(
    (body: { title: string; guidance?: string; requirement_id?: string }) => api<ProposalSection>(`/api/v1/proposals/${proposalId}/sections`, { method: "POST", body }),
    {
      success: "Section added",
      invalidate: [["proposal", proposalId], ["coverage", proposalId]],
      onSuccess: (s) => {
        setSelected(s.id);
        setAdding(false);
        setNewTitle("");
      },
    },
  );
  const outline = useApiMutation(() => api(`/api/v1/proposals/${proposalId}/outline`, { method: "POST" }), {
    success: "Outline sections added",
    invalidate: [["proposal", proposalId], ["coverage", proposalId]],
  });
  const remove = useApiMutation(() => api(`/api/v1/proposals/${proposalId}`, { method: "DELETE" }), {
    success: "Proposal deleted",
    invalidate: [["proposals", tenderId]],
    onSuccess: () => navigate(`/tenders/${tenderId}?tab=proposals`),
  });

  if (q.isLoading) return <LoadingBlock rows={8} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  return (
    <>
      <nav className="mb-3 flex items-center gap-1 text-xs text-muted" aria-label="Breadcrumb">
        <Link to="/tenders" className="hover:text-ink">Tenders</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to={`/tenders/${tenderId}?tab=proposals`} className="hover:text-ink">Tender</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-ink">Proposal</span>
      </nav>
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Input
            aria-label="Proposal title"
            key={p!.title}
            defaultValue={p!.title}
            className="max-w-lg border-transparent bg-transparent px-1 text-xl font-semibold shadow-none hover:border-line focus:bg-white"
            onBlur={(e) => e.target.value.trim() && e.target.value !== p!.title && updateMeta.mutate({ title: e.target.value.trim() })}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select aria-label="Proposal status" className="w-36" value={p!.status} onChange={(e) => updateMeta.mutate({ status: e.target.value })}>
            <option value="draft">Draft</option>
            <option value="in_review">In review</option>
            <option value="final">Final</option>
          </Select>
          <Button variant="outline" onClick={() => downloadFile(`/api/v1/tenders/${tenderId}/exports/proposal?format=docx&proposal_id=${proposalId}`, "proposal.docx").catch((e) => toast.error(e.message))}>
            <FileDown className="h-4 w-4" /> DOCX
          </Button>
          <ConfirmButton title="Delete proposal?" description="All sections of this draft will be deleted." onConfirm={() => remove.mutateAsync(undefined)} trigger={(open) => (
            <Button variant="outline" className="text-red-600 hover:bg-red-50" onClick={open} aria-label="Delete proposal"><Trash2 className="h-4 w-4" /></Button>
          )} />
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[260px_1fr_300px]">
        <Card title="Sections" className="h-fit" actions={<Button size="icon" variant="ghost" aria-label="Add section" onClick={() => setAdding(true)}><Plus className="h-4 w-4" /></Button>}>
          {p!.sections.length === 0 ? (
            <div className="space-y-3 text-sm text-muted">
              <p>No sections yet.</p>
              <Button size="sm" variant="secondary" className="w-full justify-center" disabled={!ai.data?.configured} loading={outline.isPending} onClick={() => outline.mutate(undefined)}>
                <Sparkles className="h-4 w-4" /> Generate outline
              </Button>
              <Button size="sm" variant="outline" className="w-full justify-center" onClick={() => setAdding(true)}>Add section manually</Button>
            </div>
          ) : (
            <ol className="-mx-2 space-y-0.5">
              {p!.sections.map((s, i) => (
                <li key={s.id}>
                  <button
                    onClick={() => setSelected(s.id)}
                    className={cn("flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-[13px]", current?.id === s.id ? "bg-accent-50 text-accent-700" : "hover:bg-slate-50")}
                  >
                    <span className="w-5 shrink-0 text-right text-muted tabular-nums">{i + 1}.</span>
                    <span className="flex-1">{s.title}</span>
                    {(!s.content.trim() || s.content.includes(PLACEHOLDER)) && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-amber-400" title="Incomplete" />}
                  </button>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <div>
          {current ? (
            <SectionEditor key={current.id} proposalId={proposalId} section={current} onDeleted={() => setSelected(null)} />
          ) : (
            <EmptyState title="Select or add a section" description="Each section is saved separately and stays editable." />
          )}
        </div>

        <Card title="Requirement coverage" className="h-fit" description="Requirements without a completed, linked section.">
          {coverage.data ? (
            <div className="space-y-3">
              <div className="text-sm"><span className="text-2xl font-semibold">{coverage.data.covered}</span> <span className="text-muted">/ {coverage.data.total_requirements} answered</span></div>
              {coverage.data.unanswered.length === 0 ? (
                <p className="text-sm text-muted">{coverage.data.total_requirements ? "All requirements are covered." : "No requirements recorded for this tender."}</p>
              ) : (
                <ul className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
                  {coverage.data.unanswered.slice(0, 50).map((r) => (
                    <li key={r.id} className="rounded-lg border border-line p-2.5 text-xs">
                      <div className="flex items-center gap-1.5">{r.is_mandatory && <Badge tone="red">Mandatory</Badge>}</div>
                      <p className="mt-1 line-clamp-3">{r.description}</p>
                      <button className="mt-1.5 inline-flex items-center gap-1 font-medium text-accent-700 hover:underline" onClick={() => addSection.mutate({ title: r.description.slice(0, 80), guidance: r.description, requirement_id: r.id })}>
                        <ListPlus className="h-3.5 w-3.5" /> Add response section
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <LoadingBlock rows={2} />
          )}
        </Card>
      </div>

      <Dialog
        open={adding}
        onOpenChange={setAdding}
        title="Add section"
        footer={
          <>
            <Button variant="outline" onClick={() => setAdding(false)}>Cancel</Button>
            <Button loading={addSection.isPending} disabled={!newTitle.trim()} onClick={() => addSection.mutate({ title: newTitle.trim() })}>Add</Button>
          </>
        }
      >
        <Field label="Section title" htmlFor="new-section">
          <Input id="new-section" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} autoFocus />
        </Field>
      </Dialog>
    </>
  );
}
