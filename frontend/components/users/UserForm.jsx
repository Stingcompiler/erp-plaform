"use client";

import { useEffect, useState } from "react";

import { users } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { translateRole } from "@/lib/i18n";
import { groupRoles, roleHint } from "@/lib/roles";
import Drawer from "@/components/ui/Drawer";
import { Button, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";

const EMPTY = { email: "", full_name: "", role: "", branch: "", is_active: true, password: "" };

export default function UserForm({
  open,
  onClose,
  onSaved,
  user,
  roles,
  branches = [],
  presetRoleName = "",
}) {
  const { t } = useI18n();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const editing = Boolean(user);
  const selectedRole = roles.find(
    (role) => String(role.id) === String(form.role)
  );
  const branchRequired = selectedRole?.scope_level === "branch";

  useEffect(() => {
    if (user) {
      setForm({
        email: user.email || "",
        full_name: user.full_name || "",
        role: user.role || "",
        branch: user.branch || "",
        is_active: user.is_active !== false,
        password: "",
      });
    } else {
      const presetRole = roles.find((role) => role.name === presetRoleName);
      setForm({ ...EMPTY, role: presetRole?.id || "" });
    }
    setError("");
  }, [user, open, presetRoleName, roles]);

  // Explains the selected role in one line, so picking one doesn't require
  // knowing the permission matrix by heart.
  const selectedRoleHint = roleHint(
    selectedRole?.name,
    t,
  );

  const set = (key) => (e) =>
    setForm((f) => ({
      ...f,
      [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    }));

  async function save() {
    setError("");
    setSaving(true);
    try {
      if (editing) {
        const body = {
          full_name: form.full_name,
          role: form.role || null,
          branch: form.branch || null,
          is_active: form.is_active,
        };
        if (form.password) body.password = form.password;
        await users.update(user.id, body);
      } else {
        await users.create({
          email: form.email,
          full_name: form.full_name,
          role: form.role || null,
          branch: form.branch || null,
          is_active: form.is_active,
          password: form.password,
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err, t, "users.saveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={editing ? t("users.editUser") : t("users.newUser")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={save}
            disabled={
              saving ||
              !form.email ||
              !form.role ||
              (branchRequired && !form.branch) ||
              (!editing && form.password.length < 10) ||
              (editing && form.password.length > 0 && form.password.length < 10)
            }
          >
            {saving ? t("common.saving") : editing ? t("users.saveChanges") : t("users.createUser")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {!editing && presetRoleName === "Business Owner" && (
          <div className="rounded-control border border-accent/25 bg-accent/5 p-3 text-sm text-ink">
            <p className="font-semibold">{t("users.addOwnerTitle")}</p>
            <p className="mt-1 text-muted">{t("users.addOwnerWarning")}</p>
          </div>
        )}
        <Field label={t("common.email")}>
          <Input type="email" value={form.email} onChange={set("email")} disabled={editing} />
        </Field>
        <Field label={t("users.fullName")}>
          <Input value={form.full_name} onChange={set("full_name")} />
        </Field>
        <Field label={t("users.role")} hint={selectedRoleHint}>
          <Select value={form.role} onChange={set("role")}>
            <option value="" disabled>{t("users.roleNone")}</option>
            {groupRoles(roles).map((group) => (
              <optgroup key={group.key} label={t(`users.roleFamilies.${group.key}`)}>
                {group.roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {translateRole(r.name, t)}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        </Field>
        <Field label={t("users.branch")} hint={t("users.branchHint")}>
          <Select value={form.branch} onChange={set("branch")}>
            <option value="">{t("users.branchNone")}</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </Field>
        {!editing ? (
          <Field label={t("users.password")} hint={t("users.passwordMin")}>
            <Input type="password" value={form.password} onChange={set("password")} />
          </Field>
        ) : (
          <Field label={t("users.resetPassword")} hint={t("users.passwordHint")}>
            <Input
              type="password"
              value={form.password}
              onChange={set("password")}
              placeholder={t("users.newPasswordPlaceholder")}
            />
          </Field>
        )}
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={form.is_active} onChange={set("is_active")} />
          {t("common.active")}
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
