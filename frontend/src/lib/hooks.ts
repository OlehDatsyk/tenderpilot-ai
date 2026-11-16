import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "./api";
import type { AIStatus, Member } from "./types";

export function useAIStatus() {
  return useQuery({ queryKey: ["ai-status"], queryFn: () => api<AIStatus>("/api/v1/ai/status"), staleTime: 30_000 });
}

export function useMembers() {
  return useQuery({ queryKey: ["members"], queryFn: () => api<Member[]>("/api/v1/organization/members"), staleTime: 60_000 });
}

/** Mutation helper: shows a toast on success/error and invalidates the given query keys. */
export function useApiMutation<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  opts: { success?: string | ((r: TResult) => string); invalidate?: QueryKey[]; onSuccess?: (r: TResult, vars: TVars) => void } = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result, vars) => {
      opts.invalidate?.forEach((key) => qc.invalidateQueries({ queryKey: key }));
      if (opts.success) toast.success(typeof opts.success === "function" ? opts.success(result) : opts.success);
      opts.onSuccess?.(result, vars);
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Something went wrong."),
  });
}
