"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock, Pencil, Plus, SlidersHorizontal } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformSubscriptions } from "@/lib/api";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import ModulePicker, { moduleLabel } from "@/components/platform/ModulePicker";
import { normalizeModules } from "@/lib/planModules";

const COPY_KEYS = ["name_ar", "tagline_en", "tagline_ar", "features_en", "features_ar", "is_highlighted", "sort_order"];
const EMPTY_COPY = { name_ar: "", tagline_en: "", tagline_ar: "", features_en: "", features_ar: "", is_highlighted: false, sort_order: 100 };
const EMPTY = { code: "", name: "", description: "", currency: "USD", price: "", billing_cycle: "monthly", modules: ["inventory", "sales"], users: "", branches: "", warehouses: "", devices: "", addon_devices: "", addon_users: "", ...EMPTY_COPY };

function copyFrom(form) {
  return Object.fromEntries(COPY_KEYS.map((key) => [key, key === "sort_order" ? Number(form[key]) || 100 : form[key]]));
}

// The marketing copy the public pricing page reads. Shared by the create
// form and the per-plan editor so both write the same fields.
function CopyFields({ value, onChange, t }) {
  const set = (key) => (event) => onChange({ ...value, [key]: event.target.type === "checkbox" ? event.target.checked : event.target.value });
  const area = "w-full rounded-control border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent";
  return <div className="grid gap-4 md:grid-cols-2"><Field label={t("platformPlans.nameAr")}><Input value={value.name_ar} onChange={set("name_ar")} /></Field><Field label={t("platformPlans.sortOrder")} hint={t("platformPlans.sortOrderHint")}><Input type="number" min="0" value={value.sort_order} onChange={set("sort_order")} /></Field><Field label={t("platformPlans.taglineEn")}><Input maxLength={160} value={value.tagline_en} onChange={set("tagline_en")} /></Field><Field label={t("platformPlans.taglineAr")}><Input maxLength={160} value={value.tagline_ar} onChange={set("tagline_ar")} /></Field><Field label={t("platformPlans.featuresEn")} hint={t("platformPlans.featuresHint")}><textarea rows={4} value={value.features_en} onChange={set("features_en")} className={area} /></Field><Field label={t("platformPlans.featuresAr")} hint={t("platformPlans.featuresHint")}><textarea rows={4} value={value.features_ar} onChange={set("features_ar")} className={area} dir="rtl" /></Field><label className="flex items-center gap-2 text-sm md:col-span-2"><input type="checkbox" checked={Boolean(value.is_highlighted)} onChange={set("is_highlighted")} className="accent-accent" />{t("platformPlans.highlighted")}</label></div>;
}

// The newest version of a plan (highest number), or null.
function latestVersion(plan) {
  return [...(plan.versions || [])].sort((a, b) => b.version - a.version)[0] || null;
}

