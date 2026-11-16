import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OriginBadge, VerifiedBadge } from "@/components/badges";
import { api, ApiError, sessionStore } from "@/lib/api";
import { LoginPage, RegisterPage } from "@/pages/AuthPages";
import { ComplianceTab } from "@/pages/tender/ComplianceTab";
import { TenderFormDialog } from "@/components/TenderForm";
import { mockFetch, renderWithProviders } from "./utils";

afterEach(() => vi.unstubAllGlobals());

const session = { access_token: "a1", refresh_token: "r1", expires_in: 900 };

describe("api client", () => {
  it("refreshes the access token once on 401 and retries", async () => {
    sessionStore.set(session);
    let calls = 0;
    const fetchMock = mockFetch({
      "GET /api/v1/tenders": (_url, init) => {
        calls += 1;
        const auth = (init.headers as Record<string, string>).Authorization;
        return auth === "Bearer a2" ? { body: { ok: true } } : { status: 401, body: { detail: "Not authenticated." } };
      },
      "POST /api/v1/auth/refresh": { body: { access_token: "a2", refresh_token: "r2", expires_in: 900 } },
    });
    await expect(api("/api/v1/tenders")).resolves.toEqual({ ok: true });
    expect(calls).toBe(2);
    expect(sessionStore.get()?.refresh_token).toBe("r2");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("ends the session when refresh fails", async () => {
    sessionStore.set(session);
    const onLogout = vi.fn();
    window.addEventListener("tp:logout", onLogout);
    mockFetch({
      "GET /api/v1/tenders": { status: 401, body: { detail: "Not authenticated." } },
      "POST /api/v1/auth/refresh": { status: 401, body: { detail: "Session expired." } },
    });
    await expect(api("/api/v1/tenders")).rejects.toBeInstanceOf(ApiError);
    expect(sessionStore.get()).toBeNull();
    expect(onLogout).toHaveBeenCalled();
    window.removeEventListener("tp:logout", onLogout);
  });

  it("surfaces the server's error detail", async () => {
    mockFetch({ "POST /api/v1/tenders": { status: 422, body: { detail: "Invalid title: Field required" } } });
    await expect(api("/api/v1/tenders", { method: "POST", body: {} })).rejects.toThrow("Invalid title: Field required");
  });
});

describe("badges", () => {
  it("distinguishes AI, demo and user-provided information", () => {
    render(
      <>
        <OriginBadge origin="ai" />
        <OriginBadge origin="demo" />
        <OriginBadge origin="manual" />
        <VerifiedBadge verified />
        <VerifiedBadge verified={false} />
      </>,
    );
    expect(screen.getByText("AI-extracted")).toBeInTheDocument();
    expect(screen.getByText("Demo")).toBeInTheDocument();
    expect(screen.getByText("User-entered")).toBeInTheDocument();
    expect(screen.getByText("Source verified")).toBeInTheDocument();
    expect(screen.getByText("Unverified")).toBeInTheDocument();
  });
});

describe("authentication pages", () => {
  it("validates the login form before calling the API", async () => {
    const fetchMock = mockFetch({});
    renderWithProviders(<LoginPage />, { route: "/login" });
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server error on failed login and stores nothing", async () => {
    mockFetch({ "POST /api/v1/auth/login": { status: 401, body: { detail: "Invalid email or password." } } });
    renderWithProviders(<LoginPage />, { route: "/login" });
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-pass-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
    expect(sessionStore.get()).toBeNull();
  });

  it("stores the session after a successful login", async () => {
    mockFetch({
      "POST /api/v1/auth/login": { body: session },
      "GET /api/v1/auth/me": { body: { id: "u1", email: "a@example.com", full_name: "A", organization: { id: "o", name: "Org" }, role: "owner" } },
    });
    renderWithProviders(<LoginPage />, { route: "/login" });
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "Correct-pass-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(sessionStore.get()?.access_token).toBe("a1"));
  });

  it("enforces password rules on registration", async () => {
    const fetchMock = mockFetch({});
    renderWithProviders(<RegisterPage />, { route: "/register" });
    await userEvent.type(screen.getByLabelText("Full name"), "Ann");
    await userEvent.type(screen.getByLabelText("Work email"), "ann@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.type(screen.getByLabelText("Confirm password"), "different");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 10 characters")).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("tender form", () => {
  it("requires a title and a valid currency", async () => {
    const fetchMock = mockFetch({});
    renderWithProviders(<TenderFormDialog open onOpenChange={() => {}} />);
    const currency = screen.getByLabelText("Currency");
    await userEvent.clear(currency);
    await userEvent.type(currency, "E1");
    await userEvent.click(screen.getByRole("button", { name: "Create tender" }));
    expect(await screen.findByText("Title is required")).toBeInTheDocument();
    expect(screen.getByText("3-letter ISO code, e.g. EUR")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits a new tender with normalised values", async () => {
    let posted: Record<string, unknown> | null = null;
    mockFetch({
      "POST /api/v1/tenders": (_u, init) => {
        posted = JSON.parse(String(init.body));
        return { status: 201, body: { id: "t1", ...posted } };
      },
    });
    const onSaved = vi.fn();
    renderWithProviders(<TenderFormDialog open onOpenChange={() => {}} onSaved={onSaved} />);
    await userEvent.type(screen.getByLabelText("Title"), "Cloud migration");
    await userEvent.type(screen.getByLabelText("Estimated value"), "1500.50");
    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "gbp");
    await userEvent.click(screen.getByRole("button", { name: "Create tender" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(posted).toMatchObject({ title: "Cloud migration", currency: "GBP", estimated_value: "1500.50", submission_deadline: null });
  });
});

describe("compliance matrix", () => {
  const req = {
    id: "r1",
    tender_id: "t1",
    document_id: null,
    analysis_run_id: "run",
    description: "Bidders must hold ISO 27001",
    category: "certification",
    is_mandatory: true,
    priority: "critical",
    source_document_name: "itt.pdf",
    source_page: 4,
    source_quote: "Bidders must hold ISO 27001",
    source_verified: true,
    origin: "ai",
    confidence: 0.9,
    response_status: "not_started",
    assignee_id: null,
    assignee_name: null,
    evidence: "",
    comments: "",
    position: 1,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  };

  it("shows provenance and updates a response status", async () => {
    const patches: unknown[] = [];
    mockFetch({
      "GET /api/v1/tenders/t1/requirements": { body: [req] },
      "GET /api/v1/tenders/t1/compliance": {
        body: { total: 1, mandatory_total: 1, by_status: { not_started: 1 }, addressed: 0, percent_complete: 0, mandatory_percent_complete: 0 },
      },
      "PATCH /api/v1/requirements/r1": (_u, init) => {
        patches.push(JSON.parse(String(init.body)));
        return { body: { ...req, response_status: "compliant" } };
      },
    });
    renderWithProviders(<ComplianceTab tenderId="t1" />);
    const row = (await screen.findByText("Bidders must hold ISO 27001")).closest("tr")!;
    expect(within(row).getByText("AI-extracted")).toBeInTheDocument();
    expect(within(row).getByText("Source verified")).toBeInTheDocument();
    expect(within(row).getByText(/itt\.pdf, p\. 4/)).toBeInTheDocument();
    await userEvent.selectOptions(within(row).getByLabelText("Response status"), "compliant");
    await waitFor(() => expect(patches).toEqual([{ response_status: "compliant" }]));
  });
});
