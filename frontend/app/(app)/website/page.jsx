"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Eye, Globe, Lock, RefreshCw } from "lucide-react";

import { website } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import SectionsEditor from "@/components/website/SectionsEditor";
import FeaturedProducts from "@/components/website/FeaturedProducts";
import Gallery from "@/components/website/Gallery";
import ImagePicker from "@/components/website/ImagePicker";

const CATEGORIES = ["grocery", "pharmacy", "wholesale", "electronics", "fashion", "cosmetics", "hardware", "restaurant", "services", "other"];

export default function WebsitePage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("website");
  const [page, setPage] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [preview, setPreview] = useState(false);
  // Bumped after every save so the iframe reloads the draft.
  const [previewKey, setPreviewKey] = useState(0);
  const refreshPreview = () => setPreviewKey((k) => k + 1);

  useEffect(() => {
    if (canRead("website")) {
      website.page().then((r) => setPage(r.data)).catch(() => setPage(null));
    }
  }, [canRead]);

  if (!canRead("website")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("website.noAccess")}</p>
      </div>
    );
  }

  const set = (key) => (e) => setPage((p) => ({ ...p, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const image = (kind) => ({
    onUpload: async (file) => { const r = await website.uploadImage(kind, file); setPage(r.data); refreshPreview(); },
    onRemove: async () => { const r = await website.removeImage(kind); setPage(r.data); refreshPreview(); },
  });

  async function save() {
    setMsg("");
    setSaving(true);
    try {
      const r = await website.updatePage({
        business_name: page.business_name,
        tagline: page.tagline,
        about_text: page.about_text,
        logo_url: page.logo_url,
        primary_color: page.primary_color,
        contact_email: page.contact_email,
        contact_phone: page.contact_phone,
        address: page.address,
        category: page.category || "",
        city: page.city || "",
        opening_hours: page.opening_hours || "",
        map_url: page.map_url || "",
        services: page.services || "",
        list_in_directory: page.list_in_directory !== false,
      });
      setPage(r.data);
      setMsg(t("website.saved"));
      refreshPreview();
    } catch {
      setMsg(t("website.saveChangesError"));
    } finally {
      setSaving(false);
    }
  }

  async function togglePublish() {
    setMsg("");
    if (!page.is_published && page.missing?.length && !window.confirm(t("website.publishIncompleteConfirm"))) return;
    try {
      const r = await website.publish(!page.is_published);
      setPage((p) => ({ ...p, is_published: r.data.is_published ?? !p.is_published }));
    } catch {
      setMsg(t("website.publishError"));
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader
        title={t("website.title")}
        subtitle={t("website.subtitlePublic")}
        actions={
          page && (
            <>
              {page.is_published ? (
                <Badge tone="ok">{t("website.published")}</Badge>
              ) : (
                <Badge tone="muted">{t("website.draft")}</Badge>
              )}
              <Button variant="outline" onClick={() => { setPreview((v) => !v); refreshPreview(); }}>
                <Eye size={15} />{preview ? t("website.hidePreview") : t("website.showPreview")}
              </Button>
            </>
          )
        }
      />

      {page && preview && (
        <Card className="mb-6 overflow-hidden">
          <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2 text-xs text-muted">
            <span>{t("website.previewHint")}</span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" onClick={refreshPreview} aria-label={t("website.refreshPreview")}><RefreshCw size={14} /></Button>
              <a href={website.previewUrl()} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-control px-2 py-1 hover:text-ink"><ExternalLink size={13} />{t("website.openPreview")}</a>
            </div>
          </div>
          <iframe
            key={previewKey}
            title={t("website.showPreview")}
            src={`${website.previewUrl()}?v=${previewKey}`}
            className="h-[70vh] w-full bg-paper"
          />
        </Card>
      )}

      {!page ? (
        <div className="text-muted">{t("common.loading")}</div>
      ) : (
        <Card className="p-6">
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
              <ImagePicker label={t("website.cover")} hint={t("website.coverHint")} url={page.cover_image_url} disabled={!writable} {...image("cover")} />
              <ImagePicker label={t("website.logo")} hint={t("website.logoHint")} url={page.logo_image_url} disabled={!writable} aspect="aspect-square" {...image("logo")} />
            </div>
            <Field label={t("website.businessName")}>
              <Input value={page.business_name || ""} onChange={set("business_name")} disabled={!writable} />
            </Field>
            <Field label={t("website.tagline")}>
              <Input value={page.tagline || ""} onChange={set("tagline")} disabled={!writable} />
            </Field>
            <Field label={t("website.about")}>
              <textarea
                value={page.about_text || ""}
                onChange={set("about_text")}
                disabled={!writable}
                rows={4}
                className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("website.contactEmail")}>
                <Input value={page.contact_email || ""} onChange={set("contact_email")} disabled={!writable} />
              </Field>
              <Field label={t("website.contactPhone")}>
                <Input value={page.contact_phone || ""} onChange={set("contact_phone")} disabled={!writable} />
              </Field>
            </div>
            <Field label={t("common.address")}>
              <Input value={page.address || ""} onChange={set("address")} disabled={!writable} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("website.city")}>
                <Input value={page.city || ""} onChange={set("city")} disabled={!writable} />
              </Field>
              <Field label={t("website.category")}>
                <Select value={page.category || ""} onChange={set("category")} disabled={!writable}>
                  <option value="">—</option>
                  {CATEGORIES.map((key) => <option key={key} value={key}>{t(`website.categories.${key}`)}</option>)}
                </Select>
              </Field>
            </div>
            <Field label={t("website.openingHours")} hint={t("website.openingHoursHint")}>
              <textarea
                value={page.opening_hours || ""}
                onChange={set("opening_hours")}
                disabled={!writable}
                rows={3}
                className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
              />
            </Field>
            <Field label={t("website.services")} hint={t("website.servicesHint")}>
              <textarea
                value={page.services || ""}
                onChange={set("services")}
                disabled={!writable}
                rows={4}
                maxLength={420}
                placeholder={t("website.servicesPlaceholder")}
                className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
              />
            </Field>
            <Field label={t("website.mapUrl")} hint={t("website.mapUrlHint")}>
              <Input value={page.map_url || ""} onChange={set("map_url")} disabled={!writable} placeholder="https://maps.google.com/..." />
            </Field>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={page.list_in_directory !== false} onChange={set("list_in_directory")} disabled={!writable} className="mt-1" />
              <span>
                <span className="font-medium">{t("website.listInDirectory")}</span>
                <span className="block text-xs text-muted">{t("website.listInDirectoryHint")}</span>
              </span>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("website.logoUrl")}>
                <Input value={page.logo_url || ""} onChange={set("logo_url")} disabled={!writable} />
              </Field>
              <Field label={t("website.primaryColor")}>
                <Input value={page.primary_color || ""} onChange={set("primary_color")} disabled={!writable} />
              </Field>
            </div>

            {Array.isArray(page.missing) && (
              <div className="rounded-control border border-line bg-paper p-3 text-sm">
                {page.missing.length === 0 ? (
                  <p className="flex items-center gap-2 text-ok"><CheckCircle2 size={16} />{t("website.complete")}</p>
                ) : (
                  <>
                    <p className="font-medium">{t("website.missingTitle")}</p>
                    <ul className="mt-1 list-disc ps-5 text-muted">
                      {page.missing.map((key) => <li key={key}>{t(`website.missingItems.${key}`)}</li>)}
                    </ul>
                  </>
                )}
              </div>
            )}

            {msg && <p className="text-sm text-muted">{msg}</p>}

            {writable && (
              <div className="flex items-center gap-2 border-t border-line pt-4">
                <Button onClick={save} disabled={saving}>
                  {saving ? t("common.saving") : t("website.saveChanges")}
                </Button>
                <Button variant="outline" onClick={togglePublish}>
                  <Globe size={15} />
                  {page.is_published ? t("website.unpublish") : t("website.publish")}
                </Button>
              </div>
            )}

            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
              <ExternalLink size={13} />
              {t(page.is_published ? "website.liveAt" : "website.servedAt")}
              <a href={page.public_url} target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline">{page.public_url}</a>
            </p>
          </div>
        </Card>
      )}

      {page && <SectionsEditor websiteId={page.id} writable={writable} onChanged={refreshPreview} />}
      {page && <FeaturedProducts websiteId={page.id} writable={writable} onChanged={() => { website.page().then((r) => setPage(r.data)).catch(() => {}); refreshPreview(); }} />}
      {page && <Gallery writable={writable} onChanged={refreshPreview} />}
    </div>
  );
}