// Every field of the plan and of its current version in one form. Plan
// fields are patched in place; pricing, cycle, modules and limits belong
// to a version, and a published version is immutable (subscriptions point
// at it), so a change there is saved as a new published version.
function PlanEditor({ plan, onSaved, t }) {
  const latest = latestVersion(plan);
  const initial = () => ({
    code: plan.code, name: plan.name, description: plan.description || "",
    is_public: plan.is_public !== false, is_active: plan.is_active !== false,
    ...EMPTY_COPY, ...Object.fromEntries(COPY_KEYS.map((key) => [key, plan[key] ?? EMPTY_COPY[key]])),
    currency: latest?.currency || "USD", price: latest ? String(latest.price) : "",
    billing_cycle: latest?.billing_cycle || "monthly", modules: latest?.modules || [],
    users: latest?.limits?.users ?? "", branches: latest?.limits?.branches ?? "", warehouses: latest?.limits?.warehouses ?? "", devices: latest?.limits?.devices ?? "", addon_devices: latest?.addon_prices?.devices ?? "", addon_users: latest?.addon_prices?.users ?? "",
  });
  const [open, setOpen] = useState(false); const [value, setValue] = useState(initial); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const set = (key) => (event) => setValue((current) => ({ ...current, [key]: event.target.type === "checkbox" ? event.target.checked : event.target.value }));
  const versionChanged = () => !latest
    || value.currency !== latest.currency || Number(value.price) !== Number(latest.price) || value.billing_cycle !== latest.billing_cycle
    || JSON.stringify(normalizeModules(value.modules)) !== JSON.stringify(normalizeModules(latest.modules || []))
    || JSON.stringify(limitsFrom(value)) !== JSON.stringify(latest.limits || {})
    || JSON.stringify(addonPricesFrom(value)) !== JSON.stringify(latest.addon_prices || {});
  const save = async (event) => {
    event.preventDefault(); setSaving(true); setError("");
    try {
      await platformSubscriptions.updatePlan(plan.id, { code: value.code.trim(), name: value.name.trim(), description: value.description.trim(), is_public: value.is_public, is_active: value.is_active, ...copyFrom(value) });
      if (versionChanged()) {
        await platformSubscriptions.createPlanVersion({ plan: plan.id, version: (latest?.version || 0) + 1, currency: value.currency, price: Number(value.price), billing_cycle: value.billing_cycle, modules: normalizeModules(value.modules), limits: limitsFrom(value), addon_prices: addonPricesFrom(value), published_at: new Date().toISOString() });
      }
      setOpen(false); await onSaved();
    } catch (requestError) { const data = requestError?.response?.data; const message = data?.detail || (data && Object.values(data).flat()[0]); setError(typeof message === "string" ? message : t("platformPlans.saveError")); } finally { setSaving(false); }
  };
  if (!open) return <Button type="button" variant="outline" onClick={() => { setValue(initial()); setOpen(true); }}><Pencil size={15} />{t("platformPlans.editPlan")}</Button>;
  return <form onSubmit={save} className="mt-4 space-y-5 rounded-control border border-line bg-paper p-4">
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <h3 className="font-display font-semibold">{t("platformPlans.planFields")}</h3>
    <div className="grid gap-4 md:grid-cols-2">
      <Field label={t("platformPlans.code")}><Input required value={value.code} onChange={set("code")} dir="ltr" /></Field>
      <Field label={t("platformPlans.name")}><Input required value={value.name} onChange={set("name")} /></Field>
      <div className="md:col-span-2"><Field label={t("platformPlans.description")}><textarea value={value.description} onChange={set("description")} className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent" rows={2} /></Field></div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.is_public} onChange={set("is_public")} className="accent-accent" />{t("platformPlans.isPublic")}</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.is_active} onChange={set("is_active")} className="accent-accent" />{t("platformPlans.isActive")}</label>
    </div>
    <h3 className="font-display font-semibold">{t("platformPlans.versionFields")}</h3>
    <p className="-mt-3 text-xs text-muted">{latest ? t("platformPlans.versionHint", { version: latest.version }) : t("platformPlans.noVersionHint")}</p>
    <div className="grid gap-4 md:grid-cols-2">
      <Field label={t("platformPlans.currency")}><Input required maxLength={8} value={value.currency} onChange={set("currency")} dir="ltr" /></Field>
      <Field label={t("platformPlans.price")}><Input required type="number" min="0" step="0.01" value={value.price} onChange={set("price")} /></Field>
      <Field label={t("platformPlans.cycle")}><Select value={value.billing_cycle} onChange={set("billing_cycle")}><option value="monthly">{t("platformPlans.monthly")}</option><option value="yearly">{t("platformPlans.yearly")}</option></Select></Field>
      <div className="md:col-span-2"><Field label={t("platformPlans.modules")} hint={t("platformPlans.modulesHint")}><ModulePicker value={value.modules} onChange={(modules) => setValue((current) => ({ ...current, modules }))} /></Field></div>
      <Field label={t("platformPlans.users")}><Input type="number" min="0" value={value.users} onChange={set("users")} /></Field>
      <Field label={t("platformPlans.branches")}><Input type="number" min="0" value={value.branches} onChange={set("branches")} /></Field>
      <Field label={t("platformPlans.warehouses")}><Input type="number" min="0" value={value.warehouses} onChange={set("warehouses")} /></Field>
      <Field label={t("platformPlans.devices")}><Input type="number" min="0" value={value.devices} onChange={set("devices")} /></Field>
      <Field label={t("platformPlans.addonDevices")} hint={t("platformPlans.addonHint")}><Input type="number" min="0" step="0.01" value={value.addon_devices} onChange={set("addon_devices")} /></Field>
      <Field label={t("platformPlans.addonUsers")}><Input type="number" min="0" step="0.01" value={value.addon_users} onChange={set("addon_users")} /></Field>
    </div>
    <h3 className="font-display font-semibold">{t("platformPlans.publicCopy")}</h3>
    <CopyFields value={value} onChange={setValue} t={t} />
    <div className="flex gap-2"><Button type="submit" disabled={saving || normalizeModules(value.modules).length === 0}>{saving ? t("common.saving") : versionChanged() ? t("platformPlans.saveAndPublishVersion") : t("common.save")}</Button><Button type="button" variant="outline" onClick={() => setOpen(false)}>{t("common.cancel")}</Button></div>
  </form>;
}

