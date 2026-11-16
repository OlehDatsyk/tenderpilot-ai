import { zodResolver } from "@hookform/resolvers/zod";
import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { Copy, KeyRound, Lock, UserMinus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { DemoBadge } from "@/components/badges";
import { ConfirmButton } from "@/components/dialog";
import { Badge, Button, Card, ErrorState, Field, Input, LoadingBlock, Notice, PageHeader, Select } from "@/components/ui";
import { api, sessionStore, type Session } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApiMutation, useMembers } from "@/lib/hooks";
import { PROVIDERS } from "@/lib/labels";
import type { AISettings, Invitation } from "@/lib/types";
import { formatDate } from "@/lib/utils";

function ProfileTab() {
  const { me, refreshMe } = useAuth();
  const [name, setName] = useState(me?.full_name ?? "");
  const [title, setTitle] = useState(me?.job_title ?? "");
  const save = useApiMutation(() => api("/api/v1/auth/me", { method: "PATCH", body: { full_name: name, job_title: title } }), {
    success: "Profile updated",
    invalidate: [["members"]],
    onSuccess: () => refreshMe(),
  });
  return (
    <Card title="Your profile">
      <form className="grid max-w-xl gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined); }}>
        <Field label="Email" htmlFor="pf-email" hint="Email changes are not supported in this release."><Input id="pf-email" value={me?.email ?? ""} disabled /></Field>
        <Field label="Full name" htmlFor="pf-name"><Input id="pf-name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Job title" htmlFor="pf-title"><Input id="pf-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></Field>
        <div><Button type="submit" loading={save.isPending} disabled={!name.trim()}>Save</Button></div>
      </form>
    </Card>
  );
}

const pwSchema = z
  .object({
    current_password: z.string().min(1, "Required"),
    new_password: z.string().min(10, "At least 10 characters").max(128).regex(/[A-Za-z]/, "Include a letter").regex(/\d/, "Include a number"),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });

function SecurityTab() {
  const { register, handleSubmit, formState, reset } = useForm<z.infer<typeof pwSchema>>({ resolver: zodResolver(pwSchema) });
  const change = useApiMutation(
    (v: z.infer<typeof pwSchema>) => api<Session>("/api/v1/auth/change-password", { method: "POST", body: { current_password: v.current_password, new_password: v.new_password } }),
    {
      success: "Password changed. Other sessions have been signed out.",
      onSuccess: (s) => {
        sessionStore.set(s);
        reset();
      },
    },
  );
  const e = formState.errors;
  return (
    <Card title="Change password" description="Changing your password signs out all other sessions.">
      <form className="grid max-w-xl gap-4" onSubmit={handleSubmit((v) => change.mutate(v))} noValidate>
        <Field label="Current password" htmlFor="pw-cur" error={e.current_password?.message}><Input id="pw-cur" type="password" autoComplete="current-password" {...register("current_password")} /></Field>
        <Field label="New password" htmlFor="pw-new" error={e.new_password?.message} hint="At least 10 characters with a letter and a number."><Input id="pw-new" type="password" autoComplete="new-password" {...register("new_password")} /></Field>
        <Field label="Confirm new password" htmlFor="pw-conf" error={e.confirm?.message}><Input id="pw-conf" type="password" autoComplete="new-password" {...register("confirm")} /></Field>
        <div><Button type="submit" loading={change.isPending}><Lock className="h-4 w-4" /> Change password</Button></div>
      </form>
    </Card>
  );
}

