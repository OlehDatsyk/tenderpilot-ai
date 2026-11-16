import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ListChecks, MessageSquare, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { PriorityBadge } from "@/components/badges";
import { ConfirmButton, Dialog } from "@/components/dialog";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Select, Textarea } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApiMutation, useMembers } from "@/lib/hooks";
import { PRIORITIES, TASK_STATUSES } from "@/lib/labels";
import type { Page, Task, TaskDetail, TaskStatus, Tender } from "@/lib/types";
import { cn, formatDate, timeAgo } from "@/lib/utils";

const schema = z.object({
  title: z.string().trim().min(1, "Title is required").max(300),
  description: z.string().max(20000),
  tender_id: z.string(),
  assignee_id: z.string(),
  priority: z.enum(["low", "medium", "high", "critical"]),
  status: z.enum(["todo", "in_progress", "blocked", "done"]),
  due_date: z.string(),
});
type Values = z.infer<typeof schema>;

function TaskFormDialog({ open, onOpenChange, tenderId }: { open: boolean; onOpenChange: (o: boolean) => void; tenderId?: string }) {
  const members = useMembers();
  const tenders = useQuery({
    queryKey: ["tenders", "options"],
    queryFn: () => api<Page<Tender>>("/api/v1/tenders?page_size=100&sort=title&order=asc"),
    enabled: open && !tenderId,
  });
  const { register, handleSubmit, formState, reset } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { title: "", description: "", tender_id: tenderId ?? "", assignee_id: "", priority: "medium", status: "todo", due_date: "" },
  });
  const create = useApiMutation(
    (v: Values) =>
      api<Task>("/api/v1/tasks", {
        method: "POST",
        body: { ...v, tender_id: v.tender_id || null, assignee_id: v.assignee_id || null, due_date: v.due_date || null },
      }),
    {
      success: "Task created",
      invalidate: [["tasks"], ["tender"], ["dashboard"]],
      onSuccess: () => {
        reset();
        onOpenChange(false);
      },
    },
  );
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New task"
      footer={
        <>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="task-form" loading={create.isPending}>Create task</Button>
        </>
      }
    >
      <form id="task-form" className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit((v) => create.mutate(v))} noValidate>
        <Field label="Title" htmlFor="task-title" error={formState.errors.title?.message} className="sm:col-span-2">
          <Input id="task-title" {...register("title")} />
        </Field>
        {!tenderId && (
          <Field label="Tender" htmlFor="task-tender" className="sm:col-span-2">
            <Select id="task-tender" {...register("tender_id")}>
              <option value="">Not linked to a tender</option>
              {tenders.data?.items.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
            </Select>
          </Field>
        )}
        <Field label="Assignee" htmlFor="task-assignee">
          <Select id="task-assignee" {...register("assignee_id")}>
            <option value="">Unassigned</option>
            {members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
          </Select>
        </Field>
        <Field label="Due date" htmlFor="task-due">
          <Input id="task-due" type="date" {...register("due_date")} />
        </Field>
        <Field label="Priority" htmlFor="task-priority">
          <Select id="task-priority" {...register("priority")}>
            {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </Select>
        </Field>
        <Field label="Status" htmlFor="task-status">
          <Select id="task-status" {...register("status")}>
            {TASK_STATUSES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </Select>
        </Field>
        <Field label="Description" htmlFor="task-desc" className="sm:col-span-2">
          <Textarea id="task-desc" rows={3} {...register("description")} />
        </Field>
      </form>
    </Dialog>
  );
}

function TaskDetailDialog({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const { me } = useAuth();
  const members = useMembers();
  const [comment, setComment] = useState("");
  const q = useQuery({ queryKey: ["task", taskId], queryFn: () => api<TaskDetail>(`/api/v1/tasks/${taskId}`) });
  const update = useApiMutation((body: Record<string, unknown>) => api(`/api/v1/tasks/${taskId}`, { method: "PATCH", body }), {
    success: "Task updated",
    invalidate: [["task", taskId], ["tasks"], ["dashboard"]],
  });
  const addComment = useApiMutation(() => api(`/api/v1/tasks/${taskId}/comments`, { method: "POST", body: { body: comment } }), {
    invalidate: [["task", taskId], ["tasks"]],
    onSuccess: () => setComment(""),
  });
  const delComment = useApiMutation((cid: string) => api(`/api/v1/tasks/${taskId}/comments/${cid}`, { method: "DELETE" }), {
    invalidate: [["task", taskId], ["tasks"]],
  });
  const remove = useApiMutation(() => api(`/api/v1/tasks/${taskId}`, { method: "DELETE" }), {
    success: "Task deleted",
    invalidate: [["tasks"], ["dashboard"], ["tender"]],
    onSuccess: onClose,
  });
  const t = q.data;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={t?.title ?? "Task"} wide description={t?.tender_title ? `Tender: ${t.tender_title}` : "Organisation task"}>
      {q.isLoading ? (
        <LoadingBlock />
      ) : q.isError ? (
        <ErrorState error={q.error} />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Status" htmlFor="td-status">
              <Select id="td-status" value={t!.status} onChange={(e) => update.mutate({ status: e.target.value })}>
                {TASK_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </Select>
            </Field>
            <Field label="Priority" htmlFor="td-priority">
              <Select id="td-priority" value={t!.priority} onChange={(e) => update.mutate({ priority: e.target.value })}>
                {PRIORITIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </Select>
            </Field>
            <Field label="Assignee" htmlFor="td-assignee">
              <Select id="td-assignee" value={t!.assignee_id ?? ""} onChange={(e) => update.mutate(e.target.value ? { assignee_id: e.target.value } : { clear_assignee: true })}>
                <option value="">Unassigned</option>
                {members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
              </Select>
            </Field>
            <Field label="Due date" htmlFor="td-due">
              <Input id="td-due" type="date" defaultValue={t!.due_date ?? ""} onBlur={(e) => e.target.value !== (t!.due_date ?? "") && update.mutate(e.target.value ? { due_date: e.target.value } : { clear_due_date: true })} />
            </Field>
          </div>
          {t!.description && <p className="prose-plain rounded-lg bg-slate-50 p-3">{t!.description}</p>}
          <div>
            <h3 className="mb-2 text-sm font-semibold">Comments</h3>
            {t!.comments.length === 0 ? (
              <p className="text-sm text-muted">No comments yet.</p>
            ) : (
              <ul className="space-y-3">
                {t!.comments.map((c) => (
                  <li key={c.id} className="rounded-lg border border-line p-3 text-sm">
                    <div className="mb-1 flex items-center justify-between text-xs text-muted">
                      <span><span className="font-medium text-ink">{c.author_name ?? "Former member"}</span> · {timeAgo(c.created_at)}</span>
                      {(c.author_id === me?.id || me?.role !== "member") && (
                        <button className="text-red-600 hover:underline" onClick={() => delComment.mutate(c.id)}>Delete</button>
                      )}
                    </div>
                    <p className="prose-plain">{c.body}</p>
                  </li>
                ))}
              </ul>
            )}
            <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (comment.trim()) addComment.mutate(undefined); }}>
              <Input aria-label="Add a comment" placeholder="Add a comment…" value={comment} onChange={(e) => setComment(e.target.value)} />
              <Button type="submit" loading={addComment.isPending} disabled={!comment.trim()}>Post</Button>
            </form>
          </div>
          <div className="flex justify-end border-t border-line pt-4">
            <ConfirmButton title="Delete task?" description="The task and its comments will be deleted." onConfirm={() => remove.mutateAsync(undefined)} trigger={(open) => (
              <Button variant="ghost" className="text-red-600 hover:bg-red-50" onClick={open}><Trash2 className="h-4 w-4" /> Delete task</Button>
            )} />
          </div>
        </div>
      )}
    </Dialog>
  );
}

const statusTone = { todo: "slate", in_progress: "blue", blocked: "red", done: "green" } as const;

export function TaskList({ tenderId }: { tenderId?: string }) {
  const [filter, setFilter] = useState<{ status: string; assignee: string; overdue: boolean }>({ status: "", assignee: "", overdue: false });
  const [creating, setCreating] = useState(false);
  const [openTask, setOpenTask] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["tasks", tenderId ?? "all", filter],
    queryFn: () => api<Task[]>(`/api/v1/tasks${qs({ tender_id: tenderId, status: filter.status, assignee: filter.assignee, overdue: filter.overdue || undefined })}`),
  });
  const setStatus = useApiMutation(({ id, status }: { id: string; status: TaskStatus }) => api(`/api/v1/tasks/${id}`, { method: "PATCH", body: { status } }), {
    invalidate: [["tasks"], ["dashboard"]],
  });

  return (
    <Card
      title={tenderId ? "Tender tasks" : "All tasks"}
      actions={<Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> New task</Button>}
    >
      <div className="mb-4 flex flex-wrap gap-2">
        <Select aria-label="Status filter" className="w-40" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
          <option value="">All statuses</option>
          {TASK_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </Select>
        <Select aria-label="Assignee filter" className="w-40" value={filter.assignee} onChange={(e) => setFilter({ ...filter, assignee: e.target.value })}>
          <option value="">Anyone</option>
          <option value="me">Assigned to me</option>
        </Select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4" checked={filter.overdue} onChange={(e) => setFilter({ ...filter, overdue: e.target.checked })} /> Overdue only
        </label>
      </div>
      {q.isLoading ? (
        <LoadingBlock />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data!.length === 0 ? (
        <EmptyState icon={<ListChecks className="h-5 w-5" />} title="No tasks" description="Create tasks to coordinate the bid team." />
      ) : (
        <div className="-mx-5 -mb-5 overflow-x-auto">
          <table className="table-base min-w-[760px]">
            <thead>
              <tr><th>Task</th>{!tenderId && <th>Tender</th>}<th>Assignee</th><th>Due</th><th>Priority</th><th className="w-40">Status</th></tr>
            </thead>
            <tbody>
              {q.data!.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50/60">
                  <td>
                    <button className="text-left font-medium hover:underline" onClick={() => setOpenTask(t.id)}>{t.title}</button>
                    {t.comment_count > 0 && <span className="ml-2 inline-flex items-center gap-0.5 text-xs text-muted"><MessageSquare className="h-3 w-3" />{t.comment_count}</span>}
                  </td>
                  {!tenderId && <td className="text-sm">{t.tender_id ? <Link className="hover:underline" to={`/tenders/${t.tender_id}?tab=tasks`}>{t.tender_title}</Link> : <span className="text-muted">—</span>}</td>}
                  <td className="text-sm">{t.assignee_name ?? <span className="text-muted">Unassigned</span>}</td>
                  <td className={cn("whitespace-nowrap text-sm", t.is_overdue && "font-medium text-red-600")}>
                    {t.is_overdue && <CalendarClock className="mr-1 inline h-3.5 w-3.5" />}
                    {formatDate(t.due_date)}
                  </td>
                  <td><PriorityBadge priority={t.priority} /></td>
                  <td>
                    <Select aria-label="Task status" className="py-1.5 text-[13px]" value={t.status} onChange={(e) => setStatus.mutate({ id: t.id, status: e.target.value as TaskStatus })}>
                      {TASK_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </Select>
                    <div className="mt-1"><Badge tone={statusTone[t.status]}>{TASK_STATUSES.find((s) => s.value === t.status)?.label}</Badge></div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <TaskFormDialog open={creating} onOpenChange={setCreating} tenderId={tenderId} />
      {openTask && <TaskDetailDialog taskId={openTask} onClose={() => setOpenTask(null)} />}
    </Card>
  );
}

export default function TasksPage() {
  return (
    <>
      <PageHeader title="Tasks" description="Coordinate work across all tender projects. Overdue tasks are highlighted." />
      <TaskList />
    </>
  );
}
