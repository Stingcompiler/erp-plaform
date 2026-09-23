"use client";

import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, Pencil, Plus, Trash2 } from "lucide-react";

import { website } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { SkeletonLines } from "@/components/ui/Skeleton";

const TYPES = [
  { value: "hero", key: "website.typeHero" },
  { value: "about", key: "website.typeAbout" },
  { value: "products", key: "website.typeProducts" },
  { value: "gallery", key: "website.typeGallery" },
  { value: "contact", key: "website.typeContact" },
  { value: "custom", key: "website.typeCustom" },
];
const typeLabel = (t, v) => {
  const entry = TYPES.find((x) => x.value === v);
  return entry ? t(entry.key) : v;
};

function SectionForm({ open, onClose, onSaved, websiteId, section }) {
  const { t } = useI18n();
  const editing = Boolean(section);
  const [form, setForm] = useState({ type: "hero", title: "", order: 0, body: "", is_visible: true });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (section) {
      setForm({
        type: section.type,
        title: section.title || "",
        order: section.order ?? 0,
        body: section.content?.text || "",
        is_visible: section.is_visible !== false,
      });
    } else {
      setForm({ type: "hero", title: "", order: 0, body: "", is_visible: true });
    }
    setError("");
  }, [section, open]);

  const set = (k) => (e) =>
    setForm((f) => ({
      ...f,
      [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    }));

  async function save() {
    setError("");
    setSaving(true);
    try {
      // Merge body into content.text, preserving any other keys set via API.
      const content = { ...(section?.content || {}), text: form.body };
      const body = {
        type: form.type,
        title: form.title,
        order: Number(form.order) || 0,
        is_visible: form.is_visible,
        content,
      };
      if (editing) {
        await website.updateSection(section.id, body);
      } else {
        await website.createSection({ ...body, website: websiteId });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err, t, "website.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("website.editSection") : t("website.newSection")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? t("common.saving") : editing ? t("website.saveSection") : t("website.addSection")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("website.sectionType")}>
            <Select value={form.type} onChange={set("type")}>
              {TYPES.map((ty) => (
                <option key={ty.value} value={ty.value}>
                  {t(ty.key)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("website.order")}>
            <Input type="number" value={form.order} onChange={set("order")} />
          </Field>
        </div>
        <Field label={t("website.heading")}>
          <Input value={form.title} onChange={set("title")} />
        </Field>
        <Field label={t("website.body")} hint={t("website.bodyHint")}>
          <textarea
            value={form.body}
            onChange={set("body")}
            rows={4}
            className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={form.is_visible} onChange={set("is_visible")} />
          {t("website.visibleOnSite")}
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}

export default function SectionsEditor({ websiteId, writable, onChanged }) {
  const { t } = useI18n();
  const confirm = useConfirm();
  const [sections, setSections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    website
      .sections()
      .then((r) => setSections(r.data.results || r.data))
      .catch(() => setSections([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const changed = () => {
    load();
    onChanged?.();
  };

  async function toggleVisible(s) {
    await website.updateSection(s.id, { is_visible: !s.is_visible }).catch(() => {});
    changed();
  }

  async function remove(s) {
    if (!(await confirm(t("website.deleteSectionConfirm", { name: s.title || typeLabel(t, s.type) }), { tone: "danger" }))) return;
    await website.deleteSection(s.id).catch(() => {});
    changed();
  }

  return (
    <Card className="mt-6 p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">
          {t("website.pageSections")}
        </h2>
        {writable && websiteId && (
          <Button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <Plus size={16} /> {t("website.addSection")}
          </Button>
        )}
      </div>

      {loading ? (
        <SkeletonLines />
      ) : sections.length === 0 ? (
        <p className="text-sm text-muted">{t("website.addSectionsHint")}</p>
      ) : (
        <div className="divide-y divide-line">
          {sections.map((s) => (
            <div key={s.id} className="flex items-center gap-3 py-3">
              <span className="tabular w-8 text-center text-xs text-muted">{s.order}</span>
              <Badge tone="muted">{typeLabel(t, s.type)}</Badge>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-ink">{s.title || t("website.untitled")}</div>
                {s.content?.text && (
                  <div className="truncate text-xs text-muted">{s.content.text}</div>
                )}
              </div>
              {!s.is_visible && <Badge tone="warn">{t("website.hidden")}</Badge>}
              {writable && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => toggleVisible(s)}
                    className="rounded p-1.5 text-muted hover:bg-paper hover:text-ink"
                    aria-label={s.is_visible ? t("website.hide") : t("website.show")}
                  >
                    {s.is_visible ? <Eye size={15} /> : <EyeOff size={15} />}
                  </button>
                  <button
                    onClick={() => {
                      setEditing(s);
                      setFormOpen(true);
                    }}
                    className="rounded p-1.5 text-muted hover:bg-paper hover:text-ink"
                    aria-label={t("common.edit")}
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => remove(s)}
                    className="rounded p-1.5 text-muted hover:bg-paper hover:text-danger"
                    aria-label={t("common.delete")}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <SectionForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={changed}
        websiteId={websiteId}
        section={editing}
      />
    </Card>
  );
}
