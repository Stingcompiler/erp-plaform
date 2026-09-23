"use client";

// One company user in full: profile, role and branch, created and last
// sign-in, every change made to the account, and (for owners and managers
// who may read the audit log) the person's own recent actions. Edit,
// deactivate or reactivate from here. Reached from the users list; the id
// travels in the query string because the static export cannot have a
// dynamic segment.
import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, Clock, Lock, Pencil, ShieldCheck, UserRound, UserX } from "lucide-react";

import { useAuth } from "../../../providers/AuthProvider";
import { useI18n } from "../../../providers/I18nProvider";
import { users as usersApi } from "@/lib/api";
import { translateRole } from "@/lib/i18n";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";
import UserForm from "@/components/users/UserForm";
import { errorText } from "@/lib/errors";
import { useConfirm } from "@/components/ui/ConfirmDialog";

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

function describeHistory(row, t) {
  const m = row.metadata || {};
  if (row.action === "create") return t("users.detail.events.created");
  if (row.action === "archive") return t("users.detail.events.deactivated");
  if (row.action === "unarchive") return t("users.detail.events.reactivated");
  if (row.action === "password_reset_by_admin") return t("users.detail.events.passwordResetByAdmin");
  if (row.action === "password_changed") return t("users.detail.events.passwordChanged");
  const changes = m.changes && typeof m.changes === "object" ? m.changes : {};
  const active = changes.is_active?.after;
  if (active === "True" || active === true) return t("users.detail.events.reactivated");
  if (active === "False" || active === false) return t("users.detail.events.deactivated");
  const changed = Object.keys(changes).length ? Object.keys(changes) : Array.isArray(m.fields) ? m.fields : [];
  if (changed.length) {
    const labels = changed.map((f) => {
      const label = t(`users.detail.fields.${f}`);
      return label.startsWith("users.") ? f : label;
    });
    return t("users.detail.events.updatedFields", { fields: labels.join("، ") });
  }
  return t("users.detail.events.updated");
}

