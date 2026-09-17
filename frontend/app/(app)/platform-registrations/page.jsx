"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Copy, FileCheck2, KeyRound, Lock } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { registration } from "@/lib/api";
import { Badge, Button, Card, PageHeader, Select } from "@/components/ui/kit";
import FollowUpPanel, { ContactLinks, FollowUpBadge } from "@/components/platform/FollowUpPanel";

const ACTIVE = ["submitted", "under_review", "needs_information", "approved"];
const REVIEW = ["under_review", "needs_information", "rejected"];
const APPROVABLE = ["submitted", "under_review", "needs_information"];
const TONES = { submitted: "accent", under_review: "warn", needs_information: "warn", approved: "ok", provisioned: "ok", rejected: "danger", withdrawn: "muted" };

export default function PlatformRegistrationsPage() {
  const { user, can } = useAuth();
  const canView = can("platform.registrations.view");
  const canReview = can("platform.registrations.review");
  const canProvision = can("platform.registrations.provision");
  const canReissue = can("platform.invitations.reissue");
  const { t, language } = useI18n();
  const [rows, setRows] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState(null);

  const load = useCallback(async () => {
    if (!canView) return;
    setLoading(true);
    setError("");
    try {
      const [list, publicPlans] = await Promise.all([
        registration.list(),
        registration.publicPlans().catch(() => ({ data: [] })),
      ]);
      setRows(list.data.results || list.data);
      setPlans(publicPlans.data || []);
    } catch {
      setError(t("platformRegistration.loadError"));
    } finally {
      setLoading(false);
    }
  }, [t, canView]);
  useEffect(() => { load(); }, [load]);

  const label = (status) => t(`platformRegistration.status${status.charAt(0).toUpperCase()}${status.slice(1)}`);
  // A SaaS request whose plan has since been unpublished can't be approved;
  // the published-plan list is the source of truth for what is still live.
  const planIsLive = (row) => row.delivery_mode !== "saas" || plans.some((plan) => plan.id === row.plan_version);

  const patchRow = (id, data) => setRows((current) => current.map((item) => (item.id === id ? { ...item, ...data } : item)));
  const saveFollowUp = async (row, patch) => {
    setSaving(`followup-${row.id}`);
    setError("");
    try {
      const response = await registration.update(row.id, patch);
      patchRow(row.id, response.data);
    } catch {
      setError(t("platformRegistration.saveError"));
    } finally {
      setSaving(null);
    }
  };
  const recordContact = (row) => (channel) => {
    registration.contact(row.id, channel).then((response) => patchRow(row.id, response.data)).catch(() => {});
  };

  const run = async (row, action, body = {}) => {
    setSaving(`${action}-${row.id}`);
    setError("");
    try {
      let response;
      if (action === "approve") response = await registration.approve(row.id, body);
      else if (action === "provision") response = await registration.provision(row.id);
      else if (action === "reissue") response = await registration.reissueInvitation(row.id);
      else if (action === "plan") response = await registration.setPlan(row.id, body.plan_version);
      else response = await registration.review(row.id, body);
      if (response.data.owner_invitation_token) {
        const token = response.data.owner_invitation_token;
        setInvite({ company: response.data.company_name, emailSent: !!response.data.invitation_email_sent, link: `${window.location.origin}/activate-owner/?token=${encodeURIComponent(token)}` });
      }
      await load();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError?.response?.data?.plan_version?.[0] || t("platformRegistration.saveError"));
    } finally {
      setSaving(null);
    }
  };

  if (!canView) return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("platformRegistration.noAccess")}</p></Card>;

  return (
    <div>
      <PageHeader title={t("platformRegistration.title")} subtitle={t("platformRegistration.subtitle")} actions={<Badge tone="accent">{t("platformRegistration.count", { count: rows.length })}</Badge>} />
      {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {invite && (
        <Card className="mb-5 border-accent/30 p-5">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 text-ok" />
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold">{t("platformRegistration.inviteReady", { company: invite.company })}</h2>
              <p className="mt-1 text-sm text-muted">{invite.emailSent ? t("platform.inviteEmailed") : t("platformRegistration.inviteHint")}</p>
              <code className="mt-3 block break-all rounded-control bg-paper p-3 text-xs">{invite.link}</code>
              <Button variant="outline" className="mt-3" onClick={() => navigator.clipboard.writeText(invite.link)}><Copy size={15} />{t("platformRegistration.copyInviteLink")}</Button>
            </div>
          </div>
        </Card>
      )}
      {loading ? (
        <Card className="p-8 text-center text-muted">{t("common.loading")}</Card>
      ) : rows.length === 0 ? (
        <Card className="p-10 text-center"><FileCheck2 className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("platformRegistration.empty")}</p></Card>
      ) : (
        <div className="grid gap-4">
          {rows.map((row) => {
            const live = planIsLive(row);
            const open = ACTIVE.includes(row.status);
            return (
              <Card key={row.id} className="p-5">
                <div className="flex flex-col justify-between gap-5 lg:flex-row">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-display text-lg font-semibold">{row.company_name}</h2>
                      <Badge tone={TONES[row.status]}>{label(row.status)}</Badge>
                      <FollowUpBadge row={row} />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                      <span className="text-muted">{row.contact_name}</span>
                      <ContactLinks phone={row.phone} email={row.email} country={row.country} onContact={recordContact(row)} />
                    </div>
                    <div className="mt-3 grid gap-1 text-sm text-muted sm:grid-cols-2">
                      <span>{t("platformRegistration.plan")}: {row.plan_name || "—"}</span>
                      <span>{t("platformRegistration.delivery")}: {row.delivery_mode}</span>
                      <span>{t("platformRegistration.country")}: {row.country}</span>
                      <span>{t("platformRegistration.received")}: {new Date(row.created_at).toLocaleDateString(language === "ar" ? "ar" : "en")}</span>
                    </div>
                    {open && !live && <p className="mt-2 text-sm font-medium text-danger">{t("platformRegistration.planUnavailable")}</p>}
                    {row.message && <p className="mt-3 whitespace-pre-wrap text-sm text-muted">{row.message}</p>}
                    <FollowUpPanel row={row} canEdit={canReview} saving={saving === `followup-${row.id}`} onSave={(patch) => saveFollowUp(row, patch)} />
                  </div>
                  <div className="flex shrink-0 flex-wrap items-start gap-2">
                    {canReview && open && row.delivery_mode === "saas" && plans.length > 0 && (
                      <Select value={live ? row.plan_version : ""} onChange={(event) => event.target.value && run(row, "plan", { plan_version: Number(event.target.value) })} className="w-44" disabled={saving === `plan-${row.id}`}>
                        <option value="" disabled>{t("platformRegistration.changePlan")}</option>
                        {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.plan_name} · {plan.price} {plan.currency}</option>)}
                      </Select>
                    )}
                    {canReview && open && (
                      <Select value="" onChange={(event) => event.target.value && run(row, "review", { status: event.target.value })} className="w-44">
                        <option value="" disabled>{t("platformRegistration.setStatus")}</option>
                        {REVIEW.map((status) => <option key={status} value={status}>{label(status)}</option>)}
                      </Select>
                    )}
                    {canReview && APPROVABLE.includes(row.status) && <Button disabled={saving === `approve-${row.id}` || !live} onClick={() => run(row, "approve")}>{t("platformRegistration.approve")}</Button>}
                    {canProvision && row.status === "approved" && <Button disabled={saving === `provision-${row.id}`} onClick={() => run(row, "provision")}>{t("platformRegistration.provision")}</Button>}
                    {canReissue && row.status === "provisioned" && (
                      <Button variant="outline" disabled={saving === `reissue-${row.id}`} title={t("platformRegistration.reissueHint")} onClick={() => run(row, "reissue")}>
                        <KeyRound size={15} />{t("platformRegistration.reissueInvite")}
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
