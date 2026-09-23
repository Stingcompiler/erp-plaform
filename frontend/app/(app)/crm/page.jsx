"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Lock, Plus, UserPlus } from "lucide-react";

import { crm } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";
import LeadDrawer from "@/components/crm/LeadDrawer";
import { errorText } from "@/lib/errors";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";

const STAGE_LABEL = {
  new: "crm.stageNew",
  contacted: "crm.stageContacted",
  qualified: "crm.stageQualified",
  proposal: "crm.stageProposal",
  won: "crm.stageWon",
  lost: "crm.stageLost",
};
const STAGE_TONE = {
  new: "muted",
  contacted: "accent",
  qualified: "accent",
  proposal: "warn",
  won: "ok",
  lost: "danger",
};
const FILTERS = ["all", "new", "contacted", "qualified", "proposal", "won", "lost"];

function StatTile({ label, value }) {
  return (
    <Card className="p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="tabular mt-1 text-2xl font-semibold text-ink">{value}</div>
    </Card>
  );
}

export default function CrmPage() {
  const { canRead, canWrite } = useAuth();
  const { t, language } = useI18n();
  const writable = canWrite("crm");

  const [leads, setLeads] = useState([]);
  const [pipeline, setPipeline] = useState(null);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [drawerLead, setDrawerLead] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [converting, setConverting] = useState(null);
  const toast = useToast();

  const load = useCallback(() => {
    setLoading(true);
    crm
      .leads({ page: 1 })
      .then((r) => setLeads(r.data.results))
      .catch(() => setLeads([]))
      .finally(() => setLoading(false));
    crm.pipeline().then((r) => setPipeline(r.data)).catch(() => setPipeline(null));
    crm.groups().then((r) => setGroups(r.data.results)).catch(() => setGroups([]));
  }, []);

  useEffect(() => {
    if (canRead("crm")) load();
  }, [canRead, load]);

  async function convertLead(lead) {
    setConverting(lead.id);
    try {
      const r = await crm.convertLead(lead.id);
      // The server is idempotent, so say which of the two actually happened
      // rather than claiming a customer was created every time.
      toast.success(
        r.data.created
          ? t("crm.converted", { name: r.data.name })
          : t("crm.alreadyConverted", { name: r.data.name }),
      );
    } catch (err) {
      toast.error(errorText(err, t, "crm.convertFailed"));
    } finally {
      setConverting(null);
    }
  }

  const money = (v) =>
    Number(v ?? 0).toLocaleString(language === "ar" ? "ar" : "en", {
      maximumFractionDigits: 0,
    });

  const stats = useMemo(() => {
    if (!pipeline) return { open: 0, value: 0, won: 0 };
    const openStages = ["new", "contacted", "qualified", "proposal"];
    const open = openStages.reduce((s, k) => s + (pipeline[k]?.count || 0), 0);
    const value = openStages.reduce((s, k) => s + Number(pipeline[k]?.value || 0), 0);
    const won = pipeline.won?.count || 0;
    return { open, value, won };
  }, [pipeline]);

  const dueFollowups = useMemo(
    () => leads.reduce((s, l) => s + (l.open_followups || 0), 0),
    [leads]
  );

  const visible = useMemo(
    () => (filter === "all" ? leads : leads.filter((l) => l.stage === filter)),
    [leads, filter]
  );

  const openNew = () => {
    setDrawerLead(null);
    setDrawerOpen(true);
  };
  const openLead = (lead) => {
    setDrawerLead(lead);
    setDrawerOpen(true);
  };

  if (!canRead("crm")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("crm.noAccess")}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("crm.title")}
        subtitle={t("crm.subtitle")}
        actions={
          writable && (
            <Button onClick={openNew}>
              <Plus size={16} /> {t("crm.newLead")}
            </Button>
          )
        }
      />

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatTile label={t("crm.openLeads")} value={stats.open} />
        <StatTile label={t("crm.pipelineValue")} value={money(stats.value)} />
        <StatTile label={t("crm.dueFollowups")} value={dueFollowups} />
        <StatTile label={t("crm.wonThisPeriod")} value={stats.won} />
      </div>

      {/* Stage filter chips */}
      <div className="mt-6 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`tap rounded-full border px-3 py-1.5 text-sm transition-colors ${
              filter === f
                ? "border-accent bg-accent text-white"
                : "border-line bg-surface text-muted hover:text-ink"
            }`}
          >
            {f === "all" ? t("common.all") : t(STAGE_LABEL[f])}
          </button>
        ))}
      </div>

      {/* Lead list — cards on mobile, table-like rows scale up */}
      <div className="mt-4 space-y-2">
        {loading && <SkeletonRows />}
        {!loading && visible.length === 0 && (
          <Card>
            <EmptyState
              icon={UserPlus}
              title={t("crm.emptyTitle")}
              body={t("crm.emptyBody")}
              filtered={filter !== "all" && leads.length > 0}
              onClearFilters={() => setFilter("all")}
              action={writable && <Button onClick={openNew}><Plus size={16} /> {t("crm.newLead")}</Button>}
            />
          </Card>
        )}
        {!loading &&
          visible.map((lead) => (
            <div
              key={lead.id}
              className="flex w-full items-center gap-3 rounded-card border border-line bg-surface p-4 shadow-card transition-colors hover:border-accent"
            >
              <button
                onClick={() => openLead(lead)}
                className="flex min-w-0 flex-1 items-center gap-3 text-start"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-ink">{lead.name}</div>
                  <div className="truncate text-sm text-muted">
                    {lead.contact_name || lead.email || lead.phone || "—"}
                  </div>
                </div>
                <div className="hidden text-end sm:block">
                  <div className="tabular text-sm font-medium text-ink">
                    {money(lead.estimated_value)}
                  </div>
                  {lead.open_followups > 0 && (
                    <div className="text-xs text-muted">
                      {lead.open_followups} · {t("crm.followups")}
                    </div>
                  )}
                </div>
              </button>
              <Badge tone={STAGE_TONE[lead.stage]}>{t(STAGE_LABEL[lead.stage])}</Badge>
              {/* Winning a deal used to be a dead end — the customer had to be
                  re-keyed by hand into Sales. */}
              {lead.stage === "won" && writable && (
                <Button
                  variant="outline"
                  onClick={() => convertLead(lead)}
                  disabled={converting === lead.id}
                >
                  <UserPlus size={15} />
                  <span className="hidden sm:inline">
                    {converting === lead.id ? t("common.saving") : t("crm.convert")}
                  </span>
                </Button>
              )}
            </div>
          ))}
      </div>

      <LeadDrawer
        open={drawerOpen}
        lead={drawerLead}
        groups={groups}
        writable={writable}
        onClose={() => setDrawerOpen(false)}
        onSaved={load}
        onGroupsChanged={() => crm.groups().then((r) => setGroups(r.data.results)).catch(() => {})}
      />
    </div>
  );
}
