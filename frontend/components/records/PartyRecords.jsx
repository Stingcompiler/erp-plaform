"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FileText, Lock, Search } from "lucide-react";

import { purchasing, returns, sales } from "@/lib/api";
import DocumentDrawer from "@/components/print/DocumentDrawer";

import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";
import { SkeletonRows } from "@/components/ui/Skeleton";

const STATUS_TONE = {
  active: "ok",
  settled: "ok",
  owing: "warn",
  overdue: "danger",
  suspended: "muted",
};
const STATUS_KEY = {
  active: "records.statusActive",
  settled: "records.statusSettled",
  owing: "records.statusOwing",
  overdue: "records.statusOverdue",
  suspended: "records.statusSuspended",
};
// Rows that have a printable document behind them, per party kind.
const DOCUMENT_FETCHERS = {
  customer: {
    invoice: sales.invoiceDocument,
    payment: sales.paymentDocument,
    credit_note: returns.creditNoteDocument,
    refund: sales.refundDocument,
  },
  supplier: {
    payment: purchasing.supplierPaymentDocument,
    debit_note: returns.debitNoteDocument,
  },
};

const TYPE_KEY = {
  refund: "records.typeRefund",
  quotation: "records.typeQuotation",
  order: "records.typeOrder",
  invoice: "records.typeInvoice",
  payment: "records.typePayment",
  return: "records.typeReturn",
  credit_note: "records.typeCreditNote",
  debit_note: "records.typeDebitNote",
  purchase_order: "records.typePurchaseOrder",
  goods_receipt: "records.typeGoodsReceipt",
  bill: "records.typeBill",
  data_change: "records.typeDataChange",
};
const TYPE_TONE = {
  invoice: "accent",
  bill: "accent",
  payment: "ok",
  return: "warn",
  credit_note: "danger",
  debit_note: "danger",
  refund: "warn",
  data_change: "muted",
};

/**
 * Shared "360° record" screen for a customer or supplier: pick a party on the
 * left, see their profile, account status and full chronological activity on
 * the right. Both pages are identical in shape, so the only differences are
 * passed in as props — including which RBAC module gates the page.
 */
