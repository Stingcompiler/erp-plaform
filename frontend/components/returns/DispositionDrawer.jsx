"use client";

import { useEffect, useState } from "react";

import { returns } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { enumLabel } from "@/lib/labels";

export default function DispositionDrawer({ salesReturn, open, onClose, onDone }) {
  const { t } = useI18n();
  const [decisions, setDecisions] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Only the warehouses the server will accept for a restock — its own branch
  // scope, not every warehouse in the company. Offering the full list would
  // present choices that fail on submit.
  const [warehouses, setWarehouses] = useState([]);

  useEffect(() => {
    setDecisions({});
    setError("");
  }, [salesReturn, open]);

  useEffect(() => {
    if (!open) return;
    returns
      .restockWarehouses()
      .then((r) => setWarehouses(r.data))
      .catch(() => setWarehouses([]));
  }, [open]);

  if (!salesReturn) return null;

  const quarantined = (salesReturn.lines || []).filter((l) => l.disposition === "quarantine");
  const settled = (salesReturn.lines || []).filter((l) => l.disposition !== "quarantine");

  const setAction = (lineId, patch) =>
    setDecisions((d) => ({ ...d, [lineId]: { ...d[lineId], ...patch } }));

  async function submit() {
    setError("");
    const payload = Object.entries(decisions)
      .filter(([, v]) => v.action)
      .map(([lineId, v]) => ({
        line_id: Number(lineId),
        action: v.action,
        ...(v.action === "restock" && v.warehouse ? { warehouse: Number(v.warehouse) } : {}),
      }));
    if (payload.length === 0) {
      setError(t("returns.chooseRestockScrap"));
      return;
    }
    setBusy(true);
    try {
      await returns.disposition(salesReturn.id, payload);
      onDone();
      onClose();
    } catch (err) {
      setError(errorText(err, t, "returns.dispositionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("returns.dispositionStock")}
      footer={
        quarantined.length > 0 && (
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button onClick={submit} disabled={busy}>
              {busy ? t("returns.applying") : t("returns.applyDisposition")}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        <p className="text-xs text-muted">{t("returns.dispositionHelp")}</p>

        {quarantined.length === 0 && (
          <p className="rounded-card border border-line bg-paper p-4 text-sm text-muted">
            {t("returns.allDispositioned")}
          </p>
        )}

        {quarantined.map((line) => {
          const d = decisions[line.id] || {};
          return (
            <div key={line.id} className="rounded-card border border-line p-3">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="text-ink">{t("returns.productN", { id: line.product })}</span>
                <span className="tabular text-muted">{t("returns.qtyN", { qty: line.quantity })}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setAction(line.id, { action: "restock" })}
                  className={`tap rounded-control border px-3 py-1.5 text-sm ${
                    d.action === "restock"
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-line text-muted hover:bg-paper"
                  }`}
                >
                  {t("returns.restockShort")}
                </button>
                <button
                  onClick={() => setAction(line.id, { action: "scrap", warehouse: undefined })}
                  className={`tap rounded-control border px-3 py-1.5 text-sm ${
                    d.action === "scrap"
                      ? "border-danger bg-danger/10 text-danger"
                      : "border-line text-muted hover:bg-paper"
                  }`}
                >
                  {t("returns.scrap")}
                </button>
                {d.action === "restock" && (
                  <Select
                    value={d.warehouse || ""}
                    onChange={(e) => setAction(line.id, { warehouse: e.target.value })}
                    className="w-auto"
                  >
                    <option value="">{t("returns.invoiceWarehouse")}</option>
                    {warehouses.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </Select>
                )}
              </div>
            </div>
          );
        })}

        {settled.length > 0 && (
          <div>
            <div className="mb-2 text-xs uppercase tracking-wide text-muted">{t("returns.alreadyDispositioned")}</div>
            <div className="space-y-1">
              {settled.map((line) => (
                <div key={line.id} className="flex items-center justify-between text-sm">
                  <span className="text-muted">{t("returns.productN", { id: line.product })} · {t("returns.qtyN", { qty: line.quantity })}</span>
                  <Badge tone={line.disposition === "restocked" ? "ok" : "muted"}>
                    {enumLabel(t, "reports.ops.disposition", line.disposition)}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Drawer>
  );
}
