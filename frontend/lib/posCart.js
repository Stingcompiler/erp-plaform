// Pure helpers behind the till (components/sales/PosTerminal.jsx), kept out
// of the component so they can be tested without a browser.
import { round2 } from "./money.js";

export const newTender = (method = "cash") => ({
  id: Math.random().toString(36).slice(2, 10),
  method, amount: "", bankAccount: "", sender: "", reference: "",
});

// How the money handed over settles `due`.
//
// A sale can be paid in several parts — cash and a Bankak transfer is the
// everyday case. A blank amount means "the rest": the first blank row takes
// whatever the typed rows leave (a single blank row is an exact payment, as
// before). Transfers are recorded as typed and may never exceed what is due:
// there is no change to hand back on a transfer, so a surplus is a mistake
// to fix, not something to trim silently. Cash may exceed it — the surplus
// is change, and only what is owed is recorded.
export function tenderPlan(tenders, due) {
  const owedTotal = round2(Math.max(0, Number(due) || 0));
  const rows = tenders.map((t) => ({
    ...t, value: t.amount === "" ? null : round2(Math.max(0, Number(t.amount) || 0)),
  }));
  const typed = rows.reduce((s, r) => s + (r.value ?? 0), 0);
  let blankTaken = false;
  for (const r of rows) {
    if (r.value !== null) continue;
    r.value = blankTaken ? 0 : round2(Math.max(0, owedTotal - typed));
    blankTaken = true;
  }
  const sum = (list) => round2(list.reduce((s, r) => s + r.value, 0));
  const nonCash = sum(rows.filter((r) => r.method !== "cash"));
  const cash = sum(rows.filter((r) => r.method === "cash"));
  const overTransfer = nonCash > owedTotal;
  const cashApplied = overTransfer ? 0 : round2(Math.min(cash, owedTotal - nonCash));
  const paid = round2(Math.min(nonCash, owedTotal) + cashApplied);
  return {
    rows, cash, nonCash, cashApplied, paid, overTransfer,
    change: round2(cash - cashApplied),
    owed: round2(Math.max(0, owedTotal - paid)),
  };
}

// The payments a checkout sends for a plan: every transfer as typed, and
// the cash that stays in the drawer as one payment.
export function paymentsFor(plan) {
  const out = plan.rows
    .filter((r) => r.method !== "cash" && r.value > 0)
    .map((r) => ({
      method: r.method, amount: String(r.value),
      ...(r.method === "bank_transfer" ? {
        company_bank_account: Number(r.bankAccount),
        sender_bank_name: String(r.sender || "").trim(),
        transfer_reference: String(r.reference || "").trim(),
      } : {}),
    }));
  if (plan.cashApplied > 0) out.unshift({ method: "cash", amount: String(plan.cashApplied) });
  return out;
}

// Discount above the company's limit for a till user without approval.
// `limit` null/undefined/"" = no limit. A cent of slack, as on the server:
// the ticket discount is spread across lines in cents.
// With `listTotal` (list price x quantity) a price typed under the list
// counts too, as on the server (POSCheckoutSerializer._enforce_price_rules):
// what is measured is how far the net line (after its own and the ticket
// discount) sits below the list, so a typed-down price and a discount on
// top of it add up, and a marked-up price leaves room for a discount.
export function overDiscountLimit(gross, discount, limit, listTotal = 0) {
  if (limit === null || limit === undefined || limit === "") return false;
  if (!(gross > 0)) return false;
  const off = Math.max(0, Number(discount) || 0);
  const list = round2(Number(listTotal) || 0);
  const base = list > 0 ? list : gross;
  const given = list > 0 ? round2(list - (gross - off)) : off;
  if (!(given > 0)) return false;
  return given > round2((base * Number(limit)) / 100) + 0.01;
}

// The open cart survives a reload or a closed tab: saved per signed-in
// company, user and branch (the key comes from lib/localIdentity).
export const draftStore = {
  load(key) {
    if (!key) return null;
    try { return JSON.parse(window.localStorage.getItem(key) || "null"); } catch { return null; }
  },
  save(key, draft) {
    if (!key) return;
    try { window.localStorage.setItem(key, JSON.stringify(draft)); } catch { /* storage full or blocked */ }
  },
  clear(key) {
    if (!key) return;
    try { window.localStorage.removeItem(key); } catch { /* blocked */ }
  },
};
