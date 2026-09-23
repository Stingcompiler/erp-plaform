"use client";

// The public page's photo gallery: add photos, caption them, remove them.
import { useCallback, useEffect, useRef, useState } from "react";
import { ImagePlus, Trash2 } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { website } from "@/lib/api";
import { Button, Card } from "@/components/ui/kit";
import { useConfirm } from "@/components/ui/ConfirmDialog";

export default function Gallery({ writable, onChanged }) {
  const { t } = useI18n();
  const confirm = useConfirm();
  const input = useRef(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    website.gallery().then((r) => setRows(r.data.results || r.data)).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function add(files) {
    if (!files?.length) return;
    setBusy(true);
    setError("");
    try {
      for (const file of Array.from(files)) {
        await website.addGalleryImage(file, rows.length);
      }
      load();
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.image?.[0] || t("website.imageError"));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function caption(item, value) {
    if (value === item.caption) return;
    await website.updateGalleryImage(item.id, { caption: value }).catch(() => {});
  }

  async function remove(item) {
    if (!(await confirm(t("website.removeImageConfirm"), { tone: "danger" }))) return;
    await website.deleteGalleryImage(item.id).catch(() => {});
    load();
    onChanged?.();
  }

  return (
    <Card className="mt-6 p-6">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">{t("website.gallery")}</h2>
        {writable && (
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-control bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-strong">
            <ImagePlus size={15} />{busy ? t("website.uploading") : t("website.addPhotos")}
            <input ref={input} type="file" multiple accept="image/jpeg,image/png,image/webp" className="hidden" disabled={busy} onChange={(event) => add(event.target.files)} />
          </label>
        )}
      </div>
      <p className="mb-4 text-xs text-muted">{t("website.galleryHint")}</p>
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("website.galleryEmpty")}</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {rows.map((item) => (
            <figure key={item.id} className="m-0 overflow-hidden rounded-card border border-line bg-paper">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={item.url} alt={item.caption || ""} className="aspect-square w-full object-cover" />
              <div className="flex items-center gap-1 p-2">
                <input
                  defaultValue={item.caption || ""}
                  placeholder={t("website.captionPlaceholder")}
                  disabled={!writable}
                  onBlur={(event) => caption(item, event.target.value)}
                  className="min-w-0 flex-1 bg-transparent text-xs text-ink outline-none"
                />
                {writable && (
                  <Button variant="ghost" onClick={() => remove(item)} aria-label={t("website.removeImage")}><Trash2 size={14} /></Button>
                )}
              </div>
            </figure>
          ))}
        </div>
      )}
    </Card>
  );
}
