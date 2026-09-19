"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Field, Input, Select } from "@/components/ui/kit";

// Mirrors inventory.pricing.STEPS on the server.
const STEPS = ["0.01", "1", "5", "10", "50", "100", "500", "1000"];

const fmt = (v) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }));

/**
 * Bulk repricing under inflation: preview first (dry run), then apply. Rate
 * mode rewrites every product that carries a reference (USD) price from
 * today's rate; percent mode scales whatever is selected.
 */
export default function RepriceDrawer({ open, onClose, categories, exchangeRate, referenceCurrency, currency, onApplied }) {
  const { t } = useI18n();
  const [form, setForm] = useState({ mode: "rate", rate: "", percent: "", target: "sale", step: "1", category: "" });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setForm({ mode: "rate", rate: exchangeRate ? String(exchangeRate) : "", percent: "", target: "sale", step: "1", category: "" });
      setPreview(null);
      setError("");
    }
  }, [open, exchangeRate]);

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    setPreview(null);
  };

  function body(dryRun) {
    return {
      mode: form.mode,
      rate: form.mode === "rate" ? form.rate || undefined : undefined,
      percent: form.mode === "percent" ? form.percent : undefined,
      target: form.target,
      step: form.step,
      category: form.category || undefined,
      dry_run: dryRun,
    };
  }

  async function run(dryRun) {
    setError("");
    setBusy(true);
    try {
      const r = await inventory.reprice(body(dryRun));
      if (dryRun) {
        setPreview(r.data);
      } else {
        onApplied?.(r.data);
        onClose();
      }
    } catch (err) {
      const data = err?.response?.data;
      setError(typeof data === "object" && data ? Object.values(data).flat().join(" ") : t("inventory.repriceFailed"));
    } finally {
      setBusy(false);
    }
  }

  const priceKeys = form.target === "both" ? ["sale_price", "cost_price"] : form.target === "cost" ? ["cost_price"] : ["sale_price"];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("inventory.repriceTitle")}
      wide
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="outline" type="button" disabled={busy} onClick={() => run(true)}>
            {t("inventory.repricePreview")}
          </Button>
          <Button type="button" disabled={busy || !preview || !preview.changed} onClick={() => run(false)}>
            <RefreshCw size={16} /> {t("inventory.repriceApply", { count: preview?.changed ?? 0 })}
          </Button>
        </div>
      }
    >
      <p className="mb-4 text-sm text-muted">{t("inventory.repriceHint")}</p>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("inventory.repriceMode")}>
            <Select value={form.mode} onChange={set("mode")}>
              <option value="rate">{t("inventory.repriceByRate", { currency: referenceCurrency || "USD" })}</option>
              <option value="percent">{t("inventory.repriceByPercent")}</option>
            </Select>
          </Field>
          {form.mode === "rate" ? (
            <Field
              label={t("inventory.repriceRate", { currency: referenceCurrency || "USD", local: currency || "" })}
              hint={exchangeRate ? t("inventory.repriceRateHint", { rate: fmt(exchangeRate) }) : t("inventory.repriceNoRate")}
            >
              <Input type="number" inputMode="decimal" min="0" step="0.0001" value={form.rate} onChange={set("rate")} />
            </Field>
          ) : (
            <Field label={t("inventory.repricePercent")} hint={t("inventory.repricePercentHint")}>
              <Input type="number" inputMode="decimal" step="0.1" value={form.percent} onChange={set("percent")} />
            </Field>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("inventory.repriceTarget")}>
            <Select value={form.target} onChange={set("target")}>
              <option value="sale">{t("inventory.salePrice")}</option>
              <option value="cost">{t("inventory.costPrice")}</option>
              <option value="both">{t("inventory.repriceBoth")}</option>
            </Select>
          </Field>
          <Field label={t("inventory.repriceStep")} hint={t("inventory.repriceStepHint")}>
            <Select value={form.step} onChange={set("step")}>
              {STEPS.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </Field>
          <Field label={t("inventory.category")}>
            <Select value={form.category} onChange={set("category")}>
              <option value="">{t("inventory.allCategories")}</option>
              {(categories || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        {preview && (
          <div className="rounded-card border border-line bg-paper p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
              <Badge tone="ok">{t("inventory.repriceWillChange", { count: preview.changed })}</Badge>
              <Badge tone="muted">{t("inventory.repriceMatched", { count: preview.matched })}</Badge>
              {preview.skipped > 0 && <Badge tone="warn">{t("inventory.repriceSkipped", { count: preview.skipped })}</Badge>}
            </div>
            {preview.changed === 0 ? (
              <p className="text-sm text-muted">
                {form.mode === "rate" ? t("inventory.repriceNothingRate") : t("inventory.repriceNothing")}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-muted">
                    <tr>
                      <th className="py-1 text-start font-medium">{t("inventory.product")}</th>
                      {form.mode === "rate" && <th className="py-1 text-end font-medium">{referenceCurrency || "USD"}</th>}
                      <th className="py-1 text-end font-medium">{t("inventory.repriceBefore")}</th>
                      <th className="py-1 text-end font-medium">{t("inventory.repriceAfter")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.map((row) => (
                      <tr key={row.id} className="border-t border-line">
                        <td className="py-1 text-ink">{row.name} <span className="text-muted">{row.sku}</span></td>
                        {form.mode === "rate" && <td className="tabular py-1 text-end">{fmt(row.reference_price)}</td>}
                        <td className="tabular py-1 text-end text-muted">{priceKeys.map((k) => fmt(row.before[k])).join(" / ")}</td>
                        <td className="tabular py-1 text-end font-semibold text-ink">{priceKeys.map((k) => fmt(row.after[k])).join(" / ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.changed > preview.sample.length && (
                  <p className="mt-2 text-xs text-muted">{t("inventory.repriceMore", { count: preview.changed - preview.sample.length })}</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </Drawer>
  );
}
