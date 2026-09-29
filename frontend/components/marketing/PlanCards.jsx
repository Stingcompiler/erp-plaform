"use client";

// Public plan cards, driven by /api/public/plans/. The same showcase serves
// the landing preview (`compact`, always classic), the pricing page (the
// layout the platform team picked, /api/public/plans/display/) and the live
// preview on /platform-plans.
//
// The API rows go through lib/planCatalog.js once (order, one badge, real
// limits/modules first, feature lines deduped, no internal codes, the
// billing cycle actually on offer); a template is only a renderer over
// those normalized plans — see pricing/templates.jsx.

import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "../../app/providers/I18nProvider";
import { publicSite, registration } from "@/lib/api";
import {
  billingCycles, DEFAULT_DISPLAY, formatPlanAmount, normalizePlans, resolveCycle, resolveDisplay,
} from "@/lib/planCatalog";
import { moduleLabel } from "@/lib/planModules";
import PlanCompareTable from "./pricing/PlanCompareTable";
import { CycleToggle, StandaloneBand } from "./pricing/parts";
import { TEMPLATES } from "./pricing/templates";

export { TEMPLATES };

// One amount and one currency label ("500,000 ج.س"), as on the cards.
export function formatPrice(amount, currency, language) {
  return formatPlanAmount(amount, currency, language);
}

export function usePublicPlans() {
  const [plans, setPlans] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    registration
      .publicPlans()
      .then((response) => { if (!cancelled) setPlans(response.data || []); })
      .catch(() => { if (!cancelled) { setPlans([]); setError(true); } });
    return () => { cancelled = true; };
  }, []);
  return { plans, error };
}

// The API rows as the templates read them, in the UI language, on `cycle`
// (null: no monthly/yearly switch).
export function usePlanCatalog(rows, cycle = null) {
  const { t, language } = useI18n();
  return useMemo(
    () => (rows ? normalizePlans(rows, language, {
      module: (code) => moduleLabel(code, t),
      limit: (key) => t(`pricing.limitLabels.${key}`),
    }, { cycle }) : null),
    [rows, language, t, cycle],
  );
}

// ---- The layout the platform team chose -----------------------------------

const DISPLAY_CACHE = "vezano.pricingDisplay.v1";
// Past this the page stops waiting and renders the default (classic), so a
// slow or failing settings call never keeps the plans hidden.
const DISPLAY_WAIT_MS = 1500;

function readDisplayCache() {
  try {
    const raw = sessionStorage.getItem(DISPLAY_CACHE);
    return raw ? resolveDisplay(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

// { display, ready }. The static export knows only the default; the page
// shows its skeleton until the saved layout (or the timeout) arrives, so
// the cards appear once, already in the right layout, instead of jumping
// from classic to another template.
export function usePricingDisplay() {
  const [state, setState] = useState({ display: DEFAULT_DISPLAY, ready: false });
  useEffect(() => {
    let settled = false;
    const settle = (display) => {
      if (settled) return;
      settled = true;
      setState({ display, ready: true });
    };
    const cached = readDisplayCache();
    if (cached) settle(cached);
    const timer = setTimeout(() => settle(DEFAULT_DISPLAY), DISPLAY_WAIT_MS);
    publicSite.pricingDisplay()
      .then((response) => {
        const display = resolveDisplay(response.data);
        try { sessionStorage.setItem(DISPLAY_CACHE, JSON.stringify(display)); } catch { /* private mode */ }
        settle(display);
      })
      .catch(() => settle(DEFAULT_DISPLAY));
    return () => { settled = true; clearTimeout(timer); };
  }, []);
  return state;
}

// ---- The visitor's billing cycle ------------------------------------------

const CYCLE_KEY = "vezano.pricingCycle.v1";

function readStoredCycle() {
  try { return localStorage.getItem(CYCLE_KEY); } catch { return null; }
}

function storeCycle(cycle) {
  try { localStorage.setItem(CYCLE_KEY, cycle); } catch { /* private mode */ }
}

// ---- The showcase -----------------------------------------------------------

export function PlansSkeleton() {
  return (
    <div className="grid gap-5 md:grid-cols-3" aria-busy="true">
      {[0, 1, 2].map((i) => <div key={i} className="h-96 animate-pulse rounded-card border border-line bg-paper" />)}
    </div>
  );
}

// rows: /api/public/plans/ (null while loading). display: a resolveDisplay()
// object. persistCycle: remember the visitor's monthly/yearly choice (the
// admin preview does not).
export function PlanShowcase({ rows, error = false, display = DEFAULT_DISPLAY, compact = false, persistCycle = true }) {
  const { t } = useI18n();
  const cycles = useMemo(() => billingCycles(rows), [rows]);
  const [chosen, setChosen] = useState(() => (persistCycle && typeof window !== "undefined" ? readStoredCycle() : null));
  const cycle = resolveCycle(cycles, chosen, display.default_cycle);
  const plans = usePlanCatalog(rows, cycle);
  const onSwitchCycle = useCallback((next) => {
    setChosen(next);
    if (persistCycle) storeCycle(next);
  }, [persistCycle]);

  if (plans === null) return <PlansSkeleton />;
  const Layout = TEMPLATES[display.template] || TEMPLATES.classic;
  const selfHosted = display.show_self_hosted;
  return (
    <div>
      {error && <p className="mb-4 text-center text-sm text-danger">{t("pricing.loadError")}</p>}
      {!error && plans.length === 0 && <p className="mb-4 text-center text-muted">{t("pricing.quoteOnly")}</p>}
      <CycleToggle value={cycle} options={cycles} onChange={onSwitchCycle} />
      {(plans.length > 0 || Layout.ownsSelfHosted) && <Layout plans={plans} compact={compact} onSwitchCycle={onSwitchCycle} selfHosted={selfHosted} />}
      {selfHosted && !Layout.ownsSelfHosted && <StandaloneBand />}
      {display.show_compare && !Layout.isTable && <PlanCompareTable plans={plans} onSwitchCycle={onSwitchCycle} />}
    </div>
  );
}

// The pricing page: the saved layout, the plans, one skeleton until both.
export function PricingPlans({ display, ready }) {
  const { plans: rows, error } = usePublicPlans();
  if (!ready || rows === null) return <PlansSkeleton />;
  return <PlanShowcase rows={rows} error={error} display={display} />;
}

// The landing preview (and any page that wants the plain cards).
export default function PlanCards({ compact = false, showCompare = false, template = "classic" }) {
  const { plans: rows, error } = usePublicPlans();
  const display = useMemo(
    () => resolveDisplay({ ...DEFAULT_DISPLAY, template, show_compare: showCompare }),
    [template, showCompare],
  );
  return <PlanShowcase rows={rows} error={error} display={display} compact={compact} />;
}
