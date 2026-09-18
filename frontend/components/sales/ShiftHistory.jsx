"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, History } from "lucide-react";

import { cashShifts } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import { Badge, Button, Card, Select } from "@/components/ui/kit";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Past till sessions and the manager sign-off. Closing a drawer recorded a
 * count and a variance, but nobody could see yesterday's shifts or accept
 * the count, so the second-person control the API enforces never ran.
 */
export default function ShiftHistory({ refreshKey }) {
  const { t, language } = useI18n();
  const { can, user } = useAuth();
  const toast = useToast();
  const approver = can("finance.approve");
  const [filter, setFilter] = useState("unreviewed");
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    const params = { page_size: 50 };
    if (filter === "unreviewed") params.unreviewed = 1;
    else if (filter !== "all") params.status = filter;
    cashShifts.list(params).then((r) => setRows(r.data.results ?? r.data)).catch(() => setRows([]));
  }, [filter]);
  useEffect(() => { load(); }, [load, refreshKey]);

  async function review(shift) {
    setBusy(shift.id);
    try {
      await cashShifts.review(shift.id);
      toast.success(t("till.history.reviewed"));
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("till.history.reviewError"));
    } finally { setBusy(null); }
  }

  const fmt = (v) => (v ? new Date(v).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }) : "—");
  const tone = (s) => (s.reviewed_at ? "ok" : s.status === "open" ? "accent" : Number(s.variance) === 0 ? "muted" : "warn");
  const label = (s) => (s.reviewed_at ? t("till.history.signedOff") : s.status === "open" ? t("till.history.open") : t("till.history.awaiting"));

  return (
    <Card className="mt-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
          <History size={18} className="text-accent" />{t("till.history.title")}
          {filter === "unreviewed" && rows?.length > 0 && <Badge tone="warn">{rows.length}</Badge>}
        </h2>
        <div className="w-44">
          <Select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label={t("till.history.filter")}>
            <option value="unreviewed">{t("till.history.filterUnreviewed")}</option>
            <option value="closed">{t("till.history.filterClosed")}</option>
            <option value="open">{t("till.history.filterOpen")}</option>
            <option value="all">{t("till.history.filterAll")}</option>
          </Select>
        </div>
      </div>
      {rows === null ? <p className="p-8 text-center text-muted">{t("common.loading")}</p> : rows.length === 0 ? (
        <p className="p-8 text-center text-muted">{filter === "unreviewed" ? t("till.history.emptyUnreviewed") : t("till.history.empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="px-3 py-2 text-start font-medium">{t("till.history.opened")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("till.history.closed")}</th>
              <th className="px-3 py-2 text-end font-medium">{t("till.expected")}</th>
              <th className="px-3 py-2 text-end font-medium">{t("till.countedCash")}</th>
              <th className="px-3 py-2 text-end font-medium">{t("till.variance")}</th>
              <th className="px-3 py-2 text-start font-medium">{t("common.status")}</th>
              {approver && <th className="px-3 py-2" />}
            </tr></thead>
            <tbody>{rows.map((s) => {
              const mine = s.closed_by_name && user?.full_name === s.closed_by_name;
              const canSign = approver && s.status === "closed" && !s.reviewed_at;
              return (
                <tr key={s.id} className="border-b border-line last:border-0">
                  <td className="px-3 py-2"><div>{fmt(s.opened_at)}</div><div className="text-xs text-muted">{s.opened_by_name || "—"}</div></td>
                  <td className="px-3 py-2"><div>{fmt(s.closed_at)}</div><div className="text-xs text-muted">{s.closed_by_name || "—"}</div></td>
                  <td className="tabular px-3 py-2 text-end">{money(s.expected_cash)}</td>
                  <td className="tabular px-3 py-2 text-end">{s.counted_cash == null ? "—" : money(s.counted_cash)}</td>
                  <td className={`tabular px-3 py-2 text-end font-medium ${s.variance == null || Number(s.variance) === 0 ? "text-muted" : Number(s.variance) < 0 ? "text-danger" : "text-ok"}`}>{s.variance == null ? "—" : money(s.variance)}</td>
                  <td className="px-3 py-2"><Badge tone={tone(s)}>{label(s)}</Badge>{s.reviewed_by_name && <div className="mt-0.5 text-xs text-muted">{s.reviewed_by_name}</div>}</td>
                  {approver && <td className="px-3 py-2 text-end">{canSign && (
                    <Button variant="outline" onClick={() => review(s)} disabled={busy === s.id || mine} title={mine ? t("till.history.ownShift") : undefined}>
                      <BadgeCheck size={15} />{t("till.history.signOff")}
                    </Button>
                  )}</td>}
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
