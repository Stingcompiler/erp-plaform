"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, HandCoins, Lock, Pencil, Search, UserPlus, UsersRound, Wallet } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { sales } from "@/lib/api";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";
import CollectPaymentDrawer from "@/components/sales/CollectPaymentDrawer";
import CustomerDrawer from "@/components/sales/CustomerDrawer";

const STATUS_TONE = { overdue: "danger", owing: "warn", credit: "accent", settled: "ok" };

function amount(value, language) {
  return Number(value || 0).toLocaleString(language === "ar" ? "ar" : "en", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function date(value, language) {
  return value ? new Date(value).toLocaleDateString(language === "ar" ? "ar" : "en") : "—";
}

export default function DebtsPage() {
  const { canRead, canWrite } = useAuth();
  const { t, language } = useI18n();
  const allowed = canRead("sales");
  const canCollect = canWrite("sales");
  const [collecting, setCollecting] = useState(false);
  // null = closed, "new" = create, object = edit that customer
  const [editing, setEditing] = useState(null);
  const [filters, setFilters] = useState({ search: "", status: "" });
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [selected, setSelected] = useState(null);
  const [statement, setStatement] = useState(null);
  const [dates, setDates] = useState({ start: "", end: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadList = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    setError("");
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
      const [listResponse, summaryResponse] = await Promise.all([
        sales.debtCustomers(params),
        sales.debtSummary(),
      ]);
      setRows(listResponse.data.results || []);
      setSummary(summaryResponse.data);
    } catch {
      setError(t("debts.loadError"));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [allowed, filters, t]);

  const loadStatement = useCallback(async () => {
    if (!selected) return;
    try {
      const params = Object.fromEntries(Object.entries(dates).filter(([, value]) => value));
      const response = await sales.debtStatement(selected.id, params);
      setStatement(response.data);
    } catch {
      setStatement(null);
      setError(t("debts.loadError"));
    }
  }, [dates, selected, t]);

  useEffect(() => {
    const timeout = setTimeout(loadList, 200);
    return () => clearTimeout(timeout);
  }, [loadList]);

  useEffect(() => {
    loadStatement();
  }, [loadStatement]);

  if (!allowed) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("sales.noAccess")}</p>
      </div>
    );
  }

  const cards = [
    { label: "debts.outstanding", value: summary?.outstanding, icon: Wallet, tone: "text-accent" },
    { label: "debts.overdueTotal", value: summary?.overdue, icon: AlertTriangle, tone: "text-danger" },
    { label: "debts.creditTotal", value: summary?.credit_balance, icon: Wallet, tone: "text-ok" },
    { label: "debts.debtors", value: summary?.debtor_count, icon: UsersRound, tone: "text-ink", count: true },
  ];

  return (
    <div>
      <PageHeader title={t("debts.title")} subtitle={t("debts.subtitle")} />
      <CustomerDrawer
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        customer={editing === "new" ? null : editing}
        onSaved={(saved) => { loadList(); if (editing !== "new") setSelected((c) => ({ ...c, ...saved })); }}
      />

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, tone, count }) => (
          <Card key={label} className="p-4">
            <div className="flex items-center justify-between text-sm text-muted">
              <span>{t(label)}</span><Icon size={18} className={tone} />
            </div>
            <div className={`mt-2 tabular text-2xl font-semibold ${tone}`}>
              {count ? (value ?? "—") : amount(value, language)}
            </div>
          </Card>
        ))}
      </div>

      {error && <p className="mb-4 rounded-control bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(330px,0.85fr)_minmax(0,1.6fr)]">
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="font-display text-lg font-semibold">{t("debts.customers")}</h2>
            <div className="flex items-center gap-2">
              {loading && <span className="text-xs text-muted">…</span>}
              {canCollect && (
                <Button variant="outline" onClick={() => setEditing("new")}>
                  <UserPlus size={15} />{t("customers.new")}
                </Button>
              )}
            </div>
          </div>
          <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_132px] xl:grid-cols-1">
            <div className="relative">
              <Search size={15} className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted" />
              <Input className="ps-9" placeholder={t("debts.search")} value={filters.search}
                onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} />
            </div>
            <Select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
              <option value="">{t("debts.all")}</option>
              <option value="overdue">{t("debts.overdue")}</option>
              <option value="owing">{t("debts.owing")}</option>
              <option value="credit">{t("debts.credit")}</option>
            </Select>
          </div>
          <div className="max-h-[560px] space-y-1 overflow-y-auto">
            {!loading && rows.length === 0 && <p className="px-2 py-8 text-center text-sm text-muted">{t("debts.noDebtors")}</p>}
            {rows.map((customer) => (
              <button key={customer.id} onClick={() => setSelected(customer)}
                className={`w-full rounded-control px-3 py-3 text-start transition-colors ${selected?.id === customer.id ? "bg-accent text-white" : "hover:bg-paper"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0"><div className="truncate font-medium">{customer.name}</div><div className={`mt-0.5 truncate text-xs ${selected?.id === customer.id ? "text-white/75" : "text-muted"}`}>{customer.phone || "—"}</div></div>
                  <div className="text-end"><Badge tone={selected?.id === customer.id ? "muted" : STATUS_TONE[customer.status]}>{t(`debts.${customer.status}`)}</Badge><div className="mt-1 tabular text-sm font-semibold">{amount(customer.outstanding || customer.credit_balance, language)}</div></div>
                </div>
              </button>
            ))}
          </div>
        </Card>

        <div>
          {!selected && <Card className="p-10 text-center text-muted">{t("debts.selectCustomer")}</Card>}
          {selected && (
            <>
              <Card className="mb-4 p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div><h2 className="font-display text-xl font-semibold">{selected.name}</h2><p className="mt-1 text-sm text-muted"><PhoneLink phone={selected.phone} /></p></div>
                  <div className="flex items-center gap-4">
                    <div className="text-end"><div className="text-xs text-muted">{t("debts.closingBalance")}</div><div className="tabular text-xl font-semibold">{amount(statement?.closing_balance, language)}</div></div>
                    {canCollect && (
                      <Button variant="outline" onClick={() => setEditing(selected)} aria-label={t("customers.edit")}>
                        <Pencil size={15} />{t("customers.edit")}
                      </Button>
                    )}
                    {canCollect && Number(statement?.closing_balance || selected.outstanding || 0) > 0 && (
                      <Button onClick={() => setCollecting(true)}><HandCoins size={16} />{t("debts.collect")}</Button>
                    )}
                  </div>
                </div>
              </Card>
              <CollectPaymentDrawer
                open={collecting}
                onClose={() => setCollecting(false)}
                customer={selected}
                onDone={() => { loadStatement(); loadList(); }}
              />
              <Card className="p-4">
                <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><h2 className="font-display text-lg font-semibold">{t("debts.statement")}</h2><div className="flex flex-wrap items-end gap-2"><Field label={t("debts.from")}><Input type="date" value={dates.start} onChange={(event) => setDates((current) => ({ ...current, start: event.target.value }))} /></Field><Field label={t("debts.to")}><Input type="date" value={dates.end} onChange={(event) => setDates((current) => ({ ...current, end: event.target.value }))} /></Field><Button onClick={loadStatement}>{t("debts.apply")}</Button><Button variant="ghost" onClick={() => setDates({ start: "", end: "" })}>{t("debts.clear")}</Button></div></div>
                <div className="mb-3 grid grid-cols-2 gap-3"><div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("debts.openingBalance")}</div><div className="mt-1 tabular font-semibold">{amount(statement?.opening_balance, language)}</div></div><div className="rounded-control bg-paper p-3"><div className="text-xs text-muted">{t("debts.closingBalance")}</div><div className="mt-1 tabular font-semibold">{amount(statement?.closing_balance, language)}</div></div></div>
                {(statement?.events || []).length === 0 ? <p className="py-8 text-center text-sm text-muted">{t("debts.noEvents")}</p> : <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-sm"><thead className="border-b border-line text-start text-xs text-muted"><tr><th className="px-2 py-2 font-medium">{t("common.date")}</th><th className="px-2 py-2 font-medium">{t("common.reference")}</th><th className="px-2 py-2 font-medium">{t("debts.debit")}</th><th className="px-2 py-2 font-medium">{t("debts.creditColumn")}</th><th className="px-2 py-2 font-medium">{t("debts.balance")}</th></tr></thead><tbody>{statement.events.map((event, index) => <tr key={`${event.type}-${event.reference}-${index}`} className="border-b border-line/70"><td className="px-2 py-3 text-muted">{date(event.date, language)}</td><td className="px-2 py-3"><div className="font-medium">{t(`debts.${event.type}`)}</div><div className="text-xs text-muted">{event.reference}</div></td><td className="px-2 py-3 tabular">{event.debit === "0.00" ? "—" : amount(event.debit, language)}</td><td className="px-2 py-3 tabular">{event.credit === "0.00" ? "—" : amount(event.credit, language)}</td><td className="px-2 py-3 tabular font-semibold">{amount(event.balance, language)}</td></tr>)}</tbody></table></div>}
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
