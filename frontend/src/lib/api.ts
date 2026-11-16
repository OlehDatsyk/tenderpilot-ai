/**
 * Minimal typed API client.
 * - Access token is sent as a Bearer header (no cookies => no CSRF surface).
 * - On 401 the client performs a single-flight refresh-token rotation and retries once.
 */

function resolveBase(): string {
  const raw = (import.meta.env.VITE_API_URL as string | undefined)?.trim() ?? "";
  if (!raw) return ""; // same origin (Vite dev proxy or reverse proxy)
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  return withScheme.replace(/\/+$/, "");
}

export const API_BASE = resolveBase();
const SESSION_KEY = "tp.session";

export interface Session {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const sessionStore = {
  get(): Session | null {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      return raw ? (JSON.parse(raw) as Session) : null;
    } catch {
      return null;
    }
  },
  set(s: Session) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(s));
  },
  clear() {
    localStorage.removeItem(SESSION_KEY);
  },
};

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const current = sessionStore.get();
  if (!current?.refresh_token) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: current.refresh_token }),
        });
        if (!res.ok) return false;
        sessionStore.set((await res.json()) as Session);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

function endSession() {
  sessionStore.clear();
  window.dispatchEvent(new Event("tp:logout"));
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) return data.detail.map((d: { msg?: string }) => d.msg).join("; ");
  } catch {
    /* not JSON */
  }
  if (res.status === 429) return "Too many requests. Please wait a moment and try again.";
  if (res.status >= 500) return "The server encountered an error. Please try again.";
  return `Request failed (${res.status}).`;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  auth?: boolean;
  signal?: AbortSignal;
}

async function rawRequest(path: string, opts: RequestOptions, retry = true): Promise<Response> {
  const headers: Record<string, string> = {};
  const session = sessionStore.get();
  if (opts.auth !== false && session) headers.Authorization = `Bearer ${session.access_token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: opts.method ?? "GET", headers, body, signal: opts.signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Cannot reach the TenderPilot API. Check your connection or that the backend is running.");
  }
  if (res.status === 401 && opts.auth !== false && session) {
    if (retry && (await refreshSession())) return rawRequest(path, opts, false);
    endSession(); // refresh failed, or the refreshed token was rejected too
  }
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await rawRequest(path, opts);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await rawRequest(path, {});
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  const name = match ? decodeURIComponent(match[1] ?? match[2]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function qs(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
