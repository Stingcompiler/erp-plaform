"use client";

// The money rule of lib/money.js bound to the signed-in company's currency
// and the UI language:
//
//   const { money, amount, label } = useMoney();
//   money(total)            → "1,234.50 ج.س"   (a lone figure: totals, KPIs)
//   amount(line.total)      → "1,234.50"       (table cells under a header)
//   money(v, { empty: "—" }) → "—" when the figure did not load
//   money(v, { currency: "USD" }) for a document in another currency

import { useCallback, useMemo } from "react";

import { useAuth } from "../app/providers/AuthProvider";
import { useI18n } from "../app/providers/I18nProvider";
import { currencyLabel, formatAmount, formatMoney } from "./money";

export function useMoney() {
  const { user } = useAuth();
  const { language } = useI18n();
  const currency = user?.currency || "SDG";
  const money = useCallback(
    (value, options = {}) => formatMoney(value, { currency, language, ...options }),
    [currency, language]
  );
  const amount = useCallback((value, options) => formatAmount(value, options), []);
  const labelFor = useCallback((code) => currencyLabel(code, language), [language]);
  return useMemo(
    () => ({ money, amount, currency, label: currencyLabel(currency, language), labelFor }),
    [money, amount, currency, language, labelFor]
  );
}
