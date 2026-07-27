"use client";

import { useEffect, useState } from "react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";

const EMPTY = { name: "", code: "", branch: "", is_active: true };

export default function WarehouseForm({ open, onClose, onSaved, warehouse, branches = [] }) {
  const { t } = useI18n();
  const editing = Boolean(warehouse);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (warehouse) {
      setForm({
        name: warehouse.name || "",
        code: warehouse.code || "",
        branch: warehouse.branch || "",
        is_active: warehouse.is_active !== false,
      });
    } else {
      setForm(EMPTY);
    }
    setError("");
  }, [warehouse, open]);

  const set = (k) => (e) =>
    setForm((f) => ({
      ...f,
      [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    }));

  async function save() {
    setError("");
    setSaving(true);
    const body = { ...form, branch: form.branch || null };
    try {
      if (editing) await inventory.updateWarehouse(warehouse.id, body);
      else await inventory.createWarehouse(body);
      onSaved();
      onClose();
    } catch (err) {
      const data = err?.response?.data;
      setError(
        typeof data === "object" && data
          ? Object.values(data).flat().join(" ")
          : t("org.warehouseSaveError")
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("org.editWarehouse") : t("org.newWarehouse")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !form.name}>
            {saving ? t("common.saving") : editing ? t("org.saveWarehouse") : t("org.createWarehouse")}
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
        <Field label={t("users.branch")}>
          <Select value={form.branch} onChange={set("branch")}>
            <option value="">{t("users.branchNone")}</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
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
