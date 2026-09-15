"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Copy, KeyRound, Lock, ShieldCheck, UserPlus } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformTeam } from "@/lib/api";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";

const DEFAULT_ROLE = "Support Agent";

const activationLink = (token) =>
  `${window.location.origin}/activate-owner/?kind=platform&token=${encodeURIComponent(token)}`;

export default function PlatformTeamPage() {
  const { user, can } = useAuth();
  const canView = can("platform.team.view");
  const { t, language } = useI18n();
  const canManage = can("platform.team.manage");
  const [rows, setRows] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState(null);
  const [form, setForm] = useState({ email: "", full_name: "", role: DEFAULT_ROLE });

  const load = useCallback(async () => {
    if (!canView) return;
    setLoading(true);
    setError("");
    try {
      const [members, roleList] = await Promise.all([
        platformTeam.list(),
        platformTeam.roles().catch(() => ({ data: [] })),
      ]);
      setRows(members.data);
      setRoles(roleList.data);
    } catch (requestError) {
      // Surface what the server said: a generic "could not load" hides
      // whether this was a 403 (role), a 500 (server) or a network drop.
      const status = requestError?.response?.status;
      const detail = requestError?.response?.data?.detail;
      setError([t("platformTeam.loadError"), status && `HTTP ${status}`, typeof detail === "string" && detail].filter(Boolean).join(" · "));
    } finally {
      setLoading(false);
    }
  }, [t, canView]);
  useEffect(() => { load(); }, [load]);

  const fail = (requestError) => {
    const data = requestError?.response?.data;
    const first = data?.detail || data?.email?.[0] || data?.role?.[0] || (Array.isArray(data) ? data[0] : null);
    setError(typeof first === "string" ? first : t("platformTeam.saveError"));
  };

  const submitInvite = async (event) => {
    event.preventDefault();
    setSaving("invite");
    setError("");
    try {
      const response = await platformTeam.invite(form);
      setInvite({ email: response.data.email, link: activationLink(response.data.invitation_token) });
      setForm({ email: "", full_name: "", role: DEFAULT_ROLE });
      await load();
    } catch (requestError) {
      fail(requestError);
    } finally {
      setSaving(null);
    }
  };

  const run = async (row, action, arg) => {
    setSaving(`${action}-${row.id}`);
    setError("");
    try {
      const response = await platformTeam[action](row.id, arg);
      if (response.data.invitation_token) {
        setInvite({ email: response.data.email, link: activationLink(response.data.invitation_token) });
      }
      await load();
    } catch (requestError) {
      fail(requestError);
    } finally {
      setSaving(null);
    }
  };

  // Unknown names (e.g. "Django superuser") fall back to the raw label.
  const roleLabel = (name) => {
    if (!name) return "";
    const label = t(`platformTeam.roles.${name}`);
    return label.startsWith("platformTeam.") ? name : label;
  };
  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  const statusOf = (row) => {
    if (!row.is_active) return { tone: "danger", label: t("platformTeam.inactive") };
    if (!row.activated) return { tone: "warn", label: t("platformTeam.pendingActivation") };
    return { tone: "ok", label: t("platformTeam.activated") };
  };

  if (!canView) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">{t("platformTeam.noAccess")}</p>
      </Card>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("platformTeam.title")}
        subtitle={t("platformTeam.subtitle")}
        actions={<Badge tone="accent">{t("platformTeam.count", { count: rows.length })}</Badge>}
      />
      {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {invite && (
        <Card className="mb-5 border-accent/30 p-5">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 text-ok" />
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold">{t("platformTeam.inviteReady", { email: invite.email })}</h2>
              <p className="mt-1 text-sm text-muted">{t("platformTeam.inviteHint2")}</p>
              <code className="mt-3 block break-all rounded-control bg-paper p-3 text-xs">{invite.link}</code>
              <Button variant="outline" className="mt-3" onClick={() => navigator.clipboard.writeText(invite.link)}>
                <Copy size={15} />{t("platformTeam.copyLink")}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {!canManage && (
        <p className="mb-4 rounded-control border border-line bg-surface p-3 text-sm text-muted">{t("platformTeam.readOnlyNotice")}</p>
      )}

      {canManage && <Card className="mb-5 p-5">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent"><UserPlus size={20} /></span>
          <div className="min-w-0 flex-1">
            <h2 className="font-display font-semibold">{t("platformTeam.invite")}</h2>
            <p className="mt-1 text-sm text-muted">{t("platformTeam.inviteHint")}</p>
            <form onSubmit={submitInvite} className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-start">
              <Field label={t("platformTeam.fullName")}>
                <Input required maxLength={255} value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
              </Field>
              <Field label={t("platformTeam.email")}>
                <Input required type="email" maxLength={254} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
              </Field>
              <Field label={t("platformTeam.role")} hint={t(`platformTeam.roleHints.${form.role}`)}>
                <Select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
                  {roles.map((role) => <option key={role.name} value={role.name}>{roleLabel(role.name)}</option>)}
                </Select>
              </Field>
              <div className="flex items-start lg:pt-6">
                <Button type="submit" disabled={saving === "invite"}>
                  {saving === "invite" ? t("platformTeam.sending") : t("platformTeam.send")}
                </Button>
              </div>
            </form>
            <p className="mt-3 text-xs text-muted">{t("platformTeam.rule")}</p>
          </div>
        </div>
      </Card>}

      {loading ? (
        <Card className="p-8 text-center text-muted">{t("common.loading")}</Card>
      ) : (
        <div className="grid gap-3">
          {rows.map((row) => {
            const status = statusOf(row);
            const isMe = row.id === user.id;
            return (
              <Card key={row.id} className="p-4">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/platform-team/member/?id=${row.id}`}
                        className="font-semibold hover:text-accent hover:underline"
                        title={t("platformTeam.viewMember")}
                      >
                        {row.full_name || row.email}
                      </Link>
                      {isMe && <Badge tone="accent">{t("platformTeam.you")}</Badge>}
                      <Badge tone={status.tone}>{status.label}</Badge>
                    </div>
                    <div className="mt-1 text-sm text-muted">
                      {row.email}
                      {row.role_name && <> · <ShieldCheck size={12} className="inline" /> {roleLabel(row.role_name)}</>}
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {row.last_login ? t("platformTeam.lastLogin", { date: fmt(row.last_login) }) : t("platformTeam.neverSignedIn")}
                      {row.invitation_expires_at && !row.activated && <> · {t("platformTeam.expires", { date: fmt(row.invitation_expires_at) })}</>}
                    </div>
                  </div>
                  {canManage && <div className="flex shrink-0 flex-wrap gap-2">
                    {!row.is_superuser && roles.length > 0 && (
                      <Select
                        value={row.role_name}
                        disabled={saving === `setRole-${row.id}`}
                        onChange={(event) => run(row, "setRole", event.target.value)}
                        className="w-44"
                        aria-label={t("platformTeam.changeRole")}
                      >
                        {roles.map((role) => <option key={role.name} value={role.name}>{roleLabel(role.name)}</option>)}
                      </Select>
                    )}
                    {row.is_active && !row.activated && (
                      <Button variant="outline" disabled={saving === `reissue-${row.id}`} onClick={() => run(row, "reissue")}>
                        <KeyRound size={15} />{t("platformTeam.reissue")}
                      </Button>
                    )}
                    {!isMe && row.is_active && (
                      <Button variant="outline" disabled={saving === `deactivate-${row.id}`} onClick={() => run(row, "deactivate")}>
                        {t("platformTeam.deactivate")}
                      </Button>
                    )}
                    {!row.is_active && (
                      <Button disabled={saving === `activate-${row.id}`} onClick={() => run(row, "activate")}>
                        {t("platformTeam.activate")}
                      </Button>
                    )}
                  </div>}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
