import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

interface ServerInfo {
  status: string;
  version: string;
  ephemeral_data?: boolean;
}

/** Permanent warning shown when the server runs without a persistent database (EPHEMERAL_DEMO=true). */
export function DemoDataBanner() {
  const { data } = useQuery({
    queryKey: ["server-info"],
    queryFn: () => api<ServerInfo>("/api/v1/health", { auth: false }),
    staleTime: 5 * 60_000,
    retry: false,
  });
  if (!data?.ephemeral_data) return null;
  return (
    <div role="status" className="flex items-start gap-2 bg-amber-100 px-4 py-2 text-[13px] text-amber-950 sm:items-center sm:justify-center">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 sm:mt-0" aria-hidden />
      <span>
        <strong>Demo deployment:</strong> data is temporary and is deleted whenever the server restarts or sleeps. Do not upload confidential documents.
      </span>
    </div>
  );
}
