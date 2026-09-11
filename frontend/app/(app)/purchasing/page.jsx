"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock, Plus } from "lucide-react";

import { inventory, purchasing, bankAccounts as bankApi } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";
import SupplierForm from "@/components/purchasing/SupplierForm";
import ReceivingTerminal from "@/components/purchasing/ReceivingTerminal";
import BillList from "@/components/purchasing/BillList";
import NewBillDrawer from "@/components/purchasing/NewBillDrawer";

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function SupplierList({ suppliers, loading, writable, onNew }) {
  const { t } = useI18n();
  return (
    <div>
      <div className="mb-4 flex justify-end">
        {writable && (
          <Button onClick={onNew}>
            <Plus size={16} /> {t("purchasing.newSupplier")}
          </Button>
        )}
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("common.name")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("common.phone")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("purchasing.apBalance")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("common.status")}</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {!loading && suppliers.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted">
                    {t("purchasing.noSuppliers")}
                  </td>
                </tr>
              )}
              {!loading &&
                suppliers.map((s) => (
                  <tr key={s.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3 text-ink">{s.name}</td>
                    <td className="px-4 py-3 text-muted">{s.phone || "—"}</td>
                    <td className="tabular px-4 py-3 text-end text-ink">{money(s.ap_balance)}</td>
                    <td className="px-4 py-3 text-end">
                      {s.is_active ? (
                        <Badge tone="ok">{t("common.active")}</Badge>
                      ) : (
                        <Badge tone="muted">{t("common.inactive")}</Badge>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

export default function PurchasingPage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("purchasing");
  const [tab, setTab] = useState("suppliers");
  useEffect(() => { const requested = new URLSearchParams(window.location.search).get("tab");
    if (['suppliers', 'receive', 'bills'].includes(requested)) setTab(requested);
  }, []);
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loadingSuppliers, setLoadingSuppliers] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [billOpen, setBillOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadSuppliers = useCallback(() => {
    setLoadingSuppliers(true);
    purchasing
      .suppliers({ page: 1 })
      .then((r) => setSuppliers(r.data.results))
      .catch(() => setSuppliers([]))
      .finally(() => setLoadingSuppliers(false));
  }, []);

  useEffect(() => {
    loadSuppliers();
    inventory.warehouses().then((r) => setWarehouses(r.data.results)).catch(() => {});
    bankApi.list().then((r) => setAccounts(r.data.results || r.data)).catch(() => {});
  }, [loadSuppliers]);

  if (!canRead("purchasing")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("purchasing.noAccess")}</p>
      </div>
    );
  }

  const suppliersById = suppliers.reduce((m, s) => ({ ...m, [s.id]: s.name }), {});

  const tabs = [
    { id: "suppliers", label: t("purchasing.suppliers") },
    ...(writable ? [{ id: "receive", label: t("purchasing.receiveStock") }] : []),
    { id: "bills", label: t("purchasing.bills") },
  ];

  return (
    <div>
      <PageHeader
        title={t("purchasing.title")}
        subtitle={t("purchasing.subtitle")}
        actions={
          writable &&
          tab === "bills" && (
            <Button onClick={() => setBillOpen(true)}>
              <Plus size={16} /> {t("purchasing.newBill")}
            </Button>
          )
        }
      />

      <div className="mb-6 flex gap-1 border-b border-line">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === tb.id
                ? "border-accent text-ink"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {tab === "suppliers" && (
        <SupplierList
          suppliers={suppliers}
          loading={loadingSuppliers}
          writable={writable}
          onNew={() => setFormOpen(true)}
        />
      )}
      {tab === "receive" && writable && (
        <ReceivingTerminal
          suppliers={suppliers}
          warehouses={warehouses}
          onReceived={() => setRefreshKey((k) => k + 1)}
        />
      )}
      {tab === "bills" && (
        <BillList
          suppliersById={suppliersById}
          bankAccounts={accounts}
          writable={writable}
          refreshKey={refreshKey}
        />
      )}

      <SupplierForm open={formOpen} onClose={() => setFormOpen(false)} onSaved={loadSuppliers} />
      <NewBillDrawer
        open={billOpen}
        onClose={() => setBillOpen(false)}
        onSaved={() => setRefreshKey((k) => k + 1)}
        suppliers={suppliers}
      />
    </div>
  );
}
