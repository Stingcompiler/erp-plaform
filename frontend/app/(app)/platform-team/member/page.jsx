"use client";

// One platform team member in full: profile, what the role lets them do,
// how they were invited, every change made to the account and their own
// recent actions. Reached from the team list; the id travels in the query
// string because the static export cannot have a dynamic segment.
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, Clock, KeyRound, Lock, ShieldCheck, UserRound } from "lucide-react";

import { useAuth } from "../../../providers/AuthProvider";
import { useI18n } from "../../../providers/I18nProvider";
import { platformTeam } from "@/lib/api";
import { Badge, Card, PageHeader } from "@/components/ui/kit";

function Row({ label, children }) {
  return (
    <div className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-6">
      <dt className="w-44 shrink-0 text-sm text-muted">{label}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  );
}

function Section({ icon: Icon, title, hint, children }) {
  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent"><Icon size={20} /></span>
        <div className="min-w-0 flex-1">
          <h2 className="font-display font-semibold">{title}</h2>
          {hint && <p className="mt-1 text-sm text-muted">{hint}</p>}
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </Card>
  );
}

// Turns an audit row about a member into one readable line.
function describeHistory(row, t, roleLabel) {
  const meta = row.metadata || {};
  if (row.entity_type === "PlatformInvitation") {
    if (meta.event === "accepted") return t("platformTeam.member.events.accepted");
    return t("platformTeam.member.events.reissued");
  }
  if (row.action === "create") return t("platformTeam.member.events.invited", { role: roleLabel(meta.role) });
  if (meta.role_to) {
    return t("platformTeam.member.events.roleChanged", { from: roleLabel(meta.role_from), to: roleLabel(meta.role_to) });
  }
  if (meta.is_active === false) return t("platformTeam.member.events.deactivated");
  if (meta.is_active === true) return t("platformTeam.member.events.reactivated");
  return t(`platformTeam.member.actions.${row.action}`);
}

