"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Lock } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformSubscriptions as api } from "@/lib/api";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";

const STATES = ["trialing", "active", "grace", "read_only", "suspended", "cancelled"];

function localDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function initialDraft(row) {
  const endField = {
    trialing: "trial_ends_at",
    active: "period_ends_at",
    grace: "grace_ends_at",
  }[row.status];
  return {
    plan_version: String(row.plan_version || ""),
    status: row.status === "legacy" ? "active" : row.status,
    end: localDateTime(endField ? row[endField] : ""),
  };
}

export default function PlatformSubscriptionsPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [plans, setPlans] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const versions = useMemo(
    () => plans.flatMap((plan) => (plan.versions || []).filter((version) => version.published_at)),
    [plans],
  );

  const load = useCallback(async () => {
    setError("");
    try {
      const [subscriptionsResponse, plansResponse] = await Promise.all([api.list(), api.plans()]);
      const nextRows = subscriptionsResponse.data.results || subscriptionsResponse.data;
      setRows(nextRows);
      setPlans(plansResponse.data.results || plansResponse.data);
      setDrafts(Object.fromEntries(nextRows.map((row) => [row.id, initialDraft(row)])));
    } catch {
      setError(t("subscription.loadError"));
    }
  }, [t]);

  useEffect(() => {
    if (user?.is_platform_admin) load();
  }, [load, user?.is_platform_admin]);

  const updateDraft = (id, field, value) => {
    setDrafts((current) => ({
      ...current,
      [id]: { ...current[id], [field]: value, ...(field === "status" ? { end: "" } : {}) },
    }));
  };

  const save = async (row) => {
    const draft = drafts[row.id];
    const endField = {
      trialing: "trial_ends_at",
      active: "period_ends_at",
      grace: "grace_ends_at",
    }[draft.status];
    const body = {
      plan_version: Number(draft.plan_version),
      status: draft.status,
    };
    if (endField && draft.end) body[endField] = new Date(draft.end).toISOString();
    setSaving(row.id);
    setError("");
    setSuccess("");
    try {
      await api.configure(row.id, body);
      setSuccess(t("subscription.configurationSaved"));
      await load();
    } catch (requestError) {
      const data = requestError?.response?.data;
      const first = data && Object.values(data).flat()[0];
      setError(typeof first === "string" ? first : t("subscription.loadError"));
    } finally {
      setSaving(null);
    }
  };

  if (!user?.is_platform_admin) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">
          {t("shell.noAccessBody", { module: t("nav.platformSubscriptions") })}
        </p>
      </Card>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("subscription.platformTitle")}
        subtitle={t("subscription.platformSubtitle")}
        actions={
          <Badge tone="accent">
            {t("subscription.activeSubscriptions", { count: rows.length })}
          </Badge>
        }
      />
      {error && <div className="mb-4 rounded-control bg-danger/10 p-3 text-danger">{error}</div>}
      {success && <div className="mb-4 rounded-control bg-ok/10 p-3 text-ok">{success}</div>}
      <div className="grid gap-4">
        {rows.map((row) => {
          const draft = drafts[row.id] || initialDraft(row);
          const needsEnd = ["trialing", "active", "grace"].includes(draft.status);
          return (
            <Card key={row.id} className="p-5">
              <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                <div className="min-w-48">
                  <div className="font-display text-lg font-semibold">{row.company_name}</div>
                  <div className="mt-1 text-sm text-muted">
                    {row.plan?.plan_name} · {row.plan?.billing_cycle}
                  </div>
                  <Badge tone={row.status === "active" || row.status === "legacy" ? "ok" : "warn"}>
                    {row.status}
                  </Badge>
                </div>
                <div className="grid flex-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <Field label={t("subscription.selectPlan")}>
                    <Select
                      value={draft.plan_version}
                      onChange={(event) => updateDraft(row.id, "plan_version", event.target.value)}
                    >
                      {versions.map((version) => (
                        <option key={version.id} value={version.id}>
                          {version.plan_name} v{version.version} · {version.price} {version.currency}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label={t("subscription.state")}>
                    <Select
                      value={draft.status}
                      onChange={(event) => updateDraft(row.id, "status", event.target.value)}
                    >
                      {STATES.map((state) => <option key={state} value={state}>{state}</option>)}
                    </Select>
                  </Field>
                  <Field label={t("subscription.endDate")}>
                    <Input
                      type="datetime-local"
                      value={draft.end}
                      disabled={!needsEnd}
                      required={needsEnd}
                      onChange={(event) => updateDraft(row.id, "end", event.target.value)}
                    />
                  </Field>
                  <div className="flex items-end">
                    <Button
                      className="w-full"
                      disabled={saving === row.id || !draft.plan_version || (needsEnd && !draft.end)}
                      onClick={() => save(row)}
                    >
                      {t("subscription.configure")}
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
