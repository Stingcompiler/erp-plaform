"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Globe, Lock } from "lucide-react";

import { website } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, Field, Input, PageHeader } from "@/components/ui/kit";
import SectionsEditor from "@/components/website/SectionsEditor";
import FeaturedProducts from "@/components/website/FeaturedProducts";

export default function WebsitePage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("website");
  const [page, setPage] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

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

  const set = (key) => (e) => setPage((p) => ({ ...p, [key]: e.target.value }));

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
      });
      setPage(r.data);
      setMsg(t("website.saved"));
    } catch {
      setMsg(t("website.saveChangesError"));
    } finally {
      setSaving(false);
    }
  }

  async function togglePublish() {
    setMsg("");
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
          page &&
          (page.is_published ? (
            <Badge tone="ok">{t("website.published")}</Badge>
          ) : (
            <Badge tone="muted">{t("website.draft")}</Badge>
          ))
        }
      />

      {!page ? (
        <div className="text-muted">{t("common.loading")}</div>
      ) : (
        <Card className="p-6">
          <div className="space-y-4">
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
              <Field label={t("website.logoUrl")}>
                <Input value={page.logo_url || ""} onChange={set("logo_url")} disabled={!writable} />
              </Field>
              <Field label={t("website.primaryColor")}>
                <Input value={page.primary_color || ""} onChange={set("primary_color")} disabled={!writable} />
              </Field>
            </div>

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

      {page && <SectionsEditor websiteId={page.id} writable={writable} />}
      {page && <FeaturedProducts websiteId={page.id} writable={writable} />}
    </div>
  );
}