function MemberDetail() {
  const { user } = useAuth();
  const { t, language, dir } = useI18n();
  const params = useSearchParams();
  const id = params.get("id");
  const [member, setMember] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user?.is_platform_admin || !id) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    platformTeam
      .get(id)
      .then((response) => { if (!cancelled) setMember(response.data); })
      .catch((requestError) => {
        if (cancelled) return;
        setError(t(requestError?.response?.status === 404 ? "platformTeam.member.notFound" : "platformTeam.member.loadError"));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, t, user?.is_platform_admin]);

  const roleLabel = (name) => {
    if (!name) return "";
    const label = t(`platformTeam.roles.${name}`);
    return label.startsWith("platformTeam.") ? name : label;
  };
  // Capability codes contain dots, so they cannot be part of a translation
  // key path; read the whole map and index it.
  const capabilityNames = t("platformTeam.capabilityNames");
  const capabilityLabel = (code) =>
    (capabilityNames && typeof capabilityNames === "object" && capabilityNames[code]) || code;
  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  const BackIcon = dir === "rtl" ? ArrowRight : ArrowLeft;
  const back = (
    <Link href="/platform-team" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">
      <BackIcon size={15} />{t("platformTeam.member.back")}
    </Link>
  );

  if (!user?.is_platform_admin) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">{t("platformTeam.noAccess")}</p>
      </Card>
    );
  }
  if (loading) return <Card className="p-8 text-center text-muted">{t("common.loading")}</Card>;
  if (error || !member) {
    return (
      <div>
        {back}
        <Card className="mt-4 p-8 text-center text-muted">{error || t("platformTeam.member.notFound")}</Card>
      </div>
    );
  }

  const status = !member.is_active
    ? { tone: "danger", label: t("platformTeam.inactive") }
    : !member.activated
      ? { tone: "warn", label: t("platformTeam.pendingActivation") }
      : { tone: "ok", label: t("platformTeam.activated") };
  const now = Date.now();

  return (
    <div>
      <div className="mb-4">{back}</div>
      <PageHeader
        title={member.full_name || member.email}
        subtitle={member.email}
        actions={
          <>
            {member.id === user.id && <Badge tone="accent">{t("platformTeam.you")}</Badge>}
            <Badge tone={status.tone}>{status.label}</Badge>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Section icon={UserRound} title={t("platformTeam.member.profile")}>
          <dl className="divide-y divide-line">
            <Row label={t("platformTeam.member.email")}>{member.email}</Row>
            <Row label={t("platformTeam.member.role")}>
              {member.is_superuser
                ? t("platformTeam.member.djangoSuperuser")
                : <span className="inline-flex items-center gap-1"><ShieldCheck size={14} className="text-accent" />{roleLabel(member.role_name)}</span>}
            </Row>
            <Row label={t("platformTeam.member.status")}><Badge tone={status.tone}>{status.label}</Badge></Row>
            <Row label={t("platformTeam.member.created")}>{fmt(member.created_at)}</Row>
            <Row label={t("platformTeam.member.lastLogin")}>
              {member.last_login ? fmt(member.last_login) : <span className="text-muted">{t("platformTeam.neverSignedIn")}</span>}
            </Row>
          </dl>
        </Section>

        <Section icon={ShieldCheck} title={t("platformTeam.member.capabilities")} hint={t("platformTeam.member.capabilitiesHint")}>
          {member.capabilities.length ? (
            <ul className="grid gap-2 text-sm">
              {member.capabilities.map((code) => (
                <li key={code} className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {capabilityLabel(code)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("platformTeam.member.noCapabilities")}</p>
          )}
        </Section>

        <Section icon={KeyRound} title={t("platformTeam.member.provenance")}>
          {member.invitations.length ? (
            <div className="text-sm">
              {member.invited_by && (
                <p>
                  <span className="text-muted">{t("platformTeam.member.invitedBy")}</span>{" "}
                  <Link href={`/platform-team/member/?id=${member.invited_by.id}`} className="font-medium text-accent hover:underline">
                    {member.invited_by.full_name || member.invited_by.email}
                  </Link>
                </p>
              )}
              <ul className="mt-3 divide-y divide-line">
                {member.invitations.map((invite) => {
                  const state = invite.accepted_at
                    ? t("platformTeam.member.invitationAccepted", { date: fmt(invite.accepted_at) })
                    : invite.revoked_at
                      ? t("platformTeam.member.invitationRevoked", { date: fmt(invite.revoked_at) })
                      : new Date(invite.expires_at).getTime() < now
                        ? t("platformTeam.member.invitationExpired", { date: fmt(invite.expires_at) })
                        : t("platformTeam.member.invitationExpires", { date: fmt(invite.expires_at) });
                  return (
                    <li key={invite.created_at} className="flex flex-col gap-1 py-2 sm:flex-row sm:justify-between">
                      <span>{t("platformTeam.member.invitationOn", { date: fmt(invite.created_at) })}</span>
                      <span className="text-muted">{state}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-muted">{t("platformTeam.member.noInvitations")}</p>
          )}
        </Section>

        <Section icon={Clock} title={t("platformTeam.member.history")} hint={t("platformTeam.member.historyHint")}>
          {member.history.length ? (
            <ul className="divide-y divide-line text-sm">
              {member.history.map((row) => (
                <li key={row.id} className="py-2">
                  <div>{describeHistory(row, t, roleLabel)}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {fmt(row.created_at)}
                    {row.user && <> · {t("platformTeam.member.by", { name: row.user.full_name || row.user.email })}</>}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("platformTeam.member.noHistory")}</p>
          )}
        </Section>
      </div>

      <div className="mt-4">
        <Section icon={Clock} title={t("platformTeam.member.activity")} hint={t("platformTeam.member.activityHint")}>
          {member.activity.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <tbody className="divide-y divide-line">
                  {member.activity.map((row) => (
                    <tr key={row.id}>
                      <td className="py-2 pe-4 whitespace-nowrap text-muted">{fmt(row.created_at)}</td>
                      <td className="py-2 pe-4"><Badge>{t(`platformTeam.member.actions.${row.action}`)}</Badge></td>
                      <td className="py-2 pe-4 font-medium">{row.entity_type}{row.entity_id && <span className="text-muted"> #{row.entity_id}</span>}</td>
                      <td className="py-2 text-xs text-muted">{row.ip_address || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted">{t("platformTeam.member.noActivity")}</p>
          )}
        </Section>
      </div>
    </div>
  );
}

export default function PlatformTeamMemberPage() {
  return (
    // useSearchParams needs a Suspense boundary for the static export.
    <Suspense fallback={null}>
      <MemberDetail />
    </Suspense>
  );
}
