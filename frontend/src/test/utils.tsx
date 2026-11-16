import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "@/lib/auth";

export function renderWithProviders(ui: ReactElement, { route = "/" } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

type Handler = (url: string, init: RequestInit) => { status?: number; body?: unknown } | undefined;

/** Install a fetch mock routed by "METHOD path" prefixes. Returns the vi.fn for call assertions. */
export function mockFetch(routes: Record<string, Handler | { status?: number; body?: unknown }>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init.method ?? "GET").toUpperCase();
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const key = Object.keys(routes)
      .filter((k) => {
        const [m, p] = k.split(" ");
        return m === method && path.startsWith(p);
      })
      .sort((a, b) => b.length - a.length)[0];
    if (!key) return new Response(JSON.stringify({ detail: `No mock for ${method} ${path}` }), { status: 404 });
    const route = routes[key];
    const res = typeof route === "function" ? route(path, init) : route;
    const status = res?.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(res?.body ?? {}), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
