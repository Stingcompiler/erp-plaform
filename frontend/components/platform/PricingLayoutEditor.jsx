"use client";

// «عرض صفحة الأسعار» on /platform-plans: which layout the public pricing
// page uses, whether the comparison table and the on-server offer show,
// and the billing period it opens on. Saved to /api/platform/pricing-
// display/ (plans.view to read, plans.manage to change).
//
// The preview is not an iframe: it is the pricing page's own PlanShowcase
// over the real public plans (/api/public/plans/), so what the team sees
// here is what a visitor gets. Nothing in this section touches a price.

import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, LayoutTemplate } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { platformSubscriptions, registration } from "@/lib/api";
import { billingCycles, CYCLES, DEFAULT_DISPLAY, PRICING_TEMPLATES, resolveDisplay } from "@/lib/planCatalog";
import { errorText } from "@/lib/errors";
import { Button, Card, Field, Select } from "@/components/ui/kit";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { PlanShowcase, PlansSkeleton } from "@/components/marketing/PlanCards";

// A sketch of each layout, drawn in the current text colour.
function Thumbnail({ template }) {
  const box = "fill-current opacity-15";
  const strong = "fill-current opacity-40";
  const accent = "fill-accent";
  const shapes = {
    classic: <>{[4, 30, 56].map((x) => <rect key={x} x={x} y="8" width="22" height="34" rx="3" className={box} />)}<rect x="30" y="8" width="22" height="4" rx="1.5" className={accent} /></>,
    featured: <><rect x="4" y="12" width="21" height="28" rx="3" className={box} /><rect x="55" y="12" width="21" height="28" rx="3" className={box} /><rect x="28" y="5" width="24" height="40" rx="3" className={strong} /><rect x="28" y="5" width="24" height="4" rx="1.5" className={accent} /></>,
    table: <><rect x="4" y="6" width="72" height="38" rx="3" className={box} />{[18, 26, 34].map((y) => <rect key={y} x="6" y={y} width="68" height="1.5" className={strong} />)}{[26, 43, 60].map((x) => <rect key={x} x={x} y="8" width="12" height="7" rx="1.5" className={x === 43 ? accent : strong} />)}</>,
    compact: <>{[6, 18, 30].map((y) => <g key={y}><rect x="4" y={y} width="72" height="10" rx="2" className={y === 18 ? strong : box} /><rect x="60" y={y + 2.5} width="13" height="5" rx="1.5" className={y === 18 ? accent : strong} /></g>)}</>,
  };
  return <svg viewBox="0 0 80 50" className="h-14 w-full text-ink" aria-hidden="true">{shapes[template]}</svg>;
}

function Toggle({ checked, onChange, disabled, label, hint }) {
  return (
    <label className={`flex items-start gap-2 text-sm ${disabled ? "opacity-60" : ""}`}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} disabled={disabled} className="mt-0.5 accent-accent" />
      <span>
        {label}
        {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
      </span>
    </label>
  );
}

