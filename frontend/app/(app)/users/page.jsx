"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Lock, Plus, ShieldCheck } from "lucide-react";

import { users as usersApi } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { translateRole } from "@/lib/i18n";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";
import UserForm from "@/components/users/UserForm";

export default function UsersPage() {
  const { user: currentUser, canRead, canWrite, can } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("users");
  const canAssignOwner = can("users.assign_owner");
  const canEditUser = (target) => {
    if (!writable || target.id === currentUser?.id) return false;
    if (can("users.assign_owner")) return true;
    if (can("users.manage_company")) {
      return target.role_name !== "Business Owner";
    }
    if (can("users.manage_branch")) {
      return !["Business Owner", "General Manager", "Branch Manager"].includes(
        target.role_name
      );
    }
    return false;
  };
  const [rows, setRows] = useState([]);
  const [roles, setRoles] = useState([]);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [presetRoleName, setPresetRoleName] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    usersApi
      .list({ page: 1 })
      .then((r) => setRows(r.data.results))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    usersApi.roles().then((r) => setRoles(r.data.results || r.data)).catch(() => {});
    usersApi.branches().then((r) => setBranches(r.data.results || r.data)).catch(() => {});
  }, [load]);

  if (!canRead("users")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("users.noAccess")}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("users.title")}
        subtitle={t("users.subtitle")}
        actions={writable && (
          <>
            {canAssignOwner && (
              <Button
                variant="outline"
                onClick={() => {
                  setEditing(null);
                  setPresetRoleName("Business Owner");
                  setFormOpen(true);
                }}
              >
                <ShieldCheck size={16} /> {t("users.addOwner")}
              </Button>
            )}
            <Button
              onClick={() => {
                setEditing(null);
                setPresetRoleName("");
                setFormOpen(true);
              }}
            >
              <Plus size={16} /> {t("users.newUser")}
            </Button>
          </>
        )}
      />

      {canAssignOwner && (
        <Card className="mb-5 border-accent/25 p-5">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent">
              <ShieldCheck size={20} />
            </span>
            <div>
              <h2 className="font-display font-semibold">{t("users.ownersTitle")}</h2>
              <p className="mt-1 text-sm text-muted">
                {t("users.ownersSummary", {
                  count: rows.filter((row) => row.role_name === "Business Owner" && row.is_active).length,
                })}
              </p>
              <p className="mt-1 text-xs text-muted">{t("users.ownersRule")}</p>
            </div>
          </div>
        </Card>
      )}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("common.email")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("common.name")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("users.role")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("users.branch")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
                {writable && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={writable ? 6 : 5} className="px-4 py-8 text-center text-muted">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={writable ? 6 : 5} className="px-4 py-8 text-center text-muted">
                    {t("users.noUsers")}
                  </td>
                </tr>
              )}
              {!loading &&
                rows.map((u) => (
                  <tr key={u.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3 text-ink">
                      <Link href={`/users/detail/?id=${u.id}`} className="hover:text-accent hover:underline" title={t("users.viewUser")}>{u.email}</Link>
                    </td>
                    <td className="px-4 py-3 text-muted">{u.full_name || "—"}</td>
                    <td className="px-4 py-3 text-muted">{u.role_name ? translateRole(u.role_name, t) : "—"}</td>
                    <td className="px-4 py-3 text-muted">
                      {branches.find((b) => b.id === u.branch)?.name || "—"}
                    </td>
                    <td className="px-4 py-3 text-end">
                      {u.is_active ? (
                        <Badge tone="ok">{t("common.active")}</Badge>
                      ) : (
                        <Badge tone="muted">{t("common.inactive")}</Badge>
                      )}
                    </td>
                    {writable && (
                      <td className="px-4 py-3 text-end">
                        {canEditUser(u) && (
                          <button
                            onClick={() => {
                              setEditing(u);
                              setFormOpen(true);
                            }}
                            className="text-sm text-accent hover:underline"
                          >
                            {t("common.edit")}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>

      <UserForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={load}
        user={editing}
        roles={roles}
        branches={branches}
        presetRoleName={presetRoleName}
      />
    </div>
  );
}
