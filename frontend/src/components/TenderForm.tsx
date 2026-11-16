import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api } from "@/lib/api";
import { useApiMutation } from "@/lib/hooks";
import { PRIORITIES, TENDER_STATUSES, TENDER_TYPES } from "@/lib/labels";
import type { Tender } from "@/lib/types";
import { fromLocalInput, toLocalInput } from "@/lib/utils";
import { Dialog } from "./dialog";
import { Button, Field, Input, Select, Textarea } from "./ui";

const schema = z.object({
  title: z.string().trim().min(1, "Title is required").max(300),
  buyer: z.string().trim().max(300),
  reference: z.string().trim().max(120),
  description: z.string().max(20000),
  tender_type: z.enum(["tender", "rfp", "rfq", "rfi", "procurement", "questionnaire", "other"]),
  status: z.enum(["draft", "under_review", "bid_decision", "in_preparation", "internal_review", "submitted", "won", "lost", "withdrawn"]),
  priority: z.enum(["low", "medium", "high", "critical"]),
  submission_deadline: z.string(),
  estimated_value: z
    .string()
    .trim()
    .refine((v) => v === "" || (/^\d+(\.\d{1,2})?$/.test(v) && Number(v) >= 0), "Enter a positive amount (max 2 decimals)"),
  currency: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{3}$/, "3-letter ISO code, e.g. EUR"),
  notes: z.string().max(20000),
});
type Values = z.infer<typeof schema>;

function defaults(t?: Tender): Values {
  return {
    title: t?.title ?? "",
    buyer: t?.buyer ?? "",
    reference: t?.reference ?? "",
    description: t?.description ?? "",
    tender_type: t?.tender_type ?? "tender",
    status: t?.status ?? "draft",
    priority: t?.priority ?? "medium",
    submission_deadline: toLocalInput(t?.submission_deadline),
    estimated_value: t?.estimated_value ? String(Number(t.estimated_value)) : "",
    currency: t?.currency ?? "EUR",
    notes: t?.notes ?? "",
  };
}

export function TenderFormDialog({
  open,
  onOpenChange,
  tender,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  tender?: Tender;
  onSaved?: (t: Tender) => void;
}) {
  const { register, handleSubmit, formState, reset } = useForm<Values>({ resolver: zodResolver(schema), values: defaults(tender) });
  const save = useApiMutation(
    (v: Values) => {
      const body = {
        ...v,
        currency: v.currency.toUpperCase(),
        submission_deadline: fromLocalInput(v.submission_deadline),
        estimated_value: v.estimated_value === "" ? null : v.estimated_value,
      };
      return tender
        ? api<Tender>(`/api/v1/tenders/${tender.id}`, { method: "PATCH", body })
        : api<Tender>("/api/v1/tenders", { method: "POST", body });
    },
    {
      success: tender ? "Tender updated" : "Tender created",
      invalidate: [["tenders"], ["tender"], ["dashboard"], ["activity"]],
      onSuccess: (t) => {
        onOpenChange(false);
        reset();
        onSaved?.(t);
      },
    },
  );
  const e = formState.errors;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      wide
      title={tender ? "Edit tender" : "New tender project"}
      description="Information you enter here is user-provided and is never overwritten by AI analysis."
      footer={
        <>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="tender-form" loading={save.isPending}>
            {tender ? "Save changes" : "Create tender"}
          </Button>
        </>
      }
    >
      <form id="tender-form" onSubmit={handleSubmit((v) => save.mutate(v))} className="grid gap-4 sm:grid-cols-2" noValidate>
        <Field label="Title" htmlFor="t-title" error={e.title?.message} className="sm:col-span-2">
          <Input id="t-title" {...register("title")} placeholder="e.g. Managed IT Support Services" />
        </Field>
        <Field label="Buyer / contracting authority" htmlFor="t-buyer" error={e.buyer?.message}>
          <Input id="t-buyer" {...register("buyer")} />
        </Field>
        <Field label="Tender reference" htmlFor="t-ref" error={e.reference?.message}>
          <Input id="t-ref" {...register("reference")} />
        </Field>
        <Field label="Type" htmlFor="t-type">
          <Select id="t-type" {...register("tender_type")}>
            {TENDER_TYPES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Status" htmlFor="t-status">
          <Select id="t-status" {...register("status")}>
            {TENDER_STATUSES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Priority" htmlFor="t-priority">
          <Select id="t-priority" {...register("priority")}>
            {PRIORITIES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Submission deadline" htmlFor="t-deadline" hint="Your local time">
          <Input id="t-deadline" type="datetime-local" {...register("submission_deadline")} />
        </Field>
        <Field label="Estimated value" htmlFor="t-value" error={e.estimated_value?.message}>
          <Input id="t-value" inputMode="decimal" {...register("estimated_value")} placeholder="Optional" />
        </Field>
        <Field label="Currency" htmlFor="t-cur" error={e.currency?.message}>
          <Input id="t-cur" maxLength={3} className="uppercase" {...register("currency")} />
        </Field>
        <Field label="Description" htmlFor="t-desc" className="sm:col-span-2">
          <Textarea id="t-desc" rows={3} {...register("description")} />
        </Field>
        <Field label="Internal notes" htmlFor="t-notes" hint="Visible to your organisation only." className="sm:col-span-2">
          <Textarea id="t-notes" rows={3} {...register("notes")} />
        </Field>
      </form>
    </Dialog>
  );
}