function TeamTab() {
  const { me, refreshMe } = useAuth();
  const isAdmin = me?.role === "owner" || me?.role === "admin";
  const members = useMembers();
  const invites = useQuery({ queryKey: ["invitations"], queryFn: () => api<Invitation[]>("/api/v1/organization/invitations"), enabled: isAdmin });
  const [orgName, setOrgName] = useState(me?.organization.name ?? "");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [link, setLink] = useState<string | null>(null);

  const rename = useApiMutation(() => api("/api/v1/organization", { method: "PATCH", body: { name: orgName } }), { success: "Organisation renamed", onSuccess: () => refreshMe() });
  const invite = useApiMutation(() => api<Invitation>("/api/v1/organization/invitations", { method: "POST", body: { email: inviteEmail, role: inviteRole } }), {
    success: "Invitation created",
    invalidate: [["invitations"]],
    onSuccess: (inv) => {
      setLink(`${window.location.origin}/register?invite=${encodeURIComponent(inv.token ?? "")}`);
      setInviteEmail("");
    },
  });
  const revoke = useApiMutation((id: string) => api(`/api/v1/organization/invitations/${id}`, { method: "DELETE" }), { success: "Invitation revoked", invalidate: [["invitations"]] });
  const setRole = useApiMutation(({ id, role }: { id: string; role: string }) => api(`/api/v1/organization/members/${id}`, { method: "PATCH", body: { role } }), { success: "Role updated", invalidate: [["members"]] });
  const removeMember = useApiMutation((id: string) => api(`/api/v1/organization/members/${id}`, { method: "DELETE" }), { success: "Member removed", invalidate: [["members"]] });

  return (
    <div className="space-y-5">
      <Card title="Organisation">
        <form className="flex max-w-xl flex-col gap-2 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); rename.mutate(undefined); }}>
          <Field label="Organisation name" htmlFor="org-name" className="flex-1"><Input id="org-name" value={orgName} disabled={!isAdmin} onChange={(e) => setOrgName(e.target.value)} /></Field>
          {isAdmin && <Button type="submit" loading={rename.isPending} disabled={!orgName.trim() || orgName === me?.organization.name}>Rename</Button>}
        </form>
      </Card>
      <Card title="Members" description="All members of your organisation can see and work on its tenders.">
        {members.isLoading ? <LoadingBlock /> : members.isError ? <ErrorState error={members.error} /> : (
          <div className="-mx-5 -my-5 overflow-x-auto">
            <table className="table-base min-w-[560px]">
              <thead><tr><th>Name</th><th>Role</th><th>Joined</th><th /></tr></thead>
              <tbody>
                {members.data!.map((m) => (
                  <tr key={m.user_id}>
                    <td><div className="font-medium">{m.full_name}</div><div className="text-xs text-muted">{m.email}</div></td>
                    <td>
                      {isAdmin && m.role !== "owner" && m.user_id !== me?.id ? (
                        <Select aria-label={`Role for ${m.full_name}`} className="w-32 py-1.5" value={m.role} onChange={(e) => setRole.mutate({ id: m.user_id, role: e.target.value })}>
                          <option value="admin">Admin</option>
                          <option value="member">Member</option>
                        </Select>
                      ) : (
                        <Badge tone={m.role === "owner" ? "navy" : "slate"}>{m.role}</Badge>
                      )}
                    </td>
                    <td className="text-muted">{formatDate(m.joined_at)}</td>
                    <td className="text-right">
                      {isAdmin && m.role !== "owner" && m.user_id !== me?.id && (
                        <ConfirmButton title="Remove member?" description={`${m.full_name} will immediately lose access to your organisation's data.`} confirmLabel="Remove" onConfirm={() => removeMember.mutateAsync(m.user_id)} trigger={(open) => (
                          <Button size="sm" variant="ghost" className="text-red-600 hover:bg-red-50" onClick={open}><UserMinus className="h-4 w-4" /> Remove</Button>
                        )} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {isAdmin && (
        <Card title="Invitations" description="No email is sent — copy the invitation link and share it securely. Links expire after 7 days.">
          <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); invite.mutate(undefined); }}>
            <Field label="Email" htmlFor="inv-email" className="flex-1"><Input id="inv-email" type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} /></Field>
            <Field label="Role" htmlFor="inv-role"><Select id="inv-role" value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}><option value="member">Member</option><option value="admin">Admin</option></Select></Field>
            <Button type="submit" loading={invite.isPending} disabled={!inviteEmail.includes("@")}>Create invitation</Button>
          </form>
          {link && (
            <Notice tone="teal" className="mt-4">
              <div className="mb-1 font-medium">Invitation link (shown once):</div>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all text-xs">{link}</code>
                <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(link).then(() => toast.success("Link copied"), () => toast.error("Copy failed"))}><Copy className="h-3.5 w-3.5" /> Copy</Button>
              </div>
            </Notice>
          )}
          {invites.data && invites.data.length > 0 && (
            <ul className="mt-4 divide-y divide-line text-sm">
              {invites.data.map((i) => {
                const state = i.accepted_at ? "accepted" : i.revoked_at ? "revoked" : new Date(i.expires_at) < new Date() ? "expired" : "pending";
                return (
                  <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span>{i.email} <span className="text-xs text-muted">· {i.role} · expires {formatDate(i.expires_at)}</span></span>
                    <span className="flex items-center gap-2">
                      <Badge tone={state === "pending" ? "blue" : state === "accepted" ? "green" : "slate"}>{state}</Badge>
                      {state === "pending" && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(i.id)}>Revoke</Button>}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}

function AITab() {
  const { me } = useAuth();
  const isAdmin = me?.role === "owner" || me?.role === "admin";
  const q = useQuery({ queryKey: ["ai-settings"], queryFn: () => api<AISettings>("/api/v1/organization/ai-settings") });
  const [provider, setProvider] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const save = useApiMutation(
    (clearKey: boolean) =>
      api<AISettings>("/api/v1/organization/ai-settings", {
        method: "PUT",
        body: { provider: provider ?? q.data!.provider, model: model ?? q.data!.model, ...(clearKey ? { api_key: "" } : key ? { api_key: key } : {}) },
      }),
    { success: "AI settings saved", invalidate: [["ai-settings"], ["ai-status"]], onSuccess: () => setKey("") },
  );
  if (q.isLoading) return <LoadingBlock />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data!;
  const p = provider ?? s.provider;
  const eff = s.effective;
  const needsKey = ["openai", "anthropic", "gemini"].includes(p);

  return (
    <div className="space-y-5">
      <Card title="Current status">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {eff.is_demo ? <DemoBadge /> : eff.configured ? <Badge tone="green">Configured</Badge> : <Badge tone="slate">Not configured</Badge>}
          <span>Provider: <strong>{eff.provider}</strong></span>
          {eff.model && <span>· Model: <strong>{eff.model}</strong></span>}
          <span className="text-muted">· Source: {eff.source === "organization" ? "organisation settings" : "server environment"}</span>
        </div>
        {eff.message && <p className="mt-2 text-sm text-muted">{eff.message}</p>}
      </Card>
      <Card title="Provider configuration" description={isAdmin ? "Organisation-level settings override the server default." : "Only owners and admins can change AI settings."}>
        <form className="grid max-w-2xl gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(false); }}>
          <Field label="Provider" htmlFor="ai-provider" hint={`Server default: ${s.server_default_provider}`}>
            <Select id="ai-provider" value={p} disabled={!isAdmin} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
            </Select>
          </Field>
          {p === "demo" && <Notice tone="amber">Demo mode uses a deterministic keyword heuristic. Its output is always labelled as demo content and must not be treated as AI analysis.</Notice>}
          {needsKey && (
            <>
              <Field label="Model" htmlFor="ai-model" hint={p === "anthropic" ? "Leave blank for the default (claude-opus-5-5)." : "Enter the exact model name offered by your provider account."}>
                <Input id="ai-model" value={model ?? s.model} disabled={!isAdmin} onChange={(e) => setModel(e.target.value)} placeholder={p === "anthropic" ? "claude-opus-5-5" : ""} />
              </Field>
              <Field
                label="API key"
                htmlFor="ai-key"
                hint={
                  !s.org_keys_allowed
                    ? "Storing keys is disabled on this server; the server's environment key will be used."
                    : !s.encryption_available
                      ? "ENCRYPTION_KEY is not configured on the server, so keys cannot be stored."
                      : s.api_key_stored
                        ? `A key is stored (${s.api_key_hint}). Enter a new key to replace it. Keys are encrypted and never shown again.`
                        : "Encrypted at rest and never returned to the browser. Leave blank to use the server's environment key."
                }
              >
                <Input id="ai-key" type="password" autoComplete="off" value={key} disabled={!isAdmin || !s.org_keys_allowed || !s.encryption_available} onChange={(e) => setKey(e.target.value)} placeholder={s.api_key_stored ? "••••••••" : ""} />
              </Field>
            </>
          )}
          {isAdmin && (
            <div className="flex flex-wrap gap-2">
              <Button type="submit" loading={save.isPending}><KeyRound className="h-4 w-4" /> Save AI settings</Button>
              {s.api_key_stored && <Button variant="outline" onClick={() => save.mutate(true)}>Remove stored key</Button>}
            </div>
          )}
        </form>
      </Card>
      <Notice tone="blue">
        Uploaded tender documents are sent to the selected provider for analysis. Document content is wrapped as untrusted data, and instructions inside documents are never followed. Check your provider's data-processing terms before uploading confidential material.
      </Notice>
    </div>
  );
}

const TABS = [
  { id: "profile", label: "Profile" },
  { id: "security", label: "Security" },
  { id: "team", label: "Organisation & team" },
  { id: "ai", label: "AI provider" },
];

export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "profile";
  return (
    <>
      <PageHeader title="Settings" description="Manage your account, your organisation and AI configuration." />
      <Tabs.Root value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <Tabs.List className="mb-5 flex gap-1 overflow-x-auto border-b border-line" aria-label="Settings sections">
          {TABS.map((t) => (
            <Tabs.Trigger key={t.id} value={t.id} className="-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2.5 text-sm font-medium text-muted hover:text-ink data-[state=active]:border-accent-600 data-[state=active]:text-ink">
              {t.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="profile"><ProfileTab /></Tabs.Content>
        <Tabs.Content value="security"><SecurityTab /></Tabs.Content>
        <Tabs.Content value="team"><TeamTab /></Tabs.Content>
        <Tabs.Content value="ai"><AITab /></Tabs.Content>
      </Tabs.Root>
    </>
  );
}