function limitsFrom(form) {
  return Object.fromEntries(["users", "branches", "warehouses", "devices"].filter((key) => form[key] !== "").map((key) => [key, Number(form[key])]));
}
function addonPricesFrom(form) {
  return Object.fromEntries(["devices", "users"].filter((key) => form[`addon_${key}`] !== "").map((key) => [key, String(form[`addon_${key}`])]));
}

// Plan limits are stored by their API key; show them in the reader's words.
const LIMIT_LABEL = {
  users: "platformPlans.users",
  branches: "platformPlans.branches",
  warehouses: "platformPlans.warehouses",
  devices: "platformPlans.devices",
};

export default function PlatformPlansPage() {
  const { user, can } = useAuth();
  const canView = can("platform.plans.view");
  const canManagePlans = can("platform.plans.manage");
  const { t } = useI18n();
  const [plans, setPlans] = useState([]); const [draft, setDraft] = useState(EMPTY); const [open, setOpen] = useState(false); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  const load = useCallback(async () => { if (!canView) return; try { const response = await platformSubscriptions.plans(); setPlans(response.data.results || response.data); } catch { setError(t("platformPlans.loadError")); } }, [t, canView]);
  useEffect(() => { load(); }, [load]);
  const set = (key) => (event) => setDraft((current) => ({ ...current, [key]: event.target.value }));
  const create = async (event) => { event.preventDefault(); setSaving(true); setError(""); try { const plan = await platformSubscriptions.createPlan({ code: draft.code.trim(), name: draft.name.trim(), description: draft.description.trim(), is_public: true, is_active: true, ...copyFrom(draft) }); await platformSubscriptions.createPlanVersion({ plan: plan.data.id, version: 1, currency: draft.currency, price: Number(draft.price), billing_cycle: draft.billing_cycle, modules: normalizeModules(draft.modules), limits: limitsFrom(draft), addon_prices: addonPricesFrom(draft), published_at: new Date().toISOString() }); setDraft(EMPTY); setOpen(false); await load(); } catch (requestError) { const data = requestError?.response?.data; const message = data?.detail || (data && Object.values(data).flat()[0]); setError(typeof message === "string" ? message : t("platformPlans.saveError")); } finally { setSaving(false); } };
  if (!canView) return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("platformPlans.noAccess")}</p></Card>;
  return <div><PageHeader title={t("platformPlans.title")} subtitle={t("platformPlans.subtitle")} actions={canManagePlans && <Button onClick={() => setOpen((current) => !current)}><Plus size={16} />{t("platformPlans.newPlan")}</Button>} />{error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}{open && <Card className="mb-5 p-5"><form onSubmit={create} className="space-y-4"><h2 className="font-display text-lg font-semibold">{t("platformPlans.newPlan")}</h2><div className="grid gap-4 md:grid-cols-2"><Field label={t("platformPlans.code")}><Input required value={draft.code} onChange={set("code")} /></Field><Field label={t("platformPlans.name")}><Input required value={draft.name} onChange={set("name")} /></Field><Field label={t("platformPlans.currency")}><Input required maxLength={8} value={draft.currency} onChange={set("currency")} /></Field><Field label={t("platformPlans.price")}><Input required type="number" min="0" step="0.01" value={draft.price} onChange={set("price")} /></Field><Field label={t("platformPlans.cycle")}><Select value={draft.billing_cycle} onChange={set("billing_cycle")}><option value="monthly">{t("platformPlans.monthly")}</option><option value="yearly">{t("platformPlans.yearly")}</option></Select></Field><div className="md:col-span-2"><Field label={t("platformPlans.modules")} hint={t("platformPlans.modulesHint")}><ModulePicker value={draft.modules} onChange={(modules) => setDraft((current) => ({ ...current, modules }))} /></Field></div><Field label={t("platformPlans.users")}><Input type="number" min="0" value={draft.users} onChange={set("users")} /></Field><Field label={t("platformPlans.branches")}><Input type="number" min="0" value={draft.branches} onChange={set("branches")} /></Field><Field label={t("platformPlans.warehouses")}><Input type="number" min="0" value={draft.warehouses} onChange={set("warehouses")} /></Field><Field label={t("platformPlans.devices")}><Input type="number" min="0" value={draft.devices} onChange={set("devices")} /></Field><Field label={t("platformPlans.addonDevices")} hint={t("platformPlans.addonHint")}><Input type="number" min="0" step="0.01" value={draft.addon_devices} onChange={set("addon_devices")} /></Field><Field label={t("platformPlans.addonUsers")}><Input type="number" min="0" step="0.01" value={draft.addon_users} onChange={set("addon_users")} /></Field></div><Field label={t("platformPlans.description")}><textarea value={draft.description} onChange={set("description")} className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent" rows={3} /></Field><h3 className="font-display font-semibold">{t("platformPlans.publicCopy")}</h3><CopyFields value={draft} onChange={setDraft} t={t} /><div className="flex gap-2"><Button type="submit" disabled={saving || normalizeModules(draft.modules).length === 0}>{saving ? t("common.saving") : t("platformPlans.createAndPublish")}</Button><Button type="button" variant="outline" onClick={() => setOpen(false)}>{t("common.cancel")}</Button></div></form></Card>}<div className="grid gap-4 lg:grid-cols-2">{plans.map((plan) => <Card key={plan.id} className="p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="font-display text-lg font-semibold">{plan.name}</h2><p className="mt-1 text-sm text-muted">{plan.description || t("platformPlans.noDescription")}</p></div><Badge tone={plan.is_active ? "ok" : "muted"}>{plan.is_active ? t("platformPlans.active") : t("platformPlans.archived")}</Badge></div>{(plan.name_ar || plan.tagline_en) && <p className="mt-2 text-sm text-muted">{plan.name_ar}{plan.name_ar && plan.tagline_en ? " · " : ""}{plan.tagline_en}</p>}{plan.is_highlighted && <Badge tone="accent">{t("platformPlans.highlighted")}</Badge>}<div className="mt-4 space-y-2">{(plan.versions || []).map((version) => <div key={version.id} className="rounded-control bg-paper p-3 text-sm"><div className="font-medium">v{version.version} · {version.price} {version.currency} · {t(`platformPlans.${version.billing_cycle}`)}{latestVersion(plan)?.id === version.id && <Badge tone="accent">{t("platformPlans.current")}</Badge>}</div><div className="mt-1 text-muted">{(version.modules || []).map((code) => moduleLabel(code, t)).join(" · ") || "—"}</div><div className="mt-1 text-xs text-muted">{Object.entries(version.limits || {}).map(([key, value]) => `${LIMIT_LABEL[key] ? t(LIMIT_LABEL[key]) : key}: ${value}`).join(" · ") || t("platformPlans.noLimits")}</div></div>)}</div>{canManagePlans && <div className="mt-4"><PlanEditor plan={plan} onSaved={load} t={t} /></div>}</Card>)}{!plans.length && <Card className="p-10 text-center lg:col-span-2"><SlidersHorizontal className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("platformPlans.empty")}</p></Card>}</div></div>;
}
