"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock } from "lucide-react";

import { inventory, sales, bankAccounts as bankApi } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { PageHeader } from "@/components/ui/kit";
import PosTerminal from "@/components/sales/PosTerminal";
import InvoiceList from "@/components/sales/InvoiceList";
import BankAccounts from "@/components/sales/BankAccounts";
import CashDrawer from "@/components/sales/CashDrawer";

export default function SalesPage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();
  const writable = canWrite("sales");
  const [tab, setTab] = useState(writable ? "pos" : "invoices");
  useEffect(() => { const requested = new URLSearchParams(window.location.search).get("tab");
    if (['pos', 'till', 'invoices', 'banks'].includes(requested)) setTab(requested);
  }, []);
  const [warehouses, setWarehouses] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  // The caller's open till session, lifted here so the POS can stamp every
  // sale with it and the till tab can show the running expectation.
  const [shift, setShift] = useState(null);
  const onShiftChange = useCallback((s) => setShift(s), []);

  const loadAccounts = () =>
    bankApi.list().then((r) => setAccounts(r.data.results || r.data)).catch(() => {});

  useEffect(() => {
    inventory.warehouses().then((r) => setWarehouses(r.data.results)).catch(() => {});
    sales.customers().then((r) => setCustomers(r.data.results)).catch(() => {});
    loadAccounts();
  }, []);

  if (!canRead("sales")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("sales.noAccess")}</p>
      </div>
    );
  }

  const tabs = [
    ...(writable ? [{ id: "pos", label: t("sales.pos") }] : []),
    ...(writable ? [{ id: "till", label: t("till.tab") }] : []),
    { id: "invoices", label: t("sales.invoices") },
    ...(writable ? [{ id: "banks", label: t("sales.bankAccounts") }] : []),
  ];

  return (
    <div>
      <PageHeader title={t("sales.title")} subtitle={t("sales.subtitle")} />

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

      {tab === "pos" && writable && (
        <PosTerminal
          warehouses={warehouses}
          customers={customers}
          bankAccounts={accounts}
          shift={shift}
          onSold={() => setRefreshKey((k) => k + 1)}
        />
      )}
      {/* Mounted on every tab so the shift is known before the till is opened —
          otherwise a cashier could ring up sales that belong to no drawer
          simply by never visiting this tab. Hidden rather than unmounted. */}
      <div className={tab === "till" && writable ? "" : "hidden"}>
        {writable && <CashDrawer onShiftChange={onShiftChange} />}
      </div>
      {tab === "invoices" && <InvoiceList refreshKey={refreshKey} />}
      {tab === "banks" && writable && (
        <BankAccounts writable={writable} onChanged={loadAccounts} />
      )}
    </div>
  );
}
