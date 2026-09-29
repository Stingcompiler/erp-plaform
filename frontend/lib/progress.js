// The real numbers behind the progress rings (components/ui/ProgressRing).
// A ring is only drawn where both ends of it are known; each helper here
// answers null when they are not, and the screen then shows no ring.

const DAY = 86400000;

function parse(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function monthsBefore(date, months) {
  const d = new Date(date.getTime());
  d.setUTCMonth(d.getUTCMonth() - months);
  return d;
}

// The window the company is in now and how much of it is left, from a
// subscription record (subscriptions.serializers.SubscriptionSerializer):
//
//   trialing – starts_at → trial_ends_at
//   active   – the current billing period: period_ends_at minus one cycle
//              (a month, or a year on a yearly plan) → period_ends_at
//   grace    – period_ends_at → grace_ends_at
//
// Anything else (legacy, suspended, cancelled, read-only) has no window.
// { kind, daysLeft, totalDays, endsAt } or null.
export function subscriptionWindow(record, now = new Date()) {
  if (!record) return null;
  let start = null;
  let end = null;
  let kind = record.status;
  if (kind === "trialing") {
    start = parse(record.starts_at);
    end = parse(record.trial_ends_at);
  } else if (kind === "active") {
    end = parse(record.period_ends_at);
    if (end) start = monthsBefore(end, record.plan?.billing_cycle === "yearly" ? 12 : 1);
    const began = parse(record.starts_at);
    if (start && began && began > start) start = began;
  } else if (kind === "grace") {
    start = parse(record.period_ends_at);
    end = parse(record.grace_ends_at);
  } else {
    return null;
  }
  if (!start || !end || end <= start) return null;
  const totalDays = Math.max(1, Math.round((end - start) / DAY));
  const daysLeft = Math.min(totalDays, Math.max(0, Math.ceil((end - now) / DAY)));
  return { kind, daysLeft, totalDays, endsAt: end.toISOString() };
}

// Upload progress of the offline queue. `peak` is the most operations the
// queue held since it was last empty; `waiting` how many it holds now. The
// ones that left it were sent (the server accepted or answered them).
// { sent, total, fraction } or null when nothing has been queued.
export function uploadProgress(peak, waiting) {
  const total = Math.max(Number(peak) || 0, Number(waiting) || 0);
  if (total <= 0) return null;
  const sent = total - Math.max(0, Number(waiting) || 0);
  return { sent, total, fraction: sent / total };
}

// A budget's variance rows (finance.budgetVariance) summed per kind:
// { expense: { planned, actual }, revenue: { planned, actual } }, a kind
// with nothing planned left out.
export function budgetTotals(rows) {
  const totals = {};
  for (const row of rows || []) {
    const kind = row.kind === "revenue" ? "revenue" : "expense";
    totals[kind] ||= { planned: 0, actual: 0 };
    totals[kind].planned += Number(row.planned) || 0;
    totals[kind].actual += Number(row.actual) || 0;
  }
  for (const kind of Object.keys(totals)) {
    if (!(totals[kind].planned > 0)) delete totals[kind];
    else {
      totals[kind].planned = Math.round(totals[kind].planned * 100) / 100;
      totals[kind].actual = Math.round(totals[kind].actual * 100) / 100;
    }
  }
  return totals;
}
