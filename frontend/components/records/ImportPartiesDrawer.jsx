"use client";

import { useState } from "react";
import { Download, FileSpreadsheet, Upload } from "lucide-react";

import { purchasing, sales } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button } from "@/components/ui/kit";

const TONE = { created: "ok", updated: "accent", skipped: "muted", error: "danger" };

function templateCsv(kind, t) {
  const header = kind === "customer"
    ? [t("importParties.colName"), t("importParties.colPhone"), t("importParties.colEmail"), t("importParties.colAddress"), t("importParties.colBalance"), t("importParties.colTerms")]
    : [t("importParties.colName"), t("importParties.colPhone"), t("importParties.colEmail"), t("importParties.colAddress"), t("importParties.colBalance")];
  const blob = new Blob([`\ufeff${header.join(",")}\n`], { type: "text/csv;charset=utf-8" });
  return URL.createObjectURL(blob);
}

/**
 * Bring an existing ledger in from Excel: pick the file, see exactly what
 * each row will do (create / update / skip / error) before anything is
 * written, then import. Re-importing the same sheet updates rather than
 * duplicates, so a corrected file can simply be run again.
 */
export default function ImportPartiesDrawer({ kind, open, onClose, onImported }) {
  const { t } = useI18n();
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const call = kind === "customer" ? sales.importCustomers : purchasing.importSuppliers;

  function reset() { setFile(null); setPreview(null); setError(""); }

  async function run(dryRun) {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const r = await call(file, dryRun);
      if (dryRun) setPreview(r.data);
      else {
        toast.success(t("importParties.done", r.data.summary));
        onImported?.();
        reset();
        onClose();
      }
    } catch (err) {
      const data = err?.response?.data;
      setError((data && (data.file?.join?.(" ") || data.detail)) || t("importParties.failed"));
    } finally { setBusy(false); }
  }

  const s = preview?.summary;
  return (
    <Drawer open={open} onClose={() => { reset(); onClose(); }} title={t(kind === "customer" ? "importParties.customersTitle" : "importParties.suppliersTitle")} wide
      footer={<div className="flex flex-wrap items-center justify-between gap-2">
        <a href={open ? templateCsv(kind, t) : "#"} download={`vezano-${kind}s-template.csv`} className="inline-flex items-center gap-1 text-sm text-accent hover:underline"><Download size={14} />{t("importParties.template")}</a>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => { reset(); onClose(); }}>{t("common.cancel")}</Button>
          {!preview ? (
            <Button onClick={() => run(true)} disabled={!file || busy}>{busy ? t("importParties.checking") : t("importParties.preview")}</Button>
          ) : (
            <Button onClick={() => run(false)} disabled={busy || (s.created + s.updated) === 0}>{busy ? t("common.saving") : t("importParties.confirm", { n: s.created + s.updated })}</Button>
          )}
        </div>
      </div>}>
      <div className="space-y-4">
        <p className="text-sm text-muted">{t("importParties.hint")}</p>
        <label className="flex cursor-pointer items-center gap-3 rounded-control border border-dashed border-line bg-paper p-4 text-sm hover:border-accent/50">
          <FileSpreadsheet size={22} className="text-accent" />
          <span className="min-w-0 flex-1 truncate">{file ? file.name : t("importParties.choose")}</span>
          <Upload size={16} className="text-muted" />
          <input type="file" accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); setError(""); }} />
        </label>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        {preview && (
          <>
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge tone="ok">{t("importParties.created", { n: s.created })}</Badge>
              <Badge tone="accent">{t("importParties.updated", { n: s.updated })}</Badge>
              {s.balances > 0 && <Badge tone="warn">{t("importParties.balances", { n: s.balances })}</Badge>}
              {s.skipped > 0 && <Badge tone="muted">{t("importParties.skipped", { n: s.skipped })}</Badge>}
              {s.errors > 0 && <Badge tone="danger">{t("importParties.errors", { n: s.errors })}</Badge>}
            </div>
            <div className="max-h-[50vh] overflow-auto rounded-control border border-line">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                  <th className="px-3 py-2 text-start font-medium">#</th>
                  <th className="px-3 py-2 text-start font-medium">{t("importParties.colName")}</th>
                  <th className="px-3 py-2 text-start font-medium">{t("importParties.colPhone")}</th>
                  <th className="px-3 py-2 text-start font-medium">{t("common.status")}</th>
                  <th className="px-3 py-2 text-start font-medium">{t("importParties.note")}</th>
                </tr></thead>
                <tbody>{preview.rows.map((r) => (
                  <tr key={r.row} className="border-b border-line last:border-0">
                    <td className="tabular px-3 py-2 text-muted">{r.row}</td>
                    <td className="px-3 py-2">{r.name || "—"}</td>
                    <td className="tabular px-3 py-2 text-muted">{r.phone || "—"}</td>
                    <td className="px-3 py-2"><Badge tone={TONE[r.status]}>{t(`importParties.status.${r.status}`)}</Badge></td>
                    <td className="px-3 py-2 text-xs text-muted">{[r.balance ? t("importParties.balanceOf", { amount: r.balance }) : null, r.message].filter(Boolean).join(" · ") || "—"}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Drawer>
  );
}