export default function PartyRecords({
  kind, // "customer" | "supplier"
  module, // RBAC module gating this page
  fetchList,
  fetchRecords,
  csvUrl,
  titleKey,
  subtitleKey,
  selectKey,
  createdKey,
  noAccessKey,
  typeOptions,
}) {
  const { canRead } = useAuth();
  const { t, language } = useI18n();
  const allowed = canRead(module);
  const fetchers = DOCUMENT_FETCHERS[kind] || {};
  const [doc, setDoc] = useState(null); // { type, id }

  const [parties, setParties] = useState([]);
  const [partyQuery, setPartyQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ search: "", type: "", start: "", end: "" });

  useEffect(() => {
    if (!allowed) return;
    fetchList({ page: 1 })
      .then((r) => setParties(r.data.results || r.data))
      .catch(() => setParties([]));
  }, [allowed, fetchList]);

  const load = useCallback(() => {
    if (!selected) return;
    setLoading(true);
    const params = Object.fromEntries(
      Object.entries(filters).filter(([, v]) => v !== "")
    );
    fetchRecords(selected.id, params)
      .then((r) => setRecord(r.data))
      .catch(() => setRecord(null))
      .finally(() => setLoading(false));
  }, [selected, filters, fetchRecords]);

  useEffect(() => {
    load();
  }, [load]);

  const visibleParties = useMemo(() => {
    const q = partyQuery.trim().toLowerCase();
    return q ? parties.filter((p) => p.name.toLowerCase().includes(q)) : parties;
  }, [parties, partyQuery]);

  const profile = record?.[kind];
  const events = record?.events || [];
  const money = (v) =>
    v == null
      ? "—"
      : Number(v).toLocaleString(language === "ar" ? "ar" : "en", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
  const dt = (d) => (d ? new Date(d).toLocaleString(language === "ar" ? "ar" : "en") : "—");
  const day = (d) => (d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "—");

  if (!allowed) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t(noAccessKey)}</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t(titleKey)} subtitle={t(subtitleKey)} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        {/* Party picker */}
        <Card className="p-3">
          <div className="relative mb-2">
            <Search
              size={15}
              className="pointer-events-none absolute inset-y-0 start-3 my-auto text-muted"
            />
            <Input
              className="ps-9"
              placeholder={t("records.searchParty")}
              value={partyQuery}
              onChange={(e) => setPartyQuery(e.target.value)}
            />
          </div>
          <div className="max-h-[420px] space-y-1 overflow-y-auto">
            {visibleParties.length === 0 && (
              <p className="px-2 py-6 text-center text-sm text-muted">{t("records.noParties")}</p>
            )}
            {visibleParties.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelected(p)}
                className={`tap w-full rounded-control px-3 py-2 text-start text-sm transition-colors ${
                  selected?.id === p.id
                    ? "bg-accent text-white"
                    : "text-ink hover:bg-paper"
                }`}
              >
                <div className="truncate font-medium">{p.name}</div>
                <div
                  className={`truncate text-xs ${
                    selected?.id === p.id ? "text-white/75" : "text-muted"
                  }`}
                >
                  {p.phone || p.email || "—"}
                </div>
              </button>
            ))}
          </div>
        </Card>

        {/* Record detail */}
        <div>
          {!selected && (
            <Card className="p-10 text-center text-muted">{t(selectKey)}</Card>
          )}

          {selected && profile && (
            <>
              {/* Profile + status */}
              <Card className="mb-4 p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="font-display text-xl font-semibold text-ink">{profile.name}</h2>
                    <div className="mt-1 flex flex-wrap gap-x-4 text-sm text-muted">
                      {profile.phone && <PhoneLink phone={profile.phone} />}
                      {profile.email && <span>{profile.email}</span>}
                      {profile.address && <span>{profile.address}</span>}
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {t(createdKey)}: {day(profile.created_at)}
                    </div>
                  </div>
                  <div className="text-end">
                    <Badge tone={STATUS_TONE[profile.status] || "muted"}>
                      {t(STATUS_KEY[profile.status] || "records.statusActive")}
                    </Badge>
                    <div className="mt-2 text-xs text-muted">{t("records.balance")}</div>
                    <div className="tabular text-lg font-semibold text-ink">
                      {money(profile.balance)}
                    </div>
                  </div>
                </div>
              </Card>

              {/* Filters + export */}
              <Card className="mb-4 p-4">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Field label={t("common.search")}>
                    <Input
                      placeholder={t("records.searchEvents")}
                      value={filters.search}
                      onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                    />
                  </Field>
                  <Field label={t("records.filterType")}>
                    <Select
                      value={filters.type}
                      onChange={(e) => setFilters((f) => ({ ...f, type: e.target.value }))}
                    >
                      <option value="">{t("records.allTypes")}</option>
                      {typeOptions.map((ty) => (
                        <option key={ty} value={ty}>{t(TYPE_KEY[ty] || ty)}</option>
                      ))}
                    </Select>
                  </Field>
                  <Field label={t("records.from")}>
                    <Input
                      type="date"
                      value={filters.start}
                      onChange={(e) => setFilters((f) => ({ ...f, start: e.target.value }))}
                    />
                  </Field>
                  <Field label={t("records.to")}>
                    <Input
                      type="date"
                      value={filters.end}
                      onChange={(e) => setFilters((f) => ({ ...f, end: e.target.value }))}
                    />
                  </Field>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <span className="tabular text-sm text-muted">
                    {t("records.eventCount", { count: events.length })}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      onClick={() => setFilters({ search: "", type: "", start: "", end: "" })}
                    >
                      {t("records.clear")}
                    </Button>
                    <a href={csvUrl(selected.id, filters)}>
                      <Button variant="outline">
                        <Download size={15} /> {t("records.export")}
                      </Button>
                    </a>
                  </div>
                </div>
              </Card>

              {/* Chronological activity */}
              {loading && <SkeletonRows />}
              {!loading && events.length === 0 && (
                <Card className="p-8 text-center text-muted">{t("records.noEvents")}</Card>
              )}
              {!loading && events.length > 0 && (
                <Card>
                  <div className="overflow-x-auto">
                    <table className="stack-sm w-full text-sm">
                      <thead>
                        <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                          <th className="px-4 py-3 text-start font-medium">{t("common.date")}</th>
                          <th className="px-4 py-3 text-start font-medium">{t("records.filterType")}</th>
                          <th className="px-4 py-3 text-start font-medium">{t("common.reference")}</th>
                          <th className="px-4 py-3 text-end font-medium">{t("common.amount")}</th>
                          <th className="px-4 py-3 text-start font-medium">{t("logs.changes")}</th>
                          <th className="px-4 py-3" />
                        </tr>
                      </thead>
                      <tbody>
                        {events.map((e, i) => (
                          <tr key={i} className="border-b border-line last:border-0">
                            <td className="tabular whitespace-nowrap px-4 py-3 text-muted">{dt(e.date)}</td>
                            <td className="px-4 py-3">
                              <Badge tone={TYPE_TONE[e.type] || "muted"}>
                                {t(TYPE_KEY[e.type] || e.type)}
                              </Badge>
                            </td>
                            <td className="tabular px-4 py-3 text-ink">{e.reference || "—"}</td>
                            <td className="tabular px-4 py-3 text-end text-ink">{money(e.amount)}</td>
                            <td className="px-4 py-3 text-xs text-muted">{e.meta || "—"}</td>
                            <td className="px-4 py-3 text-end">
                              {fetchers[e.type] && e.entity_id && (
                                <button
                                  onClick={() => setDoc({ type: e.type, id: e.entity_id })}
                                  className="inline-flex items-center gap-1 text-sm text-accent hover:underline"
                                  title={t("records.print")}
                                  aria-label={t("records.print")}
                                >
                                  <FileText size={15} />{t("records.print")}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
      <DocumentDrawer
        open={Boolean(doc)}
        onClose={() => setDoc(null)}
        fetcher={doc ? fetchers[doc.type] : null}
        id={doc?.id}
        title={doc ? t(TYPE_KEY[doc.type] || doc.type) : ""}
      />
    </div>
  );
}