function UserDetail() {
  const { user: currentUser, canRead, canWrite, can } = useAuth();
  const { t, language, dir } = useI18n();
  const confirm = useConfirm();
  const params = useSearchParams();
  const id = params.get("id");
  const [person, setPerson] = useState(null);
  const [roles, setRoles] = useState([]);
  const [branches, setBranches] = useState([]);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [formOpen, setFormOpen] = useState(false);

  const readable = canRead("users");
  const writable = canWrite("users");
  const canEdit = (target) => {
    if (!target || !writable || target.id === currentUser?.id) return false;
    if (can("users.assign_owner")) return true;
    if (can("users.manage_company")) return target.role_name !== "Business Owner";
    if (can("users.manage_branch")) return !["Business Owner", "General Manager", "Branch Manager"].includes(target.role_name);
    return false;
  };

  const load = useCallback(() => {
    if (!readable || !id) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    usersApi
      .get(id)
      .then((response) => { if (!cancelled) setPerson(response.data); })
      .catch((requestError) => {
        if (cancelled) return;
        setError(t(requestError?.response?.status === 404 ? "users.detail.notFound" : "users.detail.loadError"));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, readable, t]);
  useEffect(() => load(), [load]);
  useEffect(() => {
    if (!writable) return;
    usersApi.roles().then((r) => setRoles(r.data.results || r.data)).catch(() => {});
    usersApi.branches().then((r) => setBranches(r.data.results || r.data)).catch(() => {});
  }, [writable]);

  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  const BackIcon = dir === "rtl" ? ArrowRight : ArrowLeft;
  const back = (
    <Link href="/users" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">
      <BackIcon size={15} />{t("users.detail.back")}
    </Link>
  );

  const run = async (key, fn) => {
    setSaving(key);
    setActionError("");
    try {
      await fn();
      load();
    } catch (requestError) {
      setActionError(errorText(requestError, t, "users.detail.saveError"));
    } finally {
      setSaving(null);
    }
  };
  const deactivate = async () => {
    if (!(await confirm(t("users.detail.deactivateConfirm", { email: person.email }), { tone: "danger" }))) return;
    run("deactivate", () => usersApi.deactivate(person.id));
  };

  if (!readable) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">{t("users.noAccess")}</p>
      </Card>
    );
  }
  if (loading) return <Card className="p-8 text-center text-muted">{t("common.loading")}</Card>;
  if (error || !person) {
    return (
      <div>
        {back}
        <Card className="mt-4 p-8 text-center text-muted">{error || t("users.detail.notFound")}</Card>
      </div>
    );
  }

  const editable = canEdit(person);
  const isMe = person.id === currentUser?.id;

  return (
    <div>
      <div className="mb-4">{back}</div>
      <PageHeader
        title={person.full_name || person.email}
        subtitle={person.email}
        actions={
          <>
            {isMe && <Badge tone="accent">{t("platformTeam.you")}</Badge>}
            {person.is_active ? <Badge tone="ok">{t("common.active")}</Badge> : <Badge tone="muted">{t("common.inactive")}</Badge>}
          </>
        }
      />
      {actionError && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{actionError}</p>}

      {editable && (
        <Card className="mb-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display font-semibold">{t("users.detail.manage")}</h2>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" onClick={() => setFormOpen(true)}><Pencil size={15} />{t("users.detail.edit")}</Button>
              {person.is_active ? (
                <Button variant="danger" disabled={saving === "deactivate"} onClick={deactivate}><UserX size={15} />{t("users.detail.deactivate")}</Button>
              ) : (
                <Button disabled={saving === "reactivate"} onClick={() => run("reactivate", () => usersApi.reactivate(person.id))}>{t("users.detail.reactivate")}</Button>
              )}
            </div>
          </div>
          <p className="mt-2 text-xs text-muted">{t("users.detail.deactivateWhy")}</p>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Section icon={UserRound} title={t("users.detail.profile")}>
          <dl className="divide-y divide-line">
            <Row label={t("common.email")}>{person.email}</Row>
            <Row label={t("users.fullName")}>{person.full_name || "—"}</Row>
            <Row label={t("users.role")}>
              <span className="inline-flex items-center gap-1"><ShieldCheck size={14} className="text-accent" />{person.role_name ? translateRole(person.role_name, t) : "—"}</span>
            </Row>
            <Row label={t("users.branch")}>{person.branch_name || "—"}</Row>
            <Row label={t("common.status")}>{person.is_active ? t("common.active") : t("common.inactive")}</Row>
            <Row label={t("users.detail.created")}>{fmt(person.created_at)}</Row>
            <Row label={t("users.detail.lastLogin")}>{person.last_login ? fmt(person.last_login) : <span className="text-muted">{t("platformTeam.neverSignedIn")}</span>}</Row>
          </dl>
        </Section>

        <Section icon={Clock} title={t("users.detail.history")} hint={t("users.detail.historyHint")}>
          {person.history?.length ? (
            <ul className="divide-y divide-line text-sm">
              {person.history.map((row) => (
                <li key={row.id} className="py-2">
                  <div className={row.action === "password_reset_by_admin" ? "font-medium text-warn" : ""}>{describeHistory(row, t)}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {fmt(row.created_at)}
                    {row.user && <> · {t("users.detail.by", { name: row.user.full_name || row.user.email })}</>}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("users.detail.noHistory")}</p>
          )}
        </Section>
      </div>

      {Array.isArray(person.activity) && (
        <div className="mt-4">
          <Section icon={Clock} title={t("users.detail.activity")} hint={t("users.detail.activityHint")}>
            {person.activity.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-sm">
                  <tbody className="divide-y divide-line">
                    {person.activity.map((row) => (
                      <tr key={row.id}>
                        <td className="py-2 pe-4 whitespace-nowrap text-muted">{fmt(row.created_at)}</td>
                        <td className="py-2 pe-4"><Badge>{row.action}</Badge></td>
                        <td className="py-2 font-medium">{row.entity_type}{row.entity_id && <span className="text-muted"> #{row.entity_id}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted">{t("users.detail.noActivity")}</p>
            )}
          </Section>
        </div>
      )}

      {editable && (
        <UserForm
          open={formOpen}
          onClose={() => setFormOpen(false)}
          onSaved={load}
          user={person}
          roles={roles}
          branches={branches}
        />
      )}
    </div>
  );
}

export default function UserDetailPage() {
  return (
    // useSearchParams needs a Suspense boundary for the static export.
    <Suspense fallback={null}>
      <UserDetail />
    </Suspense>
  );
}
