import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CircleHelp, Eraser, Send, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { DemoBadge } from "@/components/badges";
import { ConfirmButton } from "@/components/dialog";
import { Badge, Button, Card, ErrorState, LoadingBlock, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAIStatus } from "@/lib/hooks";
import type { AssistantMessage } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { AIRequiredNotice } from "./AnalysisTab";

const SUGGESTIONS = [
  "What are the most important mandatory requirements?",
  "Which supporting documents do we need to provide?",
  "What are the main risks?",
  "Summarise the evaluation criteria.",
  "Which requirements are not yet addressed?",
  "What should we complete first?",
];

export function AssistantTab({ tenderId }: { tenderId: string }) {
  const qc = useQueryClient();
  const ai = useAIStatus();
  const [question, setQuestion] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const key = ["assistant", tenderId];
  const q = useQuery({ queryKey: key, queryFn: () => api<AssistantMessage[]>(`/api/v1/tenders/${tenderId}/assistant/messages`) });
  const ask = useMutation({
    mutationFn: (text: string) => api<AssistantMessage[]>(`/api/v1/tenders/${tenderId}/assistant/messages`, { method: "POST", body: { question: text } }),
    onSuccess: (msgs) => {
      qc.setQueryData<AssistantMessage[]>(key, (old) => [...(old ?? []), ...msgs]);
      setQuestion("");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "The assistant could not answer."),
  });
  const clear = async () => {
    await api(`/api/v1/tenders/${tenderId}/assistant/messages`, { method: "DELETE" });
    qc.setQueryData(key, []);
    toast.success("Conversation cleared");
  };
  useEffect(() => {
    // Block body on purpose: newer browsers return a Promise from scrollIntoView, which must not become an effect cleanup.
    void endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [q.data?.length, ask.isPending]);

  const submit = (text: string) => {
    const t = text.trim();
    if (t.length >= 2 && !ask.isPending) ask.mutate(t);
  };

  return (
    <div className="space-y-4">
      <AIRequiredNotice />
      <Card
        title="Tender research assistant"
        description="Answers use only this tender's documents and project data. Your conversation is private to you."
        actions={
          q.data && q.data.length > 0 ? (
            <ConfirmButton
              title="Clear conversation?"
              description="Your messages with the assistant for this tender will be deleted."
              confirmLabel="Clear"
              onConfirm={clear}
              trigger={(open) => <Button variant="ghost" size="sm" onClick={open}><Eraser className="h-4 w-4" /> Clear</Button>}
            />
          ) : undefined
        }
      >
        <div className="flex h-[min(60vh,560px)] flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto pr-1" aria-live="polite">
            {q.isLoading ? (
              <LoadingBlock rows={3} />
            ) : q.isError ? (
              <ErrorState error={q.error} onRetry={() => q.refetch()} />
            ) : q.data!.length === 0 ? (
              <div className="py-6 text-center">
                <Bot className="mx-auto h-8 w-8 text-slate-300" />
                <p className="mt-2 text-sm text-muted">Ask a question about this tender, or try one of these:</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} disabled={!ai.data?.configured || ask.isPending} onClick={() => submit(s)} className="rounded-full border border-line bg-white px-3 py-1.5 text-xs hover:border-accent-600 hover:text-accent-700 disabled:opacity-50">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              q.data!.map((m) => (
                <div key={m.id} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}>
                  <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-navy-900 text-white" : "bg-accent-50 text-accent-700")}>
                    {m.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </div>
                  <div className={cn("max-w-[85%] rounded-xl px-4 py-3", m.role === "user" ? "bg-navy-900 text-white" : "border border-line bg-white")}>
                    <div className="prose-plain">{m.content}</div>
                    {m.role === "assistant" && (
                      <div className="mt-2 space-y-1.5 border-t border-line pt-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {m.is_demo ? <DemoBadge /> : <Badge tone="violet">{m.provider} · {m.model}</Badge>}
                          {m.supported === false && <Badge tone="amber"><CircleHelp className="h-3 w-3" /> Not supported by the documents</Badge>}
                          <span className="text-[11px] text-muted">{timeAgo(m.created_at)}</span>
                        </div>
                        {m.sources && m.sources.length > 0 && (
                          <ul className="space-y-1 text-xs text-muted">
                            {m.sources.map((s, i) => (
                              <li key={i}>
                                <span className="font-medium text-ink">{s.document}</span>
                                {s.location ? `, ${s.location}` : ""}
                                {s.quote && <span className="italic"> — “{s.quote}”</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            {ask.isPending && <p className="pl-11 text-sm text-muted">Thinking…</p>}
            <div ref={endRef} />
          </div>
          <form
            className="mt-4 flex gap-2 border-t border-line pt-4"
            onSubmit={(e) => {
              e.preventDefault();
              submit(question);
            }}
          >
            <Textarea
              aria-label="Your question"
              rows={2}
              className="min-h-0"
              placeholder={ai.data?.configured ? "Ask about requirements, risks, deadlines…" : "AI is not configured"}
              disabled={!ai.data?.configured}
              value={question}
              maxLength={4000}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit(question);
                }
              }}
            />
            <Button type="submit" className="self-end" aria-label="Send question" loading={ask.isPending} disabled={!ai.data?.configured || question.trim().length < 2}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}
