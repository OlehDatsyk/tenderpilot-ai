import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, Eye, FileText, Loader2, RotateCw, Trash2, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { ConfirmButton, Dialog } from "@/components/dialog";
import { Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, Notice } from "@/components/ui";
import { api, downloadFile } from "@/lib/api";
import { useApiMutation } from "@/lib/hooks";
import type { DocumentItem, DocumentText } from "@/lib/types";
import { cn, formatBytes, formatDateTime } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";
const MAX_MB = 20;

function StatusPill({ d }: { d: DocumentItem }) {
  if (d.status === "processed") return <Badge tone="green"><CheckCircle2 className="h-3 w-3" /> Processed</Badge>;
  if (d.status === "needs_ocr") return <Badge tone="amber" title={d.status_message}><AlertTriangle className="h-3 w-3" /> OCR needed</Badge>;
  if (d.status === "failed") return <Badge tone="red" title={d.status_message}><AlertTriangle className="h-3 w-3" /> Failed</Badge>;
  return <Badge tone="blue"><Loader2 className="h-3 w-3 animate-spin" /> {d.status === "processing" ? "Processing" : "Queued"}</Badge>;
}

function TextViewer({ tenderId, doc, onClose }: { tenderId: string; doc: DocumentItem; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["doc-text", doc.id],
    queryFn: () => api<DocumentText>(`/api/v1/tenders/${tenderId}/documents/${doc.id}/text`),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={doc.original_filename} description="Extracted text (read-only). Page labels come from the PDF; DOCX/TXT files are split into sections." wide>
      {q.isLoading ? (
        <LoadingBlock />
      ) : q.isError ? (
        <ErrorState error={q.error} />
      ) : q.data!.pages.length === 0 ? (
        <p className="text-sm text-muted">No text could be extracted from this document.</p>
      ) : (
        <div className="space-y-4">
          {q.data!.pages.map((p, i) => (
            <section key={i}>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{p.label}</h4>
              <div className="prose-plain rounded-lg border border-line bg-slate-50/50 p-3 font-mono text-[12.5px]">{p.text}</div>
            </section>
          ))}
        </div>
      )}
    </Dialog>
  );
}

export function DocumentsTab({ tenderId }: { tenderId: string }) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [viewing, setViewing] = useState<DocumentItem | null>(null);

  const q = useQuery({
    queryKey: ["documents", tenderId],
    queryFn: () => api<DocumentItem[]>(`/api/v1/tenders/${tenderId}/documents`),
    refetchInterval: (query) => (query.state.data?.some((d) => d.status === "pending" || d.status === "processing") ? 2000 : false),
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["documents", tenderId] });
    qc.invalidateQueries({ queryKey: ["tender", tenderId] });
  };

  const upload = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (!ext || !["pdf", "docx", "txt"].includes(ext)) {
        toast.error(`${file.name}: only PDF, DOCX and TXT files are supported.`);
        continue;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.error(`${file.name}: larger than ${MAX_MB} MB.`);
        continue;
      }
      setUploading((n) => n + 1);
      try {
        const form = new FormData();
        form.append("file", file);
        await api(`/api/v1/tenders/${tenderId}/documents`, { method: "POST", form });
        toast.success(`${file.name} uploaded`);
      } catch (e) {
        toast.error(`${file.name}: ${e instanceof Error ? e.message : "upload failed"}`);
      } finally {
        setUploading((n) => n - 1);
        invalidate();
      }
    }
  };

  const reprocess = useApiMutation((id: string) => api(`/api/v1/tenders/${tenderId}/documents/${id}/reprocess`, { method: "POST" }), {
    success: "Re-processing started",
    invalidate: [["documents", tenderId]],
  });
  const remove = useApiMutation((id: string) => api(`/api/v1/tenders/${tenderId}/documents/${id}`, { method: "DELETE" }), {
    success: "Document deleted",
    invalidate: [["documents", tenderId], ["tender", tenderId]],
  });

  return (
    <div className="space-y-5">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          upload(e.dataTransfer.files);
        }}
        className={cn("card flex flex-col items-center justify-center gap-3 border-dashed px-6 py-8 text-center transition-colors", dragOver && "border-accent-600 bg-accent-50")}
      >
        <UploadCloud className="h-8 w-8 text-slate-400" />
        <div>
          <p className="text-sm font-medium">Drag tender documents here, or</p>
          <p className="text-xs text-muted">PDF, DOCX or TXT · up to {MAX_MB} MB each · scanned PDFs need OCR (not available)</p>
        </div>
        <input ref={inputRef} type="file" accept={ACCEPT} multiple hidden onChange={(e) => e.target.files && upload(e.target.files).then(() => (e.target.value = ""))} />
        <Button variant="secondary" loading={uploading > 0} onClick={() => inputRef.current?.click()}>
          Choose files
        </Button>
      </div>

      <Card title="Documents" description="Uploaded files are treated as untrusted data: they are parsed for text only and never executed.">
        {q.isLoading ? (
          <LoadingBlock />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data!.length === 0 ? (
          <EmptyState icon={<FileText className="h-5 w-5" />} title="No documents uploaded" description="Upload the tender documents (ITT, specification, terms) to enable analysis." />
        ) : (
          <div className="-mx-5 -my-5 overflow-x-auto">
            <table className="table-base min-w-[720px]">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Pages / text</th>
                  <th>Uploaded</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {q.data!.map((d) => (
                  <tr key={d.id}>
                    <td className="max-w-[300px]">
                      <div className="truncate font-medium" title={d.original_filename}>{d.original_filename}</div>
                      <div className="text-xs text-muted">{d.file_ext.toUpperCase()} · {formatBytes(d.size_bytes)}</div>
                    </td>
                    <td>
                      <StatusPill d={d} />
                      {(d.status === "needs_ocr" || d.status === "failed") && <p className="mt-1 max-w-xs text-xs text-muted">{d.status_message}</p>}
                    </td>
                    <td className="text-muted">
                      {d.page_count ? `${d.page_count} pages · ` : ""}
                      {d.char_count.toLocaleString()} chars
                    </td>
                    <td className="whitespace-nowrap text-muted">{formatDateTime(d.created_at)}</td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" aria-label="View extracted text" title="View extracted text" disabled={!d.char_count} onClick={() => setViewing(d)}>
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" aria-label="Download original" title="Download original" onClick={() => downloadFile(`/api/v1/tenders/${tenderId}/documents/${d.id}/download`, d.original_filename).catch((e) => toast.error(e.message))}>
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" aria-label="Re-run extraction" title="Re-run text extraction" disabled={d.status === "processing" || d.status === "pending"} onClick={() => reprocess.mutate(d.id)}>
                          <RotateCw className="h-4 w-4" />
                        </Button>
                        <ConfirmButton
                          title="Delete document?"
                          description={`"${d.original_filename}" will be deleted. Requirements already extracted from it are kept but lose their document link.`}
                          onConfirm={() => remove.mutateAsync(d.id)}
                          trigger={(open) => (
                            <Button variant="ghost" size="icon" aria-label="Delete document" title="Delete" className="text-red-600 hover:bg-red-50" onClick={open}>
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
      {q.data?.some((d) => d.status === "needs_ocr") && (
        <Notice tone="amber">Some documents appear to be scanned images. OCR is not configured on this server, so no text was extracted from them. Upload a text-based version to include them in the analysis.</Notice>
      )}
      {viewing && <TextViewer tenderId={tenderId} doc={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}
