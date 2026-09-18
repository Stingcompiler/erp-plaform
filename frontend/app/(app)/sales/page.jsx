"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock } from "lucide-react";

import { inventory, sales, bankAccounts as bankApi } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { PageHeader } from "@/components/ui/kit";
import PosTerminal from "@/components/sales/PosTerminal";
import QuotesOrders from "@/components/sales/QuotesOrders";
import { offlineStore } from "@/lib/offlineStore";
import InvoiceList from "@/components/sales/InvoiceList";
import BankAccounts from "@/components/sales/BankAccounts";
import CashDrawer from "@/components/sales/CashDrawer";
import ShiftHistory from "@/components/sales/ShiftHistory";
import TabBar from "@/components/ui/TabBar";

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
  // A confirmed sales order handed to the till to be invoiced.
  const [orderToInvoice, setOrderToInvoice] = useState(null);
  // The caller's open till session, lifted here so the POS can stamp every
  // sale with it and the till tab can show the running expectation.
  const [shift, setShift] = useState(null);
  const [shiftKey, setShiftKey] = useState(0);
  // Opening or closing the drawer changes what the history below must show.
  const onShiftChange = useCallback((s) => { setShift(s); setShiftKey((k) => k + 1); }, []);

  const loadAccounts = () =>
    bankApi.list().then((r) => setAccounts(r.data.results || r.data)).catch(() => {});

  useEffect(() => {
    // Offline: the till still needs a warehouse and a customer list, so a
    // failed request falls back to the locally mirrored records.
    inventory.warehouses()
      .then((r) => setWarehouses(r.data.results))
      .catch(() => offlineStore.getAll("warehouses").then(setWarehouses).catch(() => {}));
    sales.allCustomers()
      .then((r) => setCustomers(r.data))
      .catch(() => offlineStore.getAll("customers").then(setCustomers).catch(() => {}));
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
    { id: "quotes", label: t("quotes.tab") },
    { id: "invoices", label: t("sales.invoices"), attentionKey: "sales" },
    ...(writable ? [{ id: "banks", label: t("sales.bankAccounts") }] : []),
  ];

  return (
    <div>
      <PageHeader title={t("sales.title")} subtitle={t("sales.subtitle")} />

      <TabBar value={tab} onChange={setTab} tabs={tabs} />

      {tab === "pos" && writable && (
        <PosTerminal
          warehouses={warehouses}
          customers={customers}
          onCustomersChanged={() => sales.allCustomers().then((rows) => setCustomers(rows)).catch(() => {})}
          bankAccounts={accounts}
          shift={shift}
          initialOrder={orderToInvoice}
          onSold={() => { setOrderToInvoice(null); setRefreshKey((k) => k + 1); }}
        />
      )}
      {tab === "quotes" && (
        <QuotesOrders
          customers={customers}
          writable={writable}
          refreshKey={refreshKey}
          onInvoice={(order) => { setOrderToInvoice(order); setTab("pos"); }}
        />
      )}
      {/* Mounted on every tab so the shift is known before the till is opened —
          otherwise a cashier could ring up sales that belong to no drawer
          simply by never visiting this tab. Hidden rather than unmounted. */}
      <div className={tab === "till" && writable ? "" : "hidden"}>
        {writable && <CashDrawer onShiftChange={onShiftChange} />}
        {writable && tab === "till" && <ShiftHistory refreshKey={`${refreshKey}-${shiftKey}`} />}
      </div>
      {tab === "invoices" && <InvoiceList refreshKey={refreshKey} />}
      {tab === "banks" && writable && (
        <BankAccounts writable={writable} onChanged={loadAccounts} />
      )}
    </div>
  );
}
