"use client";

// The platform team's SEO control page: site-wide settings (verification
// tags, analytics id, default share image, extra robots lines) and a table
// of per-path overrides (title, description, noindex, canonical). Django
// applies both while serving the public pages, so a save is live at once.
import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Eye, EyeOff, Globe, Lock, MessageCircle, Pencil, Plus, SearchCheck, Trash2 } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformSeo } from "@/lib/api";
import { SITE_URL } from "@/lib/site";
import ImagePicker from "@/components/website/ImagePicker";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";

const SETTINGS_FIELDS = ["google_site_verification", "bing_site_verification", "analytics_id", "robots_extra", "support_whatsapp", "support_phone", "support_email"];
const EMPTY_OVERRIDE = { path: "/", language: "both", title: "", description: "", noindex: false, canonical: "" };
const TITLE_LIMIT = 60;
const DESCRIPTION_LIMIT = 160;

const TEXTAREA = "w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent disabled:opacity-60";

// The address a visitor would see for an override, in the edition it applies to.
function pageUrl(path, language) {
  const clean = path === "/" ? "/" : `${path.replace(/\/+$/, "")}/`;
  return `${SITE_URL}${language === "en" ? "/en" : ""}${clean}`;
}

function clip(text, limit) {
  return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}

// How a search engine would list the page with this override applied.
function SerpPreview({ form, t }) {
  const url = pageUrl(form.path || "/", form.language);
  return (
    <div className="rounded-control border border-line bg-paper p-4" dir="auto">
      <p className="text-xs text-muted">{t("platformSeo.previewHint")}</p>
      <div className="mt-2 font-sans">
        <div className="flex items-center gap-2 text-xs text-muted"><Globe size={12} /><span className="truncate">{url}</span></div>
        <div className="mt-0.5 text-lg leading-snug text-[#1a0dab] dark:text-[#8ab4f8]">
          {form.title ? clip(form.title, TITLE_LIMIT) : <span className="italic text-muted">{t("platformSeo.previewTitleFallback")}</span>}
        </div>
        <div className="mt-0.5 text-sm text-ink/80">
          {form.description ? clip(form.description, DESCRIPTION_LIMIT) : <span className="italic text-muted">{t("platformSeo.previewDescriptionFallback")}</span>}
        </div>
        {form.noindex && <p className="mt-2 text-xs font-medium text-danger">{t("platformSeo.previewNoindex")}</p>}
      </div>
    </div>
  );
}

