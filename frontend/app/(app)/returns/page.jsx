"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock, Plus } from "lucide-react";

import { returns } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, PageHeader } from "@/components/ui/kit";
import NewReturnDrawer from "@/components/returns/NewReturnDrawer";
import DispositionDrawer from "@/components/returns/DispositionDrawer";
import NotesList from "@/components/returns/NotesList";
import PurchaseReturnList from "@/components/returns/PurchaseReturnList";
import TabBar from "@/components/ui/TabBar";

export default function ReturnsPage() {
  const { canRead, canWrite } = useAuth();
  const { t } = useI18n();

  // Sales and purchase returns are separate authorities: a sales officer
  // handles what customers bring back, a purchasing officer what we send back
  // to suppliers. Each tab follows its own side.
  const canSales = canRead("sales_returns");
  const canPurchase = canRead("purchase_returns");
  const writable = canWrite("sales_returns");

  const tabs = [
    ...(canSales ? ["returns", "creditNotes"] : []),
    ...(canPurchase ? ["purchaseReturns", "debitNotes"] : []),
  ];

  const [tab, setTab] = useState(canSales ? "returns" : "purchaseReturns");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newOpen, setNewOpen] = useState(false);
  const [dispoFor, setDispoFor] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    returns
      .salesReturns({ page: 1 })
      .then((r) => setRows(r.data.results))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // A purchasing officer has no sales-returns access; skip the call rather
    // than firing a request that is guaranteed to 403.
    if (canSales) load();
    else setLoading(false);
  }, [load, canSales]);

  if (!canSales && !canPurchase) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("returns.noAccess")}</p>
      </div>
    );
  }

  const pendingCount = (r) =>
    (r.lines || []).filter((l) => l.disposition === "quarantine").length;

  return (
    <div>
      <PageHeader
        title={t("returns.title")}
        subtitle={t("returns.subtitle")}
        actions={
          writable && (
            <Button onClick={() => setNewOpen(true)}>
              <Plus size={16} /> {t("returns.newReturn")}
            </Button>
          )
        }
      />

      {/* The notes are the documents the other party actually receives, so they
          belong beside the returns that generated them (Rule #6). */}
      <TabBar
        className="mb-4"
        value={tab}
        onChange={setTab}
        tabs={tabs.map((key) => ({
          id: key,
          label: t(`returns.tab.${key}`),
          attentionKey: key === "returns" ? "returns" : undefined,
        }))}
      />

      {tab === "creditNotes" && <NotesList kind="credit" />}
      {tab === "purchaseReturns" && (
        <PurchaseReturnList writable={canWrite("purchase_returns")} />
      )}
      {tab === "debitNotes" && <NotesList kind="debit" />}

      {tab === "returns" && (
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3 text-start font-medium">{t("returns.return")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("returns.invoice")}</th>
                <th className="px-4 py-3 text-start font-medium">{t("returns.reason")}</th>
                <th className="px-4 py-3 text-end font-medium">{t("returns.lines")}</th>
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
                    {t("returns.noReturns")}
                  </td>
                </tr>
              )}
              {!loading &&
                rows.map((r) => {
                  const pending = pendingCount(r);
                  return (
                    <tr key={r.id} className="border-b border-line last:border-0">
                      <td className="tabular px-4 py-3 text-ink">#{r.id}</td>
                      <td className="tabular px-4 py-3 text-muted">{r.invoice}</td>
                      <td className="px-4 py-3 text-muted">{r.reason || "—"}</td>
                      <td className="tabular px-4 py-3 text-end text-ink">{r.lines?.length ?? 0}</td>
                      <td className="px-4 py-3 text-end">
                        {pending > 0 ? (
                          <Badge tone="warn">{pending} {t("returns.quarantined")}</Badge>
                        ) : (
                          <Badge tone="ok">{t("returns.dispositioned")}</Badge>
                        )}
                      </td>
                      {writable && (
                        <td className="px-4 py-3 text-end">
                          <button
                            onClick={() => setDispoFor(r)}
                            className="text-sm text-accent hover:underline"
                          >
                            {pending > 0 ? t("returns.disposition") : t("common.view")}
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </Card>
      )}

      <NewReturnDrawer open={newOpen} onClose={() => setNewOpen(false)} onCreated={load} />
      <DispositionDrawer
        salesReturn={dispoFor}
        open={Boolean(dispoFor)}
        onClose={() => setDispoFor(null)}
        onDone={load}
      />
    </div>
  );
}
