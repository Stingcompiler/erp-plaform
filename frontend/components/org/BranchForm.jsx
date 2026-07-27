"use client";

import { useEffect, useState } from "react";

import { org } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input } from "@/components/ui/kit";

const EMPTY = { name: "", code: "", address: "", phone: "", is_active: true };

export default function BranchForm({ open, onClose, onSaved, branch }) {
  const { t } = useI18n();
  const editing = Boolean(branch);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (branch) {
      setForm({
        name: branch.name || "",
        code: branch.code || "",
        address: branch.address || "",
        phone: branch.phone || "",
        is_active: branch.is_active !== false,
      });
    } else {
      setForm(EMPTY);
    }
    setError("");
  }, [branch, open]);

  const set = (k) => (e) =>
    setForm((f) => ({
      ...f,
      [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    }));

  async function save() {
    setError("");
    setSaving(true);
    try {
      if (editing) {
        await org.updateBranch(branch.id, form);
      } else {
        await org.createBranch(form);
      }
      onSaved();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" && data
          ? Object.values(data).flat().join(" ")
          : t("org.saveError")
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("org.editBranch") : t("org.newBranch")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !form.name}>
            {saving ? t("common.saving") : editing ? t("org.saveBranch") : t("org.createBranch")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("common.name")}>
            <Input value={form.name} onChange={set("name")} />
          </Field>
          <Field label={t("common.code")}>
            <Input value={form.code} onChange={set("code")} />
          </Field>
        </div>
        <Field label={t("common.address")}>
          <Input value={form.address} onChange={set("address")} />
        </Field>
        <Field label={t("common.phone")}>
          <Input value={form.phone} onChange={set("phone")} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={form.is_active} onChange={set("is_active")} />
          {t("common.active")}
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
