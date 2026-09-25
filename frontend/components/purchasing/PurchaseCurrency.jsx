"use client";

import { useEffect, useState } from "react";

import { purchasing } from "@/lib/api";
import { formatAmount, round2 } from "@/lib/money";
import { useI18n } from "../../app/providers/I18nProvider";
import { Field, Input, Select } from "@/components/ui/kit";

// Supplier currency on purchase documents. The API kept currency + rate on
// orders, receipts and bills (the ledger converts at that rate), but no
// screen could set them, so importing in USD was API-only.

const money = (v) =>
  formatAmount(v);

/** The company currency, its reference currency and today's rate. Empty
 *  until loaded (or offline): the screens then just use the company currency. */
export function usePurchaseCurrencies() {
  const [info, setInfo] = useState({ currency: "", reference_currency: "", exchange_rate: null });
  useEffect(() => {
    let live = true;
    purchasing.currencies()
      .then((r) => { if (live) setInfo(r.data || {}); })
      .catch(() => {});
    return () => { live = false; };
  }, []);
  return info;
}

export const EMPTY_FX = { currency: "", rate: "" };

/** The currency a form is in: the picked one, else the company's. */
export const fxCurrency = (fx, info) => fx.currency || info.currency || "";

export const isForeign = (currency, info) =>
  Boolean(currency && info.currency && currency !== info.currency);

/** The rate the form converts at: 1 in the company currency. */
export function fxRate(fx, info) {
  return isForeign(fxCurrency(fx, info), info) ? Number(fx.rate) || 0 : 1;
}

/** An error message when a foreign currency has no usable rate, else "". */
export function fxProblem(fx, info, t) {
  const currency = fxCurrency(fx, info);
  if (!isForeign(currency, info)) return "";
  return Number(fx.rate) > 0
    ? ""
    : t("purchasing.fx.rateRequired", { currency, base: info.currency });
}

/** The currency fields to send; nothing when the company currency is unknown
 *  (the server then keeps the document in the company currency). */
export function fxPayload(fx, info) {
  const currency = fxCurrency(fx, info);
  if (!currency) return {};
  if (!isForeign(currency, info)) return { currency };
  return { currency, exchange_rate: Number(fx.rate).toFixed(6) };
}

/** A catalogue cost (company currency) expressed in the form's currency. */
export function toDocumentCost(cost, fx, info) {
  const rate = fxRate(fx, info);
  const value = Number(cost ?? 0);
  return String(rate > 0 && rate !== 1 ? round2(value / rate) : value);
}

/** "1,250.00 USD" and, for a foreign amount, the company-currency figure. */
export function AmountWithBase({ amount, currency, rate, info, className = "" }) {
  const { t } = useI18n();
  const foreign = isForeign(currency, info) && Number(rate) > 0;
  return (
    <span className={`inline-flex flex-col items-end ${className}`}>
      <span className="tabular">
        {money(amount)}
        {currency && <span className="ms-1 text-xs font-normal text-muted">{currency}</span>}
      </span>
      {foreign && (
        <span className="tabular text-xs font-normal text-muted">
          {t("purchasing.fx.inBase", {
            amount: money(round2(Number(amount || 0) * Number(rate))),
            base: info.currency,
          })}
        </span>
      )}
    </span>
  );
}

/**
 * Currency selector (company currency, or its reference currency) and the
 * rate, prefilled with today's rate. `locked` shows a document's own
 * currency read-only — a receipt against an order, a bill for a receipt.
 */
export function CurrencyFields({ info, fx, onChange, locked = null }) {
  const { t } = useI18n();
  if (locked) {
    const foreign = isForeign(locked.currency, info);
    return (
      <p className="rounded-card border border-line bg-paper px-3 py-2 text-sm text-muted">
        {t(locked.source === "receipt" ? "purchasing.fx.fromReceipt" : "purchasing.fx.fromOrder", {
          currency: locked.currency || info.currency || "—",
        })}
        {foreign && (
          <span className="tabular ms-1" dir="ltr">
            ({t("purchasing.fx.rateShort", { rate: Number(locked.rate), base: info.currency, currency: locked.currency })})
          </span>
        )}
      </p>
    );
  }
  const options = [info.currency, info.reference_currency].filter(
    (c, i, all) => c && all.indexOf(c) === i
  );
  if (options.length < 2) return null;
  const currency = fxCurrency(fx, info);
  const foreign = isForeign(currency, info);
  const pick = (value) => {
    const next = { ...fx, currency: value };
    if (isForeign(value, info) && !fx.rate && info.exchange_rate) {
      next.rate = String(Number(info.exchange_rate));
    }
    onChange(next);
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label={t("purchasing.fx.currency")}>
        <Select value={currency} onChange={(e) => pick(e.target.value)}>
          {options.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </Field>
      {foreign && (
        <Field
          label={t("purchasing.fx.rate")}
          hint={t("purchasing.fx.rateHint", { base: info.currency, currency })}
        >
          <Input
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={fx.rate}
            onChange={(e) => onChange({ ...fx, rate: e.target.value })}
          />
        </Field>
      )}
    </div>
  );
}
