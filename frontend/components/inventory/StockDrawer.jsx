"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRightLeft } from "lucide-react";

import { inventory } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useOfflineMutation } from "@/components/sync/useOfflineMutation";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { useStableIds } from "@/lib/useStableIds";

// Mirrors StockAdjustment.REASON_CHOICES on the server: a coded reason is
// what lets shrinkage be reported by cause rather than as free text.
const REASON_CODES = ["count", "damage", "expiry", "theft", "sample", "opening", "other"];

const MOVE_KEY = {
  sale_out: "inventory.mvSaleOut",
  purchase_in: "inventory.mvPurchaseIn",
  adjustment: "inventory.mvAdjustment",
  transfer: "inventory.mvTransfer",
  sales_return_in: "inventory.mvSalesReturnIn",
  purchase_return_out: "inventory.mvPurchaseReturnOut",
};

export default function StockDrawer({ open, onClose, product, warehouses, canWrite, onChanged }) {
  const { idFor, reset } = useStableIds();
  const { t, language } = useI18n();
  const mutate = useOfflineMutation();
  const [stock, setStock] = useState(null);
  // "unavailable" (not null) once the server could not answer: the balance
  // block hides, but the adjustment/transfer forms still open — offline is
  // exactly when a stock count needs recording.
  const [stockState, setStockState] = useState("loading");
  const [movements, setMovements] = useState([]);
  const [adjust, setAdjust] = useState({ warehouse: "", quantity: "", reason: "", reason_code: "count" });
  const [transfer, setTransfer] = useState({ source: "", dest: "", quantity: "" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!product) return;
    try {
      const [s, m] = await Promise.all([
        inventory.stock(product.id),
        inventory.movements(product.id),
      ]);
      setStock(s.data);
      setStockState("ready");
      setMovements((m.data.results || m.data).slice(0, 12));
    } catch {
      setStock(null);
      setStockState("unavailable");
    }
  }, [product]);

  useEffect(() => {
    if (open) {
      reset();
      setMsg("");
      setStockState("loading");
      setAdjust({ warehouse: "", quantity: "", reason: "", reason_code: "count" });
      setTransfer({ source: "", dest: "", quantity: "" });
      load();
    }
  }, [open, load, reset]);

  async function submitAdjustment() {
    setMsg("");
    if (!adjust.warehouse || !adjust.quantity) {
      setMsg(t("inventory.chooseWhQty"));
      return;
    }
    if (!adjust.reason.trim()) {
      setMsg(t("inventory.reasonRequired"));
      return;
    }
    setBusy(true);
    try {
      const result = await mutate("stock_adjustment", inventory.createAdjustment, {
        client_uuid: idFor("adjustment"),
        product: product.id,
        warehouse: Number(adjust.warehouse),
        quantity: adjust.quantity,
        reason: adjust.reason,
        reason_code: adjust.reason_code,
      });
      setAdjust({ warehouse: "", quantity: "", reason: "", reason_code: "count" });
      reset();
      if (!result.queued) await load();
      onChanged?.();
      setMsg(result.queued ? t("sync.savedForUpload") : t("inventory.stockAdjusted"));
    } catch (err) {
      setMsg(errorText(err, t, "inventory.adjustmentFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function submitTransfer() {
    setMsg("");
    if (!transfer.source || !transfer.dest || !transfer.quantity) {
      setMsg(t("inventory.chooseWhQty"));
      return;
    }
    if (transfer.source === transfer.dest) {
      setMsg(t("inventory.sameWarehouse"));
      return;
    }
    setBusy(true);
    try {
      const result = await mutate("stock_transfer", inventory.createTransfer, {
        client_uuid: idFor("transfer"),
        product: product.id,
        source_warehouse: Number(transfer.source),
        dest_warehouse: Number(transfer.dest),
        quantity: transfer.quantity,
      });
      setTransfer({ source: "", dest: "", quantity: "" });
      reset();
      if (!result.queued) await load();
      onChanged?.();
      setMsg(result.queued ? t("sync.savedForUpload") : t("inventory.transferred"));
    } catch (err) {
      setMsg(errorText(err, t, "inventory.transferError"));
    } finally {
      setBusy(false);
    }
  }

  const dateFmt = (d) => (d ? new Date(d).toLocaleDateString(language === "ar" ? "ar" : "en") : "");

  return (
    <Drawer open={open} onClose={onClose} title={product ? `${product.sku} — ${t("inventory.stockSuffix")}` : t("inventory.stock")}>
      {stockState === "loading" ? (
        <p className="text-muted">{t("inventory.loadingStock")}</p>
      ) : (
        <div className="space-y-6">
          {stock ? (
          <div>
            <div className="text-sm text-muted">{t("inventory.onHand")}</div>
            <div className="tabular mt-1 text-3xl font-medium text-ink">{stock.on_hand}</div>
          </div>
          ) : (
            <p className="rounded-control bg-warn/10 p-3 text-sm text-ink">{t("inventory.stockUnavailableOffline")}</p>
          )}

          {stock && <div>
            <div className="mb-2 text-sm font-medium text-ink">{t("inventory.byWarehouse")}</div>
            {stock.by_warehouse.length === 0 ? (
              <p className="text-sm text-muted">{t("inventory.noMovements")}</p>
            ) : (
              <div className="divide-y divide-line rounded-card border border-line">
                {stock.by_warehouse.map((row) => (
                  <div key={row.warehouse} className="flex items-center justify-between px-3 py-2 text-sm">
                    <span className="text-ink">{row.warehouse__name}</span>
                    <span className="tabular text-ink">{row.on_hand}</span>
                  </div>
                ))}
              </div>
            )}
          </div>}

          {canWrite && (
            <div className="rounded-card border border-line p-4">
              <div className="mb-3 text-sm font-medium text-ink">{t("inventory.adjustStock")}</div>
              <p className="mb-3 text-xs text-muted">{t("inventory.adjustHint")}</p>
              <div className="space-y-3">
                <Field label={t("inventory.warehouse")}>
                  <Select
                    value={adjust.warehouse}
                    onChange={(e) => setAdjust((a) => ({ ...a, warehouse: e.target.value }))}
                  >
                    <option value="">{t("common.select")}</option>
                    {warehouses.map((w) => (
                      <option key={w.id} value={w.id}>{w.name}</option>
                    ))}
                  </Select>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t("inventory.quantityPm")}>
                    <Input
                      type="number"
                      value={adjust.quantity}
                      onChange={(e) => setAdjust((a) => ({ ...a, quantity: e.target.value }))}
                    />
                  </Field>
                  <Field label={t("inventory.reasonCode")}>
                    <Select
                      value={adjust.reason_code}
                      onChange={(e) => setAdjust((a) => ({ ...a, reason_code: e.target.value }))}
                    >
                      {REASON_CODES.map((code) => (
                        <option key={code} value={code}>{t(`inventory.reasonCodes.${code}`)}</option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <Field label={t("inventory.reason")}>
                  <Input
                    value={adjust.reason}
                    onChange={(e) => setAdjust((a) => ({ ...a, reason: e.target.value }))}
                  />
                </Field>
                <Button onClick={submitAdjustment} disabled={busy}>
                  {busy ? t("inventory.posting") : t("inventory.postAdjustment")}
                </Button>
              </div>
            </div>
          )}

          {/* Transfer between warehouses (needs at least two) */}
          {canWrite && warehouses.length >= 2 && (
            <div className="rounded-card border border-line p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-ink">
                <ArrowRightLeft size={15} /> {t("inventory.transferStock")}
              </div>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t("inventory.fromWarehouse")}>
                    <Select
                      value={transfer.source}
                      onChange={(e) => setTransfer((x) => ({ ...x, source: e.target.value }))}
                    >
                      <option value="">{t("common.select")}</option>
                      {warehouses.map((w) => (
                        <option key={w.id} value={w.id}>{w.name}</option>
                      ))}
                    </Select>
                  </Field>
                  <Field label={t("inventory.toWarehouse")}>
                    <Select
                      value={transfer.dest}
                      onChange={(e) => setTransfer((x) => ({ ...x, dest: e.target.value }))}
                    >
                      <option value="">{t("common.select")}</option>
                      {warehouses.map((w) => (
                        <option key={w.id} value={w.id}>{w.name}</option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <Field label={t("common.quantity")}>
                  <Input
                    type="number"
                    value={transfer.quantity}
                    onChange={(e) => setTransfer((x) => ({ ...x, quantity: e.target.value }))}
                  />
                </Field>
                <Button variant="outline" onClick={submitTransfer} disabled={busy}>
                  <ArrowRightLeft size={15} /> {t("inventory.transfer")}
                </Button>
              </div>
            </div>
          )}

          {/* Movement history */}
          <div>
            <div className="mb-2 text-sm font-medium text-ink">{t("inventory.movementHistory")}</div>
            {movements.length === 0 ? (
              <p className="text-sm text-muted">{t("inventory.noMovementsYet")}</p>
            ) : (
              <div className="divide-y divide-line rounded-card border border-line">
                {movements.map((m) => (
                  <div key={m.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <Badge tone={Number(m.quantity) < 0 ? "danger" : "ok"}>
                        {t(MOVE_KEY[m.movement_type] || "inventory.mvAdjustment")}
                      </Badge>
                      <span className="text-xs text-muted">{dateFmt(m.created_at)}</span>
                    </div>
                    <span className="tabular text-ink">{m.quantity}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {msg && <p className="text-sm text-muted">{msg}</p>}
        </div>
      )}
    </Drawer>
  );
}
