"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock, Plus } from "lucide-react";

import { inventory, org } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";
import BranchForm from "@/components/org/BranchForm";
import WarehouseForm from "@/components/org/WarehouseForm";
import { SkeletonTableRows } from "@/components/ui/Skeleton";

function SectionHeading({ title, subtitle, action }) {
  return (
    <div className="mb-3 mt-8 flex items-end justify-between gap-4 first:mt-0">
      <div>
        <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export default function OrgPage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("org");
  const canWriteInv = canWrite("inventory");

  const [branches, setBranches] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [branchFormOpen, setBranchFormOpen] = useState(false);
  const [editingBranch, setEditingBranch] = useState(null);
  const [whFormOpen, setWhFormOpen] = useState(false);
  const [editingWh, setEditingWh] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    org
      .branches()
      .then((r) => setBranches(r.data.results || r.data))
      .catch(() => setBranches([]))
      .finally(() => setLoading(false));
    inventory
      .warehouses()
      .then((r) => setWarehouses(r.data.results || r.data))
      .catch(() => setWarehouses([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!canRead("org")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("org.noAccess")}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t("org.title")} subtitle={t("org.subtitle")} />

      {/* Branches */}
      <SectionHeading
        title={t("org.branches")}
        action={
          writable && (
            <Button
              onClick={() => {
                setEditingBranch(null);
                setBranchFormOpen(true);
              }}
            >
              <Plus size={16} /> {t("org.newBranch")}
            </Button>
          )
        }
      />
      <Card>
        <div className="overflow-x-auto">
          <table className="stack-sm w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("common.name")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("common.code")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("common.phone")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
                {writable && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <SkeletonTableRows cols={writable ? 5 : 4} />
              )}
              {!loading && branches.length === 0 && (
                <tr>
                  <td colSpan={writable ? 5 : 4} className="px-4 py-8 text-center text-muted">
                    {t("org.noBranches")}
                  </td>
                </tr>
              )}
              {!loading &&
                branches.map((b) => (
                  <tr key={b.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3 text-ink">{b.name}</td>
                    <td className="tabular px-4 py-3 text-muted">{b.code || "—"}</td>
                    <td className="px-4 py-3 text-muted"><PhoneLink phone={b.phone} /></td>
                    <td className="px-4 py-3 text-end">
                      {b.is_active ? (
                        <Badge tone="ok">{t("common.active")}</Badge>
                      ) : (
                        <Badge tone="muted">{t("common.inactive")}</Badge>
                      )}
                    </td>
                    {writable && (
                      <td className="px-4 py-3 text-end">
                        <button
                          onClick={() => {
                            setEditingBranch(b);
                            setBranchFormOpen(true);
                          }}
                          className="text-sm text-accent hover:underline"
                        >
                          {t("common.edit")}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Warehouses */}
      <SectionHeading
        title={t("org.warehouses")}
        subtitle={t("org.warehousesSubtitle")}
        action={
          canWriteInv && (
            <Button
              onClick={() => {
                setEditingWh(null);
                setWhFormOpen(true);
              }}
            >
              <Plus size={16} /> {t("org.newWarehouse")}
            </Button>
          )
        }
      />
      <Card>
        <div className="overflow-x-auto">
          <table className="stack-sm w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("common.name")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("common.code")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
                {canWriteInv && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {!loading && warehouses.length === 0 && (
                <tr>
                  <td colSpan={canWriteInv ? 4 : 3} className="px-4 py-8 text-center text-muted">
                    {t("org.noWarehouses")}
                  </td>
                </tr>
              )}
              {warehouses.map((w) => (
                <tr key={w.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3 text-ink">{w.name}</td>
                  <td className="tabular px-4 py-3 text-muted">{w.code || "—"}</td>
                  <td className="px-4 py-3 text-end">
                    {w.is_active ? (
                      <Badge tone="ok">{t("common.active")}</Badge>
                    ) : (
                      <Badge tone="muted">{t("common.inactive")}</Badge>
                    )}
                  </td>
                  {canWriteInv && (
                    <td className="px-4 py-3 text-end">
                      <button
                        onClick={() => {
                          setEditingWh(w);
                          setWhFormOpen(true);
                        }}
                        className="text-sm text-accent hover:underline"
                      >
                        {t("common.edit")}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <BranchForm
        open={branchFormOpen}
        onClose={() => setBranchFormOpen(false)}
        onSaved={load}
        branch={editingBranch}
      />
      <WarehouseForm
        open={whFormOpen}
        onClose={() => setWhFormOpen(false)}
        onSaved={load}
        warehouse={editingWh}
        branches={branches}
      />
    </div>
  );
}