export default function PricingLayoutEditor({ canManage }) {
  const { t, href } = useI18n();
  const confirm = useConfirm();
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState(DEFAULT_DISPLAY);
  const [rows, setRows] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    platformSubscriptions.pricingDisplay()
      .then((response) => {
        if (cancelled) return;
        const value = resolveDisplay(response.data);
        setSaved(value); setDraft(value);
      })
      .catch(() => { if (!cancelled) { setSaved(DEFAULT_DISPLAY); setMessage({ tone: "danger", text: t("platformPlans.layoutLoadError") }); } });
    registration.publicPlans()
      .then((response) => { if (!cancelled) setRows(response.data || []); })
      .catch(() => { if (!cancelled) setRows([]); });
    return () => { cancelled = true; };
  }, [t]);

  const dirty = saved !== null && JSON.stringify(draft) !== JSON.stringify(saved);
  // Closing or reloading the tab with unsaved changes asks first.
  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const set = useCallback((key, value) => { setMessage(null); setDraft((current) => ({ ...current, [key]: value })); }, []);
  const cycles = useMemo(() => billingCycles(rows), [rows]);
  const preview = useMemo(() => resolveDisplay(draft), [draft]);

  const save = async () => {
    setSaving(true); setMessage(null);
    try {
      const response = await platformSubscriptions.updatePricingDisplay(draft);
      const value = resolveDisplay(response.data);
      setSaved(value); setDraft(value);
      try { sessionStorage.removeItem("vezano.pricingDisplay.v1"); } catch { /* private mode */ }
      setMessage({ tone: "ok", text: t("platformPlans.layoutSaved") });
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, t, "platformPlans.layoutSaveError") });
    } finally {
      setSaving(false);
    }
  };
  const discard = async () => {
    if (!(await confirm(t("platformPlans.layoutDiscardConfirm")))) return;
    setDraft(saved); setMessage(null);
  };

  const locked = !canManage || saved === null;
  return (
    <Card className="mt-8 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold"><LayoutTemplate size={18} aria-hidden="true" />{t("platformPlans.layoutTitle")}</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("platformPlans.layoutSubtitle")}</p>
        </div>
        <a href={href("/pricing")} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
          {t("platformPlans.layoutOpenPage")} <ExternalLink size={14} aria-hidden="true" />
        </a>
      </div>
      {!canManage && <p className="mt-3 text-sm text-muted">{t("platformPlans.layoutReadOnly")}</p>}

      <fieldset className="mt-5" disabled={locked}>
        <legend className="mb-2 text-sm font-medium text-ink">{t("platformPlans.layoutTemplate")}</legend>
        <div role="radiogroup" aria-label={t("platformPlans.layoutTemplate")} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {PRICING_TEMPLATES.map((template) => {
            const active = draft.template === template;
            return (
              <button
                key={template}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => set("template", template)}
                className={`rounded-control border p-3 text-start transition-colors disabled:cursor-not-allowed ${active ? "border-accent bg-accent/5 ring-1 ring-accent" : "border-line bg-paper hover:border-accent"}`}
              >
                <Thumbnail template={template} />
                <span className="mt-2 block text-sm font-medium text-ink">{t(`platformPlans.layoutTemplates.${template}.name`)}</span>
                <span className="mt-0.5 block text-xs text-muted">{t(`platformPlans.layoutTemplates.${template}.hint`)}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <Toggle
            checked={draft.template === "table" ? true : draft.show_compare}
            disabled={locked || draft.template === "table"}
            onChange={(value) => set("show_compare", value)}
            label={t("platformPlans.layoutShowCompare")}
            hint={draft.template === "table" ? t("platformPlans.layoutShowCompareTable") : null}
          />
          <Toggle
            checked={draft.show_self_hosted}
            disabled={locked}
            onChange={(value) => set("show_self_hosted", value)}
            label={t("platformPlans.layoutShowSelfHosted")}
            hint={t("platformPlans.layoutShowSelfHostedHint")}
          />
          <Field label={t("platformPlans.layoutDefaultCycle")} hint={cycles.length ? t("platformPlans.layoutDefaultCycleHint") : t("platformPlans.layoutNoCycles")}>
            <Select value={draft.default_cycle} onChange={(event) => set("default_cycle", event.target.value)} disabled={locked}>
              {CYCLES.map((cycle) => <option key={cycle} value={cycle}>{t(`platformPlans.${cycle}`)}</option>)}
            </Select>
          </Field>
        </div>
      </fieldset>

      {canManage && (
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <Button type="button" onClick={save} disabled={!dirty || saving}>{saving ? t("common.saving") : t("common.save")}</Button>
          {dirty && <Button type="button" variant="outline" onClick={discard}>{t("platformPlans.layoutDiscard")}</Button>}
          {dirty && <span className="text-sm text-warn">{t("platformPlans.layoutUnsaved")}</span>}
        </div>
      )}
      {message && <p role={message.tone === "danger" ? "alert" : "status"} className={`mt-3 text-sm ${message.tone === "danger" ? "text-danger" : "text-ok"}`}>{message.text}</p>}

      <section className="mt-6 border-t border-line pt-5" aria-label={t("platformPlans.layoutPreview")}>
        <h3 className="font-display font-semibold">{t("platformPlans.layoutPreview")}</h3>
        <p className="mt-1 text-xs text-muted">{t("platformPlans.layoutPreviewHint")}</p>
        <div className="mt-4 rounded-card border border-dashed border-line bg-surface p-3 sm:p-5">
          {rows === null ? <PlansSkeleton bleed={false} selfHosted={preview.show_self_hosted} /> : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">{t("platformPlans.layoutPreviewEmpty")}</p>
          ) : (
            // Re-mounted on a new default period so the preview opens on it.
            <PlanShowcase key={preview.default_cycle} rows={rows} display={preview} persistCycle={false} bleed={false} />
          )}
        </div>
      </section>
    </Card>
  );
}
