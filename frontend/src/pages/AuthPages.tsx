import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { DemoDataBanner } from "@/components/DemoDataBanner";
import { Logo } from "@/components/layout";
import { Button, Field, Input, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function AuthLayout({ title, subtitle, children }: { title: string; subtitle: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
    <DemoDataBanner />
    <div className="grid flex-1 lg:grid-cols-[1fr_1.1fr]">
      <div className="hidden flex-col justify-between bg-navy-900 p-10 text-white lg:flex">
        <Logo />
        <div className="max-w-md">
          <h2 className="text-2xl font-semibold leading-snug">Win more of the right tenders, with less effort.</h2>
          <ul className="mt-6 space-y-3 text-sm text-slate-300">
            {[
              "Extract requirements with verifiable source references",
              "Track compliance and bid/no-bid decisions in one place",
              "Draft proposals that never invent company facts",
            ].map((t) => (
              <li key={t} className="flex gap-2.5">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent-500" /> {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="flex items-center gap-2 text-xs text-slate-400">
          <ShieldCheck className="h-4 w-4" /> AI output is always labelled and must be verified by your team.
        </p>
      </div>
      <div className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Logo dark={false} />
          </div>
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
    </div>
  );
}

const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (isAuthenticated) return <Navigate to={from} replace />;

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await login(values.email, values.password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign in failed.");
    }
  });

  return (
    <AuthLayout title="Sign in" subtitle={<>New to TenderPilot? <Link className="font-medium text-accent-700 hover:underline" to="/register">Create an account</Link></>}>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error && <Notice tone="red">{error}</Notice>}
        <Field label="Email" htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
        </Field>
        <Button type="submit" className="w-full justify-center" loading={formState.isSubmitting}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}

const registerSchema = z
  .object({
    full_name: z.string().trim().min(1, "Enter your name").max(200),
    email: z.string().trim().email("Enter a valid email address"),
    organization_name: z.string().trim().max(200).optional(),
    password: z
      .string()
      .min(10, "Use at least 10 characters")
      .max(128)
      .regex(/[A-Za-z]/, "Include at least one letter")
      .regex(/\d/, "Include at least one number"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });
type RegisterValues = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const { register: registerUser, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const invite = params.get("invite") ?? undefined;
  const [error, setError] = useState<string | null>(null);
  const invitation = useQuery({
    queryKey: ["invite", invite],
    queryFn: () => api<{ organization_name: string; email: string; role: string }>(`/api/v1/auth/invitations/${encodeURIComponent(invite!)}`, { auth: false }),
    enabled: !!invite,
    retry: false,
  });
  const { register, handleSubmit, formState } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    values: invitation.data ? ({ email: invitation.data.email } as RegisterValues) : undefined,
    resetOptions: { keepDirtyValues: true },
  });

  if (isAuthenticated) return <Navigate to="/" replace />;

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await registerUser({
        email: v.email,
        password: v.password,
        full_name: v.full_name,
        organization_name: invite ? undefined : v.organization_name || undefined,
        invitation_token: invite,
      });
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registration failed.");
    }
  });

  return (
    <AuthLayout title={invite ? "Join your team" : "Create your account"} subtitle={<>Already have an account? <Link className="font-medium text-accent-700 hover:underline" to="/login">Sign in</Link></>}>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {invite && invitation.isError && <Notice tone="red">This invitation link is invalid or has expired.</Notice>}
        {invitation.data && (
          <Notice tone="teal">
            You have been invited to join <strong>{invitation.data.organization_name}</strong> as {invitation.data.role}.
          </Notice>
        )}
        {error && <Notice tone="red">{error}</Notice>}
        <Field label="Full name" htmlFor="full_name" error={formState.errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" {...register("full_name")} />
        </Field>
        <Field label="Work email" htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" readOnly={!!invitation.data} {...register("email")} />
        </Field>
        {!invite && (
          <Field label="Organisation name" htmlFor="organization_name" hint="You can change this later." error={formState.errors.organization_name?.message}>
            <Input id="organization_name" autoComplete="organization" {...register("organization_name")} />
          </Field>
        )}
        <Field label="Password" htmlFor="password" hint="At least 10 characters, with a letter and a number." error={formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="new-password" {...register("password")} />
        </Field>
        <Field label="Confirm password" htmlFor="confirm" error={formState.errors.confirm?.message}>
          <Input id="confirm" type="password" autoComplete="new-password" {...register("confirm")} />
        </Field>
        <Button type="submit" className="w-full justify-center" loading={formState.isSubmitting} disabled={!!invite && invitation.isError}>
          Create account
        </Button>
      </form>
    </AuthLayout>
  );
}
