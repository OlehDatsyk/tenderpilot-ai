import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { Button, Card, ErrorState, Field, Input, LoadingBlock, Notice, PageHeader, Progress, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useApiMutation } from "@/lib/hooks";
import type { CompanyProfile } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

type Values = Omit<CompanyProfile, "updated_at" | "completeness">;

const FIELDS: { key: keyof Values; label: string; hint: string; rows: number }[] = [
  { key: "overview", label: "Company overview", hint: "Who you are, size, locations, legal entity.", rows: 4 },
  { key: "services", label: "Services", hint: "Services and products you offer.", rows: 4 },
  { key: "capabilities", label: "Capabilities", hint: "Technical capabilities, tools, methodologies.", rows: 4 },
  { key: "experience", label: "Relevant experience", hint: "Verified past projects: client (if shareable), scope, value, dates, outcomes.", rows: 6 },
  { key: "certifications", label: "Certifications & accreditations", hint: "Include certificate numbers and expiry dates.", rows: 3 },
  { key: "client_references", label: "Client references", hint: "Only references that have agreed to be contacted.", rows: 4 },
  { key: "team", label: "Team & key staff", hint: "Roles, qualifications, availability.", rows: 4 },
  { key: "differentiators", label: "Differentiators & social value", hint: "What makes you different; social value commitments.", rows: 3 },
];

export default function CompanyProfilePage() {
  const q = useQuery({ queryKey: ["company-profile"], queryFn: () => api<CompanyProfile>("/api/v1/organization/company-profile") });
  const { register, handleSubmit, formState, reset } = useForm<Values>({ values: q.data });
  const save = useApiMutation((v: Values) => api<CompanyProfile>("/api/v1/organization/company-profile", { method: "PUT", body: v }), {
    success: "Company profile saved",
    invalidate: [["company-profile"]],
    onSuccess: (p) => reset(p),
  });

  return (
    <>
      <PageHeader
        title="Company Profile"
        description="Verified company information. Proposal drafts and bid assessments may only use facts recorded here."
        actions={<Button form="company-form" type="submit" loading={save.isPending} disabled={!formState.isDirty}>Save profile</Button>}
      />
      {q.isLoading ? (
        <LoadingBlock rows={8} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <form id="company-form" onSubmit={handleSubmit((v) => save.mutate(v))} className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div className="space-y-6">
            <Card title="Basics">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Company name" htmlFor="cp-name"><Input id="cp-name" maxLength={200} {...register("company_name")} /></Field>
                <Field label="Website" htmlFor="cp-web"><Input id="cp-web" maxLength={300} {...register("website")} /></Field>
              </div>
            </Card>
            <Card title="Verified information">
              <div className="space-y-5">
                {FIELDS.map((f) => (
                  <Field key={f.key} label={f.label} htmlFor={`cp-${f.key}`} hint={f.hint}>
                    <Textarea id={`cp-${f.key}`} rows={f.rows} {...register(f.key)} />
                  </Field>
                ))}
              </div>
            </Card>
          </div>
          <div className="space-y-4">
            <Card title="Completeness">
              <div className="text-2xl font-semibold">{q.data!.completeness}%</div>
              <Progress value={q.data!.completeness} className="mt-2" />
              <p className="mt-2 text-xs text-muted">Last updated {formatDateTime(q.data!.updated_at)}</p>
            </Card>
            <Notice tone="teal" icon={<ShieldCheck className="h-4 w-4" />}>
              Only record information you can evidence. TenderPilot never invents experience, references, certifications, staff or figures — where information is missing, drafts contain <code>[COMPANY INFORMATION REQUIRED]</code>.
            </Notice>
          </div>
        </form>
      )}
    </>
  );
}
