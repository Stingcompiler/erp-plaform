"use client";

import { useCallback, useEffect, useState } from "react";
import { Inbox, Lock, Search } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformLeads as platformLeadsApi } from "@/lib/api";
import { Badge, Card, Input, PageHeader, Select } from "@/components/ui/kit";
import FollowUpPanel, { ContactLinks, FollowUpBadge } from "@/components/platform/FollowUpPanel";

const STATUSES = ["new", "contacted", "qualified", "closed"];
const TONES = { new: "accent", contacted: "warn", qualified: "ok", closed: "muted" };

export default function PlatformLeadsPage() {
  const { user, can } = useAuth();
  const canView = can("platform.leads.view");
  const canManageLeads = can("platform.leads.manage");
  const { t, language } = useI18n();
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [dueOnly, setDueOnly] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!canView) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    platformLeadsApi
      .list({ search, status, ...(dueOnly ? { due: 1 } : {}) })
      .then((response) => {
        setRows(response.data.results || response.data);
        setCount(response.data.count ?? response.data.length);
      })
      .catch(() => {
        setRows([]);
        setCount(0);
        setError(t("platformLeads.loadError"));
      })
      .finally(() => setLoading(false));
  }, [search, status, dueOnly, t, canView]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  const updateStatus = async (lead, nextStatus) => {
    setError("");
    setRows((current) => current.map((row) => row.id === lead.id ? { ...row, status: nextStatus } : row));
    try {
      await platformLeadsApi.update(lead.id, { status: nextStatus });
    } catch {
      setRows((current) => current.map((row) => row.id === lead.id ? { ...row, status: lead.status } : row));
      setError(t("platformLeads.saveError"));
    }
  };

  const patchRow = (id, data) => setRows((current) => current.map((row) => (row.id === id ? { ...row, ...data } : row)));
  const saveFollowUp = async (lead, patch) => {
    setSavingId(lead.id);
    setError("");
    try {
      const response = await platformLeadsApi.update(lead.id, patch);
      patchRow(lead.id, response.data);
    } catch {
      setError(t("platformLeads.saveError"));
    } finally {
      setSavingId(null);
    }
  };
  // Fired by the call/WhatsApp/email links; the link itself still opens.
  const recordContact = (lead) => (channel) => {
    platformLeadsApi.contact(lead.id, channel).then((response) => patchRow(lead.id, response.data)).catch(() => {});
  };

  const statusLabel = (value) => t(`platformLeads.status${value.charAt(0).toUpperCase()}${value.slice(1)}`);
  const dateLabel = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en");

  if (!canView) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("platformLeads.noAccess")}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("platformLeads.title")}
        subtitle={t("platformLeads.subtitle")}
        actions={<span className="tabular text-sm text-muted">{t("platformLeads.count", { count })}</span>}
      />

      <Card className="mb-5 p-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_220px]">
          <div className="relative">
            <Search size={16} className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("platformLeads.searchPlaceholder")} className="ps-9" />
          </div>
          <Select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">{t("platformLeads.allStatuses")}</option>
            {STATUSES.map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
          </Select>
        </div>
        <label className="mt-3 inline-flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" checked={dueOnly} onChange={(event) => setDueOnly(event.target.checked)} className="h-4 w-4 accent-accent" />
          {t("followUp.dueOnly")}
        </label>
      </Card>

      {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {loading ? (
        <Card className="p-8 text-center text-muted">{t("common.loading")}</Card>
      ) : rows.length === 0 ? (
        <Card className="p-10 text-center"><Inbox className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("platformLeads.empty")}</p></Card>
      ) : (
        <div className="grid gap-4">
          {rows.map((lead) => (
            <Card key={lead.id} className="p-5">
              <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-display text-lg font-semibold">{lead.name}</h2>
                    <Badge tone={TONES[lead.status]}>{statusLabel(lead.status)}</Badge>
                    <FollowUpBadge row={lead} />
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                    <ContactLinks phone={lead.phone} email={lead.email} onContact={recordContact(lead)} />
                    {lead.preferred_channel && <Badge tone={lead.preferred_channel === "whatsapp" ? "ok" : "muted"}>{t("platformLeads.prefers", { channel: t(`landing.channels.${lead.preferred_channel}`) })}</Badge>}
                  </div>
                  {lead.message && <div className="mt-4"><div className="text-xs font-medium text-muted">{t("platformLeads.message")}</div><p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">{lead.message}</p></div>}
                  <div className="mt-4 text-xs text-muted">{t("platformLeads.received")}: {dateLabel(lead.created_at)}</div>
                  <FollowUpPanel row={lead} canEdit={canManageLeads} saving={savingId === lead.id} onSave={(patch) => saveFollowUp(lead, patch)} />
                </div>
                <Select value={lead.status} disabled={!canManageLeads} onChange={(event) => updateStatus(lead, event.target.value)} className="w-full sm:w-44">
                  {STATUSES.map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
                </Select>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
