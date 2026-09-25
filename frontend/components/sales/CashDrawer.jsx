"use client";

import { useCallback, useEffect, useState } from "react";
import { Banknote, CheckCircle2, LockKeyhole, Plus } from "lucide-react";

import { cashShifts } from "@/lib/api";
import { useI18n } from "../../app/providers/I18nProvider";
import { useToast } from "@/components/ui/Toast";
import Drawer from "@/components/ui/Drawer";
import { Badge, Button, Card, Field, Input, Select } from "@/components/ui/kit";
import { errorText } from "@/lib/errors";
import { useSync } from "@/components/sync/SyncProvider";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { formatAmount } from "@/lib/money";

const money = (v) =>
  formatAmount(v);

/** Kinds a cashier can record, with the sign the API demands for each.
 * No "refund": a refund moves the drawer from its return or invoice, which
 * links the document — a loose one here paid the customer twice. */
const MOVEMENT_KINDS = [
  { kind: "drop", sign: -1 },
  { kind: "petty", sign: -1 },
  { kind: "float_add", sign: +1 },
  { kind: "correction", sign: 0 },
];

function Row({ label, value, currency, strong, tone }) {
  const toneClass =
    tone === "danger" ? "text-danger" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-muted">{label}</span>
      <span className={`tabular ${strong ? "text-base font-semibold" : "text-sm"} ${toneClass}`}>
        {money(value)} {currency}
      </span>
    </div>
  );
}

/**
 * Records cash into or out of the drawer for a reason other than a sale.
 *
 * The sign is derived from the chosen reason rather than typed, so a cashier
 * enters a plain positive number and cannot accidentally book a refund as a
 * deposit — which would hide a shortfall instead of explaining it.
 */
