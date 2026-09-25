// Stored codes (statuses, payment methods, dispositions…) as words a person
// reads. The API sends the machine value — `partially_paid`, `bank_transfer`
// — and a screen that printed it as-is showed English snake_case inside the
// Arabic UI. Every label here goes through the catalog; a code the catalog
// does not know yet reads as plain words ("Partially paid"), never as the
// raw code.

// "partially_paid" → "Partially paid"
export function humanize(value) {
  const text = String(value ?? "").replace(/[_-]+/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1).toLowerCase() : "";
}

// t(`${prefix}.${value}`), or the humanized code when the key is missing
// (the catalog returns the key itself for an unknown one).
export function enumLabel(t, prefix, value) {
  if (value === null || value === undefined || value === "") return "—";
  const key = `${prefix}.${value}`;
  const text = t(key);
  return text && text !== key ? text : humanize(value);
}

export const invoiceStatusLabel = (t, status) => enumLabel(t, "labels.invoiceStatus", status);

export const subscriptionStateLabel = (t, state) =>
  enumLabel(t, "platformCompanies.status", state);

export const billingCycleLabel = (t, cycle) => enumLabel(t, "platformPlans", cycle);

// The activity log's action codes (create, update, login…) — the same words
// the audit log page uses.
export function activityActionLabel(t, action) {
  if (!action) return "—";
  const key = `logs.action${action.charAt(0).toUpperCase()}${action.slice(1)}`;
  const text = t(key);
  return text !== key ? text : humanize(action);
}

// A payment method as the API sends it: the code ("bank_transfer") or, on
// printed documents, the model's English display ("Bank Transfer").
export function paymentMethodLabel(t, method) {
  if (!method) return "";
  const code = String(method).trim().toLowerCase().replace(/\s+/g, "_");
  const known = { store_credit: "credit" }[code] || code;
  return enumLabel(t, "labels.paymentMethod", known);
}
