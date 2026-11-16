import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ListChecks, Pencil, Plus, Quote, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { CategoryBadge, OriginBadge, ResponseBadge, VerifiedBadge } from "@/components/badges";
import { ConfirmButton, Dialog } from "@/components/dialog";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, LoadingBlock, Progress, Select, Textarea } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { useApiMutation, useMembers } from "@/lib/hooks";
import { CATEGORIES, PRIORITIES, RESPONSE_STATUSES } from "@/lib/labels";
import type { Category, ComplianceSummary, Priority, Requirement, ResponseStatus } from "@/lib/types";

const editSchema = z.object({
  description: z.string().trim().min(3, "At least 3 characters").max(5000),
  category: z.string(),
  priority: z.string(),
  is_mandatory: z.boolean(),
  response_status: z.string(),
  assignee_id: z.string(),
  evidence: z.string().max(20000),
  comments: z.string().max(20000),
});
type EditValues = z.infer<typeof editSchema>;

function RequirementDialog({ tenderId, req, onClose }: { tenderId: string; req: Requirement | "new"; onClose: () => void }) {
  const members = useMembers();
  const isNew = req === "new";
  const { register, handleSubmit, formState } = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: isNew
      ? { description: "", category: "other", priority: "medium", is_mandatory: false, response_status: "not_started", assignee_id: "", evidence: "", comments: "" }
      : { description: req.description, category: req.category, priority: req.priority, is_mandatory: req.is_mandatory, response_status: req.response_status, assignee_id: req.assignee_id ?? "", evidence: req.evidence, comments: req.comments },
  });
  const save = useApiMutation(
    async (v: EditValues) => {
      if (isNew) {
        const created = await api<Requirement>(`/api/v1/tenders/${tenderId}/requirements`, {
          method: "POST",
          body: { description: v.description, category: v.category, priority: v.priority, is_mandatory: v.is_mandatory },
        });
        return api<Requirement>(`/api/v1/requirements/${created.id}`, {
          method: "PATCH",
          body: { response_status: v.response_status, evidence: v.evidence, comments: v.comments, ...(v.assignee_id ? { assignee_id: v.assignee_id } : {}) },
        });
      }
      return api<Requirement>(`/api/v1/requirements/${req.id}`, {
        method: "PATCH",
        body: { ...v, assignee_id: v.assignee_id || null, clear_assignee: !v.assignee_id },
      });
    },
    { success: isNew ? "Requirement added" : "Requirement saved", invalidate: [["requirements", tenderId], ["compliance", tenderId], ["tender", tenderId]], onSuccess: onClose },
  );
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      wide
      title={isNew ? "Add requirement" : "Edit requirement"}
      description={isNew ? "Manually entered requirements are marked as user-entered." : undefined}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="req-form" loading={save.isPending}>Save</Button>
        </>
      }
    >
      <form id="req-form" className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit((v) => save.mutate(v))} noValidate>
        {!isNew && (
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <OriginBadge origin={req.origin} />
            <VerifiedBadge verified={req.source_verified} />
            <span className="text-xs text-muted">
              Source: {req.source_document_name || "unavailable"}
              {req.source_page ? `, page ${req.source_page}` : ""}
            </span>
          </div>
        )}
        {!isNew && req.source_quote && (
          <blockquote className="flex gap-2 rounded-lg border border-line bg-slate-50 p-3 text-sm italic text-muted sm:col-span-2">
            <Quote className="h-4 w-4 shrink-0" /> {req.source_quote}
          </blockquote>
        )}
        <Field label="Requirement" htmlFor="r-desc" error={formState.errors.description?.message} className="sm:col-span-2">
          <Textarea id="r-desc" rows={3} {...register("description")} />
        </Field>
        <Field label="Category" htmlFor="r-cat">
          <Select id="r-cat" {...register("category")}>
            {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </Select>
        </Field>
        <Field label="Priority" htmlFor="r-pri">
          <Select id="r-pri" {...register("priority")}>
            {PRIORITIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </Select>
        </Field>
        <Field label="Response status" htmlFor="r-status">
          <Select id="r-status" {...register("response_status")}>
            {RESPONSE_STATUSES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </Select>
        </Field>
        <Field label="Assigned to" htmlFor="r-assignee">
          <Select id="r-assignee" {...register("assignee_id")}>
            <option value="">Unassigned</option>
            {members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" className="h-4 w-4 rounded border-line accent-[var(--color-accent-600)]" {...register("is_mandatory")} /> Mandatory (pass/fail) requirement
        </label>
        <Field label="Evidence / supporting notes" htmlFor="r-ev" hint="Used as the only evidence when AI drafts responses — never claim compliance without it." className="sm:col-span-2">
          <Textarea id="r-ev" rows={3} {...register("evidence")} />
        </Field>
        <Field label="Internal comments" htmlFor="r-com" className="sm:col-span-2">
          <Textarea id="r-com" rows={2} {...register("comments")} />
        </Field>
      </form>
    </Dialog>
  );
}

export function ComplianceTab({ tenderId }: { tenderId: string }) {
  const [filters, setFilters] = useState({ mandatory: "", status: "", category: "", q: "" });
  const [editing, setEditing] = useState<Requirement | "new" | null>(null);
  const reqs = useQuery({
    queryKey: ["requirements", tenderId, filters],
    queryFn: () =>
      api<Requirement[]>(`/api/v1/tenders/${tenderId}/requirements${qs({ mandatory: filters.mandatory || undefined, status: filters.status, category: filters.category, q: filters.q })}`),
  });
  const summary = useQuery({ queryKey: ["compliance", tenderId], queryFn: () => api<ComplianceSummary>(`/api/v1/tenders/${tenderId}/compliance`) });
  const setStatus = useApiMutation(
    ({ id, status }: { id: string; status: ResponseStatus }) => api(`/api/v1/requirements/${id}`, { method: "PATCH", body: { response_status: status } }),
    { invalidate: [["requirements", tenderId], ["compliance", tenderId], ["tender", tenderId]] },
  );
  const remove = useApiMutation((id: string) => api(`/api/v1/requirements/${id}`, { method: "DELETE" }), {
    success: "Requirement deleted",
    invalidate: [["requirements", tenderId], ["compliance", tenderId], ["tender", tenderId]],
  });
  const s = summary.data;
  const filtered = Object.values(filters).some(Boolean);

  return (
    <div className="space-y-5">
      {s && s.total > 0 && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card p-4">
            <div className="flex justify-between text-sm"><span className="text-muted">Overall completion</span><span className="font-semibold">{s.percent_complete}%</span></div>
            <Progress value={s.percent_complete} className="mt-2" />
            <p className="mt-2 text-xs text-muted">{s.addressed} of {s.total} requirements have a final status</p>
          </div>
          <div className="card p-4">
            <div className="flex justify-between text-sm"><span className="text-muted">Mandatory completion</span><span className="font-semibold">{s.mandatory_percent_complete}%</span></div>
            <Progress value={s.mandatory_percent_complete} tone="navy" className="mt-2" />
            <p className="mt-2 text-xs text-muted">{s.mandatory_total} mandatory requirements</p>
          </div>
          <div className="card flex flex-wrap content-start gap-1.5 p-4">
            {RESPONSE_STATUSES.map((x) => (
              <Badge key={x.value} tone="slate">{x.label}: {s.by_status[x.value] ?? 0}</Badge>
            ))}
          </div>
        </div>
      )}

      <Card
        title="Compliance matrix"
        description="Every requirement shows where it came from: AI-extracted, demo heuristic, or user-entered."
        actions={<Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> Add requirement</Button>}
      >
        <div className="mb-4 grid gap-2 sm:grid-cols-4">
          <Input aria-label="Search requirements" placeholder="Search…" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
          <Select aria-label="Mandatory filter" value={filters.mandatory} onChange={(e) => setFilters({ ...filters, mandatory: e.target.value })}>
            <option value="">Mandatory & optional</option>
            <option value="true">Mandatory only</option>
            <option value="false">Optional only</option>
          </Select>
          <Select aria-label="Status filter" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">All statuses</option>
            {RESPONSE_STATUSES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
          </Select>
          <Select aria-label="Category filter" value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>
            <option value="">All categories</option>
            {CATEGORIES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
          </Select>
        </div>
        {reqs.isLoading ? (
          <LoadingBlock />
        ) : reqs.isError ? (
          <ErrorState error={reqs.error} onRetry={() => reqs.refetch()} />
        ) : reqs.data!.length === 0 ? (
          <EmptyState
            icon={<ListChecks className="h-5 w-5" />}
            title={filtered ? "No requirements match the filters" : "No requirements yet"}
            description={filtered ? undefined : "Run the AI analysis on uploaded documents or add requirements manually."}
          />
        ) : (
          <div className="-mx-5 -mb-5 overflow-x-auto">
            <table className="table-base min-w-[980px]">
              <thead>
                <tr>
                  <th className="w-[38%]">Requirement</th>
                  <th>Category</th>
                  <th>Source</th>
                  <th>Assignee</th>
                  <th className="w-48">Response status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {reqs.data!.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div className="text-[13.5px] leading-snug">{r.description}</div>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {r.is_mandatory && <Badge tone="red">Mandatory</Badge>}
                        <Badge tone="slate">{(r.priority as Priority)[0].toUpperCase() + r.priority.slice(1)}</Badge>
                        <OriginBadge origin={r.origin} />
                      </div>
                      {r.evidence && <div className="mt-1.5 line-clamp-2 text-xs text-muted">Evidence: {r.evidence}</div>}
                    </td>
                    <td><CategoryBadge category={r.category as Category} /></td>
                    <td className="max-w-[200px]">
                      <VerifiedBadge verified={r.source_verified} />
                      <div className="mt-1 truncate text-xs text-muted" title={r.source_quote ?? ""}>
                        {r.source_document_name || "Unavailable"}
                        {r.source_page ? `, p. ${r.source_page}` : ""}
                      </div>
                    </td>
                    <td className="text-sm">{r.assignee_name ?? <span className="text-muted">—</span>}</td>
                    <td>
                      <Select
                        aria-label="Response status"
                        className="py-1.5 text-[13px]"
                        value={r.response_status}
                        onChange={(e) => setStatus.mutate({ id: r.id, status: e.target.value as ResponseStatus })}
                      >
                        {RESPONSE_STATUSES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
                      </Select>
                      <div className="mt-1"><ResponseBadge status={r.response_status} /></div>
                    </td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" aria-label="Edit requirement" onClick={() => setEditing(r)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <ConfirmButton
                          title="Delete requirement?"
                          description="The requirement will be removed from the compliance matrix."
                          onConfirm={() => remove.mutateAsync(r.id)}
                          trigger={(open) => (
                            <Button variant="ghost" size="icon" aria-label="Delete requirement" className="text-red-600 hover:bg-red-50" onClick={open}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {editing && <RequirementDialog tenderId={tenderId} req={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