export default function PlatformSeoPage() {
  const { can } = useAuth();
  const { t, language } = useI18n();
  const canView = can("platform.seo.view");
  const canManage = can("platform.seo.manage");

  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState(null);
  const [overrides, setOverrides] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState(null); // null | "new" | id
  const [draft, setDraft] = useState(EMPTY_OVERRIDE);
  const [showPreview, setShowPreview] = useState(false);

  const load = useCallback(async () => {
    if (!canView) { setLoading(false); return; }
    setLoading(true);
    setError("");
    try {
      const [settingsResponse, overridesResponse] = await Promise.all([platformSeo.settings(), platformSeo.overrides()]);
      setSettings(settingsResponse.data);
      setForm(Object.fromEntries(SETTINGS_FIELDS.map((key) => [key, settingsResponse.data[key] || ""])));
      const list = overridesResponse.data;
      setOverrides(Array.isArray(list) ? list : list.results || []);
    } catch (requestError) {
      const status = requestError?.response?.status;
      setError([t("platformSeo.loadError"), status && `HTTP ${status}`].filter(Boolean).join(" · "));
    } finally {
      setLoading(false);
    }
  }, [t, canView]);
  useEffect(() => { load(); }, [load]);

  const fail = (requestError) => {
    const data = requestError?.response?.data;
    const first = data?.detail
      || ["path", "title", "description", "canonical", "analytics_id", "google_site_verification", "bing_site_verification", "image"]
        .map((key) => data?.[key]?.[0]).find(Boolean)
      || (Array.isArray(data) ? data[0] : null);
    setError(typeof first === "string" ? first : t("platformSeo.saveError"));
  };
  const flash = (message) => {
    setNotice(message);
    setTimeout(() => setNotice(""), 2500);
  };

  const saveSettings = async (event) => {
    event.preventDefault();
    setSaving("settings");
    setError("");
    try {
      const response = await platformSeo.updateSettings(form);
      setSettings(response.data);
      flash(t("platformSeo.saved"));
    } catch (requestError) {
      fail(requestError);
    } finally {
      setSaving(null);
    }
  };

  const uploadImage = async (file) => {
    const response = await platformSeo.uploadOgImage(file);
    setSettings(response.data);
  };
  const removeImage = async () => {
    const response = await platformSeo.removeOgImage();
    setSettings(response.data);
  };

  const startEdit = (row) => {
    setEditing(row ? row.id : "new");
    setDraft(row ? { path: row.path, language: row.language, title: row.title, description: row.description, noindex: row.noindex, canonical: row.canonical } : EMPTY_OVERRIDE);
    setShowPreview(false);
    setError("");
  };
  const cancelEdit = () => { setEditing(null); setDraft(EMPTY_OVERRIDE); };

  const submitOverride = async (event) => {
    event.preventDefault();
    setSaving("override");
    setError("");
    try {
      if (editing === "new") await platformSeo.createOverride(draft);
      else await platformSeo.updateOverride(editing, draft);
      cancelEdit();
      flash(t("platformSeo.saved"));
      await load();
    } catch (requestError) {
      fail(requestError);
    } finally {
      setSaving(null);
    }
  };

  const removeOverride = async (row) => {
    if (!window.confirm(t("platformSeo.confirmDelete", { path: row.path }))) return;
    setSaving(`delete-${row.id}`);
    setError("");
    try {
      await platformSeo.deleteOverride(row.id);
      if (editing === row.id) cancelEdit();
      await load();
    } catch (requestError) {
      fail(requestError);
    } finally {
      setSaving(null);
    }
  };

  const fmt = (value) => new Date(value).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" });
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });
  const setDraftField = (key) => (event) => setDraft({ ...draft, [key]: event.target.type === "checkbox" ? event.target.checked : event.target.value });

  if (!canView) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">{t("platformSeo.noAccess")}</p>
      </Card>
    );
  }

  const overrideForm = (
    <form onSubmit={submitOverride} className="mt-4 grid gap-3 rounded-control border border-accent/30 bg-accent/5 p-4">
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
        <Field label={t("platformSeo.path")} hint={t("platformSeo.pathHint")}>
          <Input required dir="ltr" value={draft.path} onChange={setDraftField("path")} placeholder="/pricing" />
        </Field>
        <Field label={t("platformSeo.language")}>
          <Select value={draft.language} onChange={setDraftField("language")}>
            {["both", "ar", "en"].map((code) => <option key={code} value={code}>{t(`platformSeo.languages.${code}`)}</option>)}
          </Select>
        </Field>
      </div>
      <Field label={t("platformSeo.titleField")} hint={t("platformSeo.titleHint", { count: draft.title.length })}>
        <Input maxLength={255} value={draft.title} onChange={setDraftField("title")} />
      </Field>
      <Field label={t("platformSeo.description")} hint={t("platformSeo.descriptionHint", { count: draft.description.length })}>
        <textarea rows={3} maxLength={400} value={draft.description} onChange={setDraftField("description")} className={TEXTAREA} />
      </Field>
      <Field label={t("platformSeo.canonical")} hint={t("platformSeo.canonicalHint")}>
        <Input dir="ltr" type="url" maxLength={500} value={draft.canonical} onChange={setDraftField("canonical")} placeholder="https://vezano.app/…" />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.noindex} onChange={setDraftField("noindex")} className="h-4 w-4 accent-accent" />
        {t("platformSeo.noindex")}
      </label>
      {showPreview && <SerpPreview form={draft} t={t} />}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={saving === "override"}>
          {saving === "override" ? t("platformSeo.saving") : editing === "new" ? t("platformSeo.create") : t("platformSeo.update")}
        </Button>
        <Button type="button" variant="outline" onClick={() => setShowPreview((value) => !value)}>
          {showPreview ? <EyeOff size={15} /> : <Eye size={15} />}
          {showPreview ? t("platformSeo.hidePreview") : t("platformSeo.preview")}
        </Button>
        <Button type="button" variant="ghost" onClick={cancelEdit}>{t("platformSeo.cancel")}</Button>
      </div>
    </form>
  );

  return (
    <div>
      <PageHeader
        title={t("platformSeo.title")}
        subtitle={t("platformSeo.subtitle")}
        actions={<Badge tone="accent">{t("platformSeo.overridesCount", { count: overrides.length })}</Badge>}
      />
      {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {notice && <p role="status" className="mb-4 rounded-control bg-ok/10 p-3 text-sm text-ok">{notice}</p>}
      {!canManage && (
        <p className="mb-4 rounded-control border border-line bg-surface p-3 text-sm text-muted">{t("platformSeo.readOnlyNotice")}</p>
      )}

      {loading || !form ? (
        <Card className="p-8 text-center text-muted">{t("common.loading")}</Card>
      ) : (
        <>
          <Card className="mb-5 p-5">
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent"><SearchCheck size={20} /></span>
              <div className="min-w-0 flex-1">
                <h2 className="font-display font-semibold">{t("platformSeo.siteCard")}</h2>
                <p className="mt-1 text-sm text-muted">{t("platformSeo.siteHint")}</p>
                <form onSubmit={saveSettings} className="mt-4 grid gap-4 lg:grid-cols-[1fr_320px]">
                  <div className="grid gap-3">
                    <Field label={t("platformSeo.googleVerification")} hint={t("platformSeo.googleVerificationHint")}>
                      <Input dir="ltr" maxLength={255} value={form.google_site_verification} onChange={set("google_site_verification")} disabled={!canManage} />
                    </Field>
                    <Field label={t("platformSeo.bingVerification")} hint={t("platformSeo.bingVerificationHint")}>
                      <Input dir="ltr" maxLength={255} value={form.bing_site_verification} onChange={set("bing_site_verification")} disabled={!canManage} />
                    </Field>
                    <Field label={t("platformSeo.analyticsId")} hint={t("platformSeo.analyticsIdHint")}>
                      <Input dir="ltr" maxLength={64} value={form.analytics_id} onChange={set("analytics_id")} disabled={!canManage} placeholder="G-XXXXXXXXXX" />
                    </Field>
                    <Field label={t("platformSeo.robotsExtra")} hint={t("platformSeo.robotsExtraHint")}>
                      <textarea dir="ltr" rows={3} value={form.robots_extra} onChange={set("robots_extra")} disabled={!canManage} className={`${TEXTAREA} font-mono`} />
                    </Field>
                    {canManage && (
                      <div className="flex items-center gap-3">
                        <Button type="submit" disabled={saving === "settings"}>
                          {saving === "settings" ? t("platformSeo.saving") : t("platformSeo.save")}
                        </Button>
                        {settings?.updated_at && <span className="text-xs text-muted">{t("platformSeo.updatedAt", { date: fmt(settings.updated_at) })}</span>}
                      </div>
                    )}
                  </div>
                  <ImagePicker
                    url={settings?.default_og_image_url || ""}
                    onUpload={uploadImage}
                    onRemove={removeImage}
                    label={t("platformSeo.ogImage")}
                    hint={t("platformSeo.ogImageHint")}
                    disabled={!canManage}
                    aspect="aspect-[1200/630]"
                  />
                </form>
              </div>
            </div>
          </Card>

          <Card className="mb-5 p-5">
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[#25d366]/15 text-[#128c7e]"><MessageCircle size={20} /></span>
              <div className="min-w-0 flex-1">
                <h2 className="font-display font-semibold">{t("platformSeo.contactCard")}</h2>
                <p className="mt-1 text-sm text-muted">{t("platformSeo.contactHint")}</p>
                <form onSubmit={saveSettings} className="mt-4 grid gap-3 sm:grid-cols-3">
                  <Field label={t("platformSeo.supportWhatsapp")} hint={t("platformSeo.supportWhatsappHint")}>
                    <Input dir="ltr" type="tel" maxLength={32} value={form.support_whatsapp} onChange={set("support_whatsapp")} disabled={!canManage} placeholder="+249 91 234 5678" />
                  </Field>
                  <Field label={t("platformSeo.supportPhone")}>
                    <Input dir="ltr" type="tel" maxLength={32} value={form.support_phone} onChange={set("support_phone")} disabled={!canManage} />
                  </Field>
                  <Field label={t("platformSeo.supportEmail")}>
                    <Input dir="ltr" type="email" maxLength={254} value={form.support_email} onChange={set("support_email")} disabled={!canManage} />
                  </Field>
                  {canManage && (
                    <div className="sm:col-span-3">
                      <Button type="submit" disabled={saving === "settings"}>
                        {saving === "settings" ? t("platformSeo.saving") : t("platformSeo.save")}
                      </Button>
                    </div>
                  )}
                </form>
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h2 className="font-display font-semibold">{t("platformSeo.overridesCard")}</h2>
                <p className="mt-1 text-sm text-muted">{t("platformSeo.overridesHint")}</p>
              </div>
              {canManage && editing === null && (
                <Button className="shrink-0 whitespace-nowrap" onClick={() => startEdit(null)}><Plus size={15} />{t("platformSeo.add")}</Button>
              )}
            </div>
            {editing === "new" && overrideForm}

            {overrides.length === 0 && editing !== "new" ? (
              <p className="mt-4 text-sm text-muted">{t("platformSeo.noOverrides")}</p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-start text-xs text-muted">
                      <th className="px-2 py-2 text-start font-medium">{t("platformSeo.colPath")}</th>
                      <th className="px-2 py-2 text-start font-medium">{t("platformSeo.colLanguage")}</th>
                      <th className="px-2 py-2 text-start font-medium">{t("platformSeo.colTitle")}</th>
                      <th className="px-2 py-2 text-start font-medium">{t("platformSeo.colFlags")}</th>
                      <th className="px-2 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {overrides.map((row) => (
                      <tr key={row.id} className="border-t border-line align-top">
                        <td className="px-2 py-2 font-mono text-xs" dir="ltr">
                          <a href={pageUrl(row.path, row.language)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-accent" title={t("platformSeo.openPage")}>
                            {row.path}<ExternalLink size={11} />
                          </a>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">{t(`platformSeo.languages.${row.language}`)}</td>
                        <td className="px-2 py-2">
                          <div className="font-medium">{row.title || <span className="text-muted">—</span>}</div>
                          {row.description && <div className="mt-0.5 line-clamp-2 text-xs text-muted">{row.description}</div>}
                        </td>
                        <td className="px-2 py-2">
                          <div className="flex flex-wrap gap-1">
                            {row.noindex && <Badge tone="warn">{t("platformSeo.flagNoindex")}</Badge>}
                            {row.canonical && <Badge tone="muted">{t("platformSeo.flagCanonical")}</Badge>}
                          </div>
                        </td>
                        <td className="px-2 py-2">
                          {canManage && (
                            <div className="flex justify-end gap-1">
                              <Button variant="ghost" className="px-2" onClick={() => startEdit(row)} title={t("platformSeo.edit")}><Pencil size={14} /></Button>
                              <Button variant="ghost" className="px-2 text-danger" disabled={saving === `delete-${row.id}`} onClick={() => removeOverride(row)} title={t("platformSeo.delete")}><Trash2 size={14} /></Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {editing !== null && editing !== "new" && overrideForm}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
