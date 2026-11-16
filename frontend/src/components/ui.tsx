import { AlertTriangle, Inbox, Loader2, RefreshCw } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "icon";

const variants: Record<Variant, string> = {
  primary: "bg-navy-900 text-white hover:bg-navy-800 shadow-sm",
  secondary: "bg-accent-600 text-white hover:bg-accent-700 shadow-sm",
  outline: "border border-line bg-white text-ink hover:bg-slate-50 shadow-xs",
  ghost: "text-muted hover:bg-slate-100 hover:text-ink",
  danger: "bg-red-600 text-white hover:bg-red-700 shadow-sm",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-9 px-4 text-sm gap-2",
  icon: "h-8 w-8 justify-center",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, disabled, className, children, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(
        "inline-flex shrink-0 items-center rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-55",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("input", className)} {...props} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn("input min-h-[90px] resize-y leading-relaxed", className)} {...props} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...props }, ref) {
  return (
    <select ref={ref} className={cn("input appearance-auto pr-8", className)} {...props}>
      {children}
    </select>
  );
});

export function Field({ label, htmlFor, hint, error, children, className }: { label: string; htmlFor?: string; hint?: string; error?: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="field-label">
        {label}
      </label>
      {children}
      {error ? <p className="field-error" role="alert">{error}</p> : hint ? <p className="field-hint">{hint}</p> : null}
    </div>
  );
}

const tones = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  teal: "bg-accent-50 text-accent-700 ring-accent-100",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  navy: "bg-navy-900 text-white ring-navy-900",
};
export type Tone = keyof typeof tones;

export function Badge({ tone = "slate", children, className, title }: { tone?: Tone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Card({ children, className, title, actions, description }: { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode; description?: ReactNode }) {
  return (
    <section className={cn("card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-slate-200/70", className)} />;
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin text-muted", className)} aria-label="Loading" />;
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-white/60 px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-slate-100 p-3 text-muted">{icon ?? <Inbox className="h-5 w-5" />}</div>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 sm:flex-row sm:items-center">
      <AlertTriangle className="h-5 w-5 shrink-0" />
      <p className="flex-1">{message}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </Button>
      )}
    </div>
  );
}

export function Notice({ tone = "amber", icon, children, className }: { tone?: "amber" | "blue" | "red" | "teal"; icon?: ReactNode; children: ReactNode; className?: string }) {
  const map = {
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    blue: "border-blue-200 bg-blue-50 text-blue-900",
    red: "border-red-200 bg-red-50 text-red-800",
    teal: "border-accent-100 bg-accent-50 text-accent-700",
  };
  return (
    <div className={cn("flex gap-2.5 rounded-lg border px-3.5 py-2.5 text-[13px] leading-relaxed", map[tone], className)}>
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function PageHeader({ title, description, actions, eyebrow }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium text-muted">{eyebrow}</div>}
        <h1 className="truncate text-xl font-semibold text-ink sm:text-[22px]">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Progress({ value, className, tone = "teal" }: { value: number; className?: string; tone?: "teal" | "navy" }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-slate-100", className)} role="progressbar" aria-valuenow={v} aria-valuemin={0} aria-valuemax={100}>
      <div className={cn("h-full rounded-full transition-all", tone === "teal" ? "bg-accent-600" : "bg-navy-700")} style={{ width: `${v}%` }} />
    </div>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between text-xs font-medium text-muted">
        <span>{label}</span>
        {icon && <span className="text-slate-400">{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}
