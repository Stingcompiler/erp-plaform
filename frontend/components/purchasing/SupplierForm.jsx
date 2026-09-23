"use client";

import { useState } from "react";

import { purchasing } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";

const EMPTY = { name: "", phone: "", email: "", address: "" };

export default function SupplierForm({ open, onClose, onSaved }) {
  const { t } = useI18n();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function save() {
    setError("");
    setSaving(true);
    try {
      await purchasing.createSupplier(form);
      setForm(EMPTY);
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err, t, "purchasing.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("purchasing.newSupplier")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !form.name}>
            {saving ? t("common.saving") : t("purchasing.createSupplier")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label={t("common.name")}>
          <Input value={form.name} onChange={set("name")} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("common.phone")}>
            <Input value={form.phone} onChange={set("phone")} />
          </Field>
          <Field label={t("common.email")}>
            <Input type="email" value={form.email} onChange={set("email")} />
          </Field>
        </div>
        <Field label={t("common.address")}>
          <Input value={form.address} onChange={set("address")} />
        </Field>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
