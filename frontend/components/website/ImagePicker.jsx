"use client";

// One image slot (cover, logo, product photo): shows the current picture,
// uploads a replacement, removes it. The server validates, resizes and
// re-encodes; this only sends the file and shows what came back.
import { useRef, useState } from "react";
import { ImagePlus, Trash2 } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { errorText } from "@/lib/errors";

export default function ImagePicker({ url, onUpload, onRemove, label, hint, disabled, aspect = "aspect-[3/1]", rounded = "rounded-card" }) {
  const { t } = useI18n();
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function pick(file) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await onUpload(file);
    } catch (err) {
      const data = err?.response?.data;
      setError(data?.image?.[0] || errorText(err, t, "website.imageError"));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await onRemove();
    } catch {
      setError(t("website.imageError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {label && <div className="mb-1 text-sm font-medium text-ink">{label}</div>}
      <div className={`relative overflow-hidden border border-dashed border-line bg-paper ${aspect} ${rounded}`}>
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full w-full place-items-center text-muted"><ImagePlus size={22} /></div>
        )}
      </div>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {!disabled && (
        <div className="mt-2 flex flex-wrap gap-2">
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-control border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:border-accent">
            <ImagePlus size={15} />
            {busy ? t("website.uploading") : url ? t("website.replaceImage") : t("website.uploadImage")}
            <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" disabled={busy} onChange={(event) => pick(event.target.files?.[0])} />
          </label>
          {url && onRemove && (
            <button type="button" onClick={remove} disabled={busy} className="tap inline-flex items-center gap-1.5 rounded-control px-3 py-1.5 text-sm text-muted hover:text-danger">
              <Trash2 size={15} />{t("website.removeImage")}
            </button>
          )}
        </div>
      )}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
