import { useQuery } from "@tanstack/react-query";
import { FileDown, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, Card, Select } from "@/components/ui";
import { api, downloadFile } from "@/lib/api";
import type { Proposal } from "@/lib/types";

const KINDS = [
  { kind: "summary", title: "Tender summary", description: "Project details, compliance progress, documents and the recorded decision.", formats: ["pdf", "docx"] },
  { kind: "analysis", title: "Tender analysis report", description: "Latest AI/demo analysis with source verification status. Clearly labelled as generated content.", formats: ["pdf", "docx"] },
  { kind: "compliance", title: "Compliance matrix", description: "All requirements with origin, source, status, assignee and evidence.", formats: ["pdf", "docx", "csv"] },
  { kind: "bid", title: "Bid / no-bid report", description: "Latest assessment, factor scores and the final recorded decision.", formats: ["pdf", "docx"] },
] as const;

export function ExportsPanel({ tenderId, tenderTitle }: { tenderId: string; tenderTitle: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const proposals = useQuery({ queryKey: ["proposals", tenderId], queryFn: () => api<Proposal[]>(`/api/v1/tenders/${tenderId}/proposals`) });
  const [proposalId, setProposalId] = useState("");
  const pid = proposalId || proposals.data?.[0]?.id || "";

  const run = async (kind: string, fmt: string, extra = "") => {
    const key = `${kind}-${fmt}`;
    setBusy(key);
    try {
      await downloadFile(`/api/v1/tenders/${tenderId}/exports/${kind}?format=${fmt}${extra}`, `${tenderTitle}-${kind}.${fmt}`);
      toast.success("Export downloaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  };

  const icon = (fmt: string) => (fmt === "csv" ? <FileSpreadsheet className="h-4 w-4" /> : fmt === "docx" ? <FileText className="h-4 w-4" /> : <FileDown className="h-4 w-4" />);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {KINDS.map((k) => (
        <Card key={k.kind} title={k.title} description={k.description}>
          <div className="flex flex-wrap gap-2">
            {k.formats.map((fmt) => (
              <Button key={fmt} variant="outline" size="sm" loading={busy === `${k.kind}-${fmt}`} onClick={() => run(k.kind, fmt)}>
                {icon(fmt)} {fmt.toUpperCase()}
              </Button>
            ))}
          </div>
        </Card>
      ))}
      <Card title="Proposal draft" description="Exports the selected draft. AI-generated or demo content is labelled as a draft.">
        {proposals.data && proposals.data.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <Select aria-label="Proposal to export" className="max-w-xs" value={pid} onChange={(e) => setProposalId(e.target.value)}>
              {proposals.data.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </Select>
            {(["docx", "pdf"] as const).map((fmt) => (
              <Button key={fmt} variant="outline" size="sm" loading={busy === `proposal-${fmt}`} onClick={() => run("proposal", fmt, `&proposal_id=${pid}`)}>
                {icon(fmt)} {fmt.toUpperCase()}
              </Button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No proposal drafts for this tender yet.</p>
        )}
      </Card>
    </div>
  );
}
