"use client";

import { useEffect, useState } from "react";

import { hr } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";

const EMPTY = {
  full_name: "",
  employee_code: "",
  email: "",
  phone: "",
  position: "",
  hire_date: "",
  status: "active",
};

export default function EmployeeDrawer({ open, employee, positions, writable, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const editing = Boolean(employee?.id);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!open) return;
    if (employee?.id) {
      setForm({
        full_name: employee.full_name || "",
        employee_code: employee.employee_code || "",
        email: employee.email || "",
        phone: employee.phone || "",
        position: employee.position ?? "",
        hire_date: employee.hire_date || "",
        status: employee.status || "active",
      });
    } else {
      setForm(EMPTY);
    }
  }, [open, employee]);

  async function save() {
    setSaving(true);
    const payload = {
      ...form,
      position: form.position === "" ? null : form.position,
      hire_date: form.hire_date === "" ? null : form.hire_date,
    };
    try {
      if (editing) await hr.updateEmployee(employee.id, payload);
      else await hr.createEmployee(payload);
      toast.success(t("common.save"));
      onSaved?.();
      onClose();
    } catch {
      toast.error(t("common.loadError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("hr.editEmployee") : t("hr.newEmployee")}
      footer={
        writable && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !form.full_name}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <Field label={t("hr.fullName")}>
          <Input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} disabled={!writable} />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t("hr.employeeCode")}>
            <Input value={form.employee_code} onChange={(e) => set("employee_code", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("hr.position")}>
            <Select value={form.position} onChange={(e) => set("position", e.target.value)} disabled={!writable}>
              <option value="">—</option>
              {(positions || []).map((p) => (
                <option key={p.id} value={p.id}>{p.title}</option>
              ))}
            </Select>
          </Field>
          <Field label={t("common.email")}>
            <Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("common.phone")}>
            <Input value={form.phone} onChange={(e) => set("phone", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("hr.hireDate")}>
            <Input type="date" value={form.hire_date} onChange={(e) => set("hire_date", e.target.value)} disabled={!writable} />
          </Field>
          <Field label={t("hr.status")}>
            <Select value={form.status} onChange={(e) => set("status", e.target.value)} disabled={!writable}>
              <option value="active">{t("hr.statusActive")}</option>
              <option value="on_leave">{t("hr.statusOnLeave")}</option>
              <option value="terminated">{t("hr.statusTerminated")}</option>
            </Select>
          </Field>
        </div>
      </div>
    </Drawer>
  );
}