function MovementDrawer({ shift, open, onClose, onSaved }) {
  const { t } = useI18n();
  const toast = useToast();
  const [kind, setKind] = useState("drop");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [direction, setDirection] = useState("out");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setKind("drop");
    setAmount("");
    setReason("");
    setDirection("out");
  }, [open]);

  const spec = MOVEMENT_KINDS.find((k) => k.kind === kind);
  const signed = () => {
    const n = Math.abs(Number(amount || 0));
    if (!n) return 0;
    const sign = spec.sign !== 0 ? spec.sign : direction === "out" ? -1 : +1;
    return n * sign;
  };

  async function save() {
    const value = signed();
    if (!value) {
      toast.error(t("till.amountRequired"));
      return;
    }
    setBusy(true);
    try {
      await cashShifts.addMovement({
        client_uuid: crypto.randomUUID(),
        shift: shift.id,
        kind,
        amount: String(value),
        reason,
      });
      onSaved();
      onClose();
    } catch (err) {
      toast.error(errorText(err, t, "till.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("till.recordMovement")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={busy}>
            {busy ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Field label={t("till.movementKind")}>
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {MOVEMENT_KINDS.map((k) => (
              <option key={k.kind} value={k.kind}>
                {t(`till.kind.${k.kind}`)}
              </option>
            ))}
          </Select>
        </Field>

        {/* A correction is the one kind that can go either way, so it is the
            only one that asks. */}
        {spec.sign === 0 && (
          <Field label={t("till.direction")}>
            <Select value={direction} onChange={(e) => setDirection(e.target.value)}>
              <option value="out">{t("till.cashOut")}</option>
              <option value="in">{t("till.cashIn")}</option>
            </Select>
          </Field>
        )}

        <Field
          label={t("doc.amount")}
          hint={
            signed() < 0
              ? t("till.willLeaveDrawer")
              : signed() > 0
                ? t("till.willEnterDrawer")
                : undefined
          }
        >
          <Input
            type="number"
            min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </Field>

        <Field label={t("till.reason")}>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      </div>
    </Drawer>
  );
}

function CloseDrawer({ shift, open, onClose, onClosed }) {
  const { t } = useI18n();
  const toast = useToast();
  // Sales rung into this drawer that are still waiting to upload: their
  // cash is in the drawer but not yet in the expected figure. Counting now
  // shows a false overage, so the close waits for them.
  const { operations, flush, flushing, online } = useSync();
  const waiting = operations.filter(
    (op) => op.op_type === "pos_checkout" && !op.error && Number(op.payload?.shift) === Number(shift?.id),
  ).length;
  const [counted, setCounted] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setCounted("");
    setNote("");
  }, [open]);

  // The expected figure is deliberately NOT shown before the count is entered:
  // seeing it first turns counting into confirming, which is how a shortfall
  // gets rubber-stamped.
  const entered = counted !== "" && !Number.isNaN(Number(counted));
  const variance = entered
    ? Number(counted) - Number(shift?.expected_cash ?? 0)
    : null;

  async function submit() {
    setBusy(true);
    try {
      await cashShifts.close(shift.id, { counted_cash: String(counted), note });
      onClosed();
      onClose();
    } catch (err) {
      toast.error(errorText(err, t, "till.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("till.closeShift")}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={busy || !entered || waiting > 0}>
            {busy ? t("common.saving") : t("till.confirmClose")}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {waiting > 0 && (
          <div role="alert" className="space-y-2 rounded-card border border-warn/40 bg-warn/5 p-3 text-sm text-warn">
            <p>{t("till.waitingSales", { count: waiting })}</p>
            {online && (
              <Button variant="outline" onClick={flush} disabled={flushing}>{t("till.syncNow")}</Button>
            )}
          </div>
        )}
        <p className="rounded-card border border-line bg-paper p-3 text-xs text-muted">
          {t("till.countHint")}
        </p>

        <Field label={t("till.countedCash")}>
          <Input
            type="number"
            min="0"
            value={counted}
            onChange={(e) => setCounted(e.target.value)}
            autoFocus
          />
        </Field>

        {entered && (
          <div className="rounded-card border border-line p-3">
            <Row
              label={t("till.expected")}
              value={shift.expected_cash}
              currency=""
            />
            <Row
              label={t("till.variance")}
              value={variance}
              currency=""
              strong
              tone={variance === 0 ? "ok" : "danger"}
            />
            {variance !== 0 && (
              <p className="mt-2 text-xs text-muted">
                {variance < 0 ? t("till.shortBy") : t("till.overBy")}
              </p>
            )}
          </div>
        )}

        <Field label={t("till.noteOptional")}>
          <Input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
    </Drawer>
  );
}

export default function CashDrawer({ currency = "", onShiftChange }) {
  const { t, language } = useI18n();
  const toast = useToast();
  const [shift, setShift] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openingFloat, setOpeningFloat] = useState("");
  const [busy, setBusy] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    cashShifts
      .current()
      .then((r) => {
        const s = r.data?.shift === null ? null : r.data;
        setShift(s);
        onShiftChange?.(s);
      })
      .catch(() => {
        setShift(null);
        onShiftChange?.(null);
      })
      .finally(() => setLoading(false));
  }, [onShiftChange]);

  useEffect(() => {
    load();
  }, [load]);

  async function openShift() {
    setBusy(true);
    try {
      await cashShifts.open({
        client_uuid: crypto.randomUUID(),
        opening_float: String(Number(openingFloat || 0)),
      });
      setOpeningFloat("");
      load();
    } catch (err) {
      toast.error(errorText(err, t, "till.saveError"));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <SkeletonCard />;
  }

  // ---- no open drawer: offer to open one -------------------------------
  if (!shift) {
    return (
      <Card className="p-6">
        <div className="mb-1 flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wide text-muted">
          <LockKeyhole size={15} /> {t("till.noOpenShift")}
        </div>
        <p className="mb-4 text-sm text-muted">{t("till.openHint")}</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-40">
            <Field label={t("till.openingFloat")}>
              <Input
                type="number"
                min="0"
                value={openingFloat}
                onChange={(e) => setOpeningFloat(e.target.value)}
                placeholder="0.00"
              />
            </Field>
          </div>
          <Button onClick={openShift} disabled={busy}>
            <Banknote size={16} />
            {busy ? t("common.saving") : t("till.openShift")}
          </Button>
        </div>
      </Card>
    );
  }

  // ---- open drawer -----------------------------------------------------
  const movements = shift.drawer_movements || [];
  return (
    <Card className="p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge tone="ok">{t("till.open")}</Badge>
          <span className="text-sm text-muted">
            {t("till.openedBy", { name: shift.opened_by_name })} ·{" "}
            {new Date(shift.opened_at).toLocaleString(language === "ar" ? "ar" : "en")}
          </span>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setMoveOpen(true)}>
            <Plus size={15} /> {t("till.recordMovement")}
          </Button>
          <Button onClick={() => setCloseOpen(true)}>
            <CheckCircle2 size={16} /> {t("till.closeShift")}
          </Button>
        </div>
      </div>

      <div className="divide-y divide-line">
        <Row label={t("till.openingFloat")} value={shift.opening_float} currency={currency} />
        <Row label={t("till.cashSales")} value={shift.cash_sales} currency={currency} />
        <Row
          label={t("till.drawerMovements")}
          value={shift.drawer_movements_total}
          currency={currency}
        />
        <Row
          label={t("till.expected")}
          value={shift.expected_cash}
          currency={currency}
          strong
        />
      </div>

      <p className="mt-3 text-xs text-muted">{t("till.cashOnlyNote")}</p>

      {movements.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs uppercase tracking-wide text-muted">
            {t("till.drawerMovements")}
          </div>
          <div className="divide-y divide-line rounded-card border border-line">
            {movements.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  <span className="text-ink">{t(`till.kind.${m.kind}`)}</span>
                  {m.reason && <span className="text-muted"> · {m.reason}</span>}
                </span>
                <span
                  className={`tabular ${
                    Number(m.amount) < 0 ? "text-danger" : "text-ok"
                  }`}
                >
                  {money(m.amount)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <MovementDrawer
        shift={shift}
        open={moveOpen}
        onClose={() => setMoveOpen(false)}
        onSaved={load}
      />
      <CloseDrawer
        shift={shift}
        open={closeOpen}
        onClose={() => setCloseOpen(false)}
        onClosed={load}
      />
    </Card>
  );
}
