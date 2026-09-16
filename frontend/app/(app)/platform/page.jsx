"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Building2, CreditCard, FileCheck2, Lock, ShieldCheck, Timer, UsersRound } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { registration } from "@/lib/api";
import { usePlatformRoleLabel } from "@/components/PlatformShell";
import { Badge, Card, PageHeader } from "@/components/ui/kit";

function MetricCard({ href, icon: Icon, value, title, hint }) {
  return <Link href={href}><Card className="h-full p-6 transition-transform hover:-translate-y-0.5"><Icon className="text-accent" /><div className="mt-5 text-3xl font-bold tabular-nums">{value ?? "…"}</div><h2 className="mt-2 font-display text-base font-semibold">{title}</h2><p className="mt-1 text-sm text-muted">{hint}</p></Card></Link>;
}

export default function PlatformPage() {
  const { user } = useAuth();
  const { t, language } = useI18n();
  const roleLabel = usePlatformRoleLabel();
  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  // Unknown role names (e.g. "Django superuser") fall back to the raw label.
  const memberRole = (name) => {
    if (!name) return "";
    const label = t(`platformTeam.roles.${name}`);
    return label.startsWith("platformTeam.") ? name : label;
  };
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!user?.is_platform_admin) return;
    registration.overview().then((response) => setOverview(response.data)).catch(() => setError(t("platform.loadError")));
  }, [t, user?.is_platform_admin]);
  if (!user?.is_platform_admin) return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("shell.noAccessBody", { module: t("nav.platform") })}</p></Card>;
  const counts = overview?.counts;
  const attention = overview?.registration_attention || [];
  const expiring = overview?.expiring_subscriptions || [];
  // Only present for members who may see the team (platform.team.view).
  const team = overview?.team;
  return <div>
    <PageHeader title={t("platform.title")} subtitle={t("platform.subtitle")} actions={<Badge tone="accent"><ShieldCheck size={14} /> {roleLabel}</Badge>} />
    {error && <p role="alert" className="mb-5 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}
    <Card className="mb-5 border-accent/25 p-5">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent"><ShieldCheck size={20} /></span>
          <div>
            <h2 className="font-display font-semibold">{t("platform.ownerCreationTitle")}</h2>
            <p className="mt-1 max-w-3xl text-sm text-muted">{t("platform.ownerCreationHint")}</p>
          </div>
        </div>
        <Link href="/platform-registrations" className="shrink-0 rounded-control bg-accent px-4 py-2 text-center text-sm font-semibold text-white">{t("platform.createOwnerAction")}</Link>
      </div>
    </Card>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard href="/platform-registrations" icon={FileCheck2} value={counts?.registration_attention} title={t("platform.registrationAttention")} hint={t("platform.registrationAttentionHint")} />
      <MetricCard href="/platform-subscriptions" icon={CreditCard} value={counts?.pending_payments} title={t("platform.pendingPaymentsTitle")} hint={t("platform.pendingPaymentsHint")} />
      <MetricCard href="/platform-subscriptions" icon={Building2} value={counts?.provisioned_companies} title={t("platform.provisionedCompanies")} hint={t("platform.provisionedCompaniesHint")} />
      <MetricCard href="/platform-subscriptions" icon={Timer} value={counts?.expiring_within_7_days} title={t("platform.expiringSoon")} hint={t("platform.expiringSoonHint")} />
    </div>
    <div className="mt-7 grid gap-5 lg:grid-cols-2">
      <Card className="p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-display text-lg font-semibold">{t("platform.registrationQueue")}</h2><Link href="/platform-registrations" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">{t("platform.openQueue")}<ArrowRight size={15} /></Link></div>{attention.length ? <div className="mt-4 divide-y divide-line">{attention.map((row) => <div key={row.id} className="py-3"><div className="font-medium">{row.company_name}</div><div className="mt-1 text-sm text-muted">{row.contact_name} · {row.email}</div><Badge tone={row.status === "approved" ? "ok" : "warn"}>{t(`platformRegistration.status${row.status.charAt(0).toUpperCase()}${row.status.slice(1)}`)}</Badge></div>)}</div> : <p className="mt-4 text-sm text-muted">{t("platform.noRegistrationAttention")}</p>}</Card>
      {team && <Card className="p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-display text-lg font-semibold"><UsersRound size={18} className="me-2 inline text-accent" />{t("platform.teamPresence")}</h2><Link href="/platform-team" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">{t("platform.openTeam")}<ArrowRight size={15} /></Link></div><p className="mt-1 text-sm text-muted">{t("platform.teamPresenceHint")}</p><div className="mt-4 divide-y divide-line">{team.map((row) => <div key={row.id} className="flex items-center justify-between gap-4 py-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><Link href={`/platform-team/member/?id=${row.id}`} className="font-medium hover:text-accent hover:underline">{row.full_name || row.email}</Link>{row.online && <Badge tone="ok"><span className="me-1 inline-block h-2 w-2 rounded-full bg-ok" />{t("platformTeam.online")}</Badge>}</div><div className="mt-1 truncate text-sm text-muted">{row.email}{row.role_name && <> · {memberRole(row.role_name)}</>}</div></div><div className="shrink-0 text-end text-xs text-muted">{row.online ? "" : row.last_seen_at ? t("platformTeam.lastSeen", { date: fmt(row.last_seen_at) }) : t("platformTeam.neverSignedIn")}</div></div>)}</div></Card>}
      <Card className="p-5"><h2 className="font-display text-lg font-semibold">{t("platform.expiringQueue")}</h2>{expiring.length ? <div className="mt-4 divide-y divide-line">{expiring.map((row) => <div key={row.id} className="flex items-center justify-between gap-4 py-3"><div><div className="font-medium">{row.company_name}</div><div className="mt-1 text-sm text-muted">{row.status}</div></div><time className="text-sm text-muted">{new Date(row.ends_at).toLocaleDateString()}</time></div>)}</div> : <p className="mt-4 text-sm text-muted">{t("platform.noExpiringSubscriptions")}</p>}</Card>
    </div>
  </div>;
}
