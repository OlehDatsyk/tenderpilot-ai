import { useQuery } from "@tanstack/react-query";
import { FileDown } from "lucide-react";
import { useState } from "react";
import { Card, EmptyState, ErrorState, Field, LoadingBlock, Notice, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { Page, Tender } from "@/lib/types";
import { ExportsPanel } from "./tender/ExportsPanel";

export default function ExportsPage() {
  const q = useQuery({ queryKey: ["tenders", "options"], queryFn: () => api<Page<Tender>>("/api/v1/tenders?page_size=100&sort=updated_at&order=desc") });
  const [selected, setSelected] = useState("");
  const tender = q.data?.items.find((t) => t.id === selected) ?? q.data?.items[0];

  return (
    <>
      <PageHeader title="Export Centre" description="Download reports as PDF or DOCX, and the compliance matrix as CSV." />
      <Notice tone="blue" className="mb-5">
        Exports contain only your organisation's data. Content produced by AI or demo mode is clearly labelled as draft or generated content in every file.
      </Notice>
      {q.isLoading ? (
        <LoadingBlock />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !tender ? (
        <EmptyState icon={<FileDown className="h-5 w-5" />} title="Nothing to export yet" description="Create a tender project first." />
      ) : (
        <>
          <Card className="mb-5">
            <Field label="Tender" htmlFor="export-tender">
              <Select id="export-tender" className="max-w-xl" value={tender.id} onChange={(e) => setSelected(e.target.value)}>
                {q.data!.items.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
              </Select>
            </Field>
          </Card>
          <ExportsPanel key={tender.id} tenderId={tender.id} tenderTitle={tender.title} />
        </>
      )}
    </>
  );
}
