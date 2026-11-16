import * as DM from "@radix-ui/react-dropdown-menu";
import {
  BarChart3,
  Building2,
  ChevronDown,
  FileDown,
  FileStack,
  FlaskConical,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { useAIStatus } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { DemoDataBanner } from "./DemoDataBanner";
import { ErrorBoundary } from "./ErrorBoundary";
import { Spinner } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/tenders", label: "Tenders", icon: FileStack },
  { to: "/tasks", label: "Tasks", icon: ListChecks },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/exports", label: "Export Centre", icon: FileDown },
  { to: "/company", label: "Company Profile", icon: Building2 },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Logo({ dark = true }: { dark?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5" aria-label="TenderPilot AI home">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="7" fill={dark ? "#172a4f" : "#0f1f3d"} />
        <path d="M9 22 L16 8 L23 22 L16 18 Z" fill="#2dd4bf" />
      </svg>
      <span className={cn("text-[15px] font-semibold tracking-tight", dark ? "text-white" : "text-ink")}>
        TenderPilot <span className="text-accent-500">AI</span>
      </span>
    </Link>
  );
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-1 flex-col gap-0.5 px-3" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
              isActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white",
            )
          }
        >
          <Icon className="h-4 w-4" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function AIIndicator() {
  const { data } = useAIStatus();
  if (!data) return null;
  const label = data.is_demo ? "Demo mode" : data.configured ? `${data.provider} · ${data.model}` : "AI not configured";
  return (
    <Link
      to="/settings?tab=ai"
      className={cn(
        "mx-3 mb-3 flex items-center gap-2 rounded-lg px-3 py-2 text-xs",
        data.is_demo ? "bg-amber-400/10 text-amber-200" : data.configured ? "bg-accent-500/10 text-accent-100" : "bg-white/5 text-slate-400",
      )}
      title="AI provider status"
    >
      {data.is_demo ? <FlaskConical className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
      <span className="truncate">{label}</span>
    </Link>
  );
}

function UserMenu() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  if (!me) return null;
  const initials = me.full_name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <DM.Root>
      <DM.Trigger className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-navy-900 text-xs font-semibold text-white">{initials}</span>
        <span className="hidden min-w-0 sm:block">
          <span className="block truncate text-[13px] font-medium text-ink">{me.full_name}</span>
          <span className="block truncate text-[11px] text-muted">{me.organization.name}</span>
        </span>
        <ChevronDown className="h-4 w-4 text-muted" />
      </DM.Trigger>
      <DM.Portal>
        <DM.Content align="end" sideOffset={6} className="z-50 min-w-[220px] rounded-xl border border-line bg-white p-1.5 shadow-lg">
          <div className="px-2.5 py-2">
            <div className="text-sm font-medium text-ink">{me.full_name}</div>
            <div className="text-xs text-muted">{me.email}</div>
            <div className="mt-1 text-[11px] uppercase tracking-wide text-muted">{me.role}</div>
          </div>
          <DM.Separator className="my-1 h-px bg-line" />
          <DM.Item onSelect={() => navigate("/settings")} className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-slate-100">
            <Settings className="h-4 w-4" /> Account settings
          </DM.Item>
          <DM.Item
            onSelect={async () => {
              await logout();
              navigate("/login");
            }}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm text-red-600 outline-none data-[highlighted]:bg-red-50"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </DM.Item>
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-full">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col bg-navy-900 lg:flex">
        <div className="flex h-16 items-center px-5">
          <Logo />
        </div>
        <SidebarNav />
        <AIIndicator />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-navy-950/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-navy-900 shadow-xl">
            <div className="flex h-16 items-center justify-between px-5">
              <Logo />
              <button className="rounded-md p-1.5 text-slate-300 hover:bg-white/10" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
                <X className="h-5 w-5" />
              </button>
            </div>
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
            <AIIndicator />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
        <DemoDataBanner />
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-md p-2 text-muted hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
            <Menu className="h-5 w-5" />
          </button>
          <div className="lg:hidden">
            <Logo dark={false} />
          </div>
          <div className="flex-1" />
          <UserMenu />
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <ErrorBoundary resetKey={location.pathname + location.search}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

export function RequireAuth() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading)
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <AppShell />;
}
