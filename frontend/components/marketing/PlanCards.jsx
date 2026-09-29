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
import { deckStyle, PlanDeckSkeleton } from "./pricing/PlanDeck";
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

// The deck's shape at every width (carousel with pills, or the grid) and
// the on-server band under it, so the page does not move when the plans
// arrive. Three plans is the usual catalogue.
export function PlansSkeleton({ bleed = true, compact = false, selfHosted = DEFAULT_DISPLAY.show_self_hosted }) {
  return (
    <div aria-busy="true" className="plan-showcase" style={deckStyle(3)}>
      <PlanDeckSkeleton count={3} bleed={bleed} compact={compact} />
      {selfHosted && <div className={`plan-band plan-band--skeleton mt-8 animate-pulse rounded-card bg-ink/90 ${compact ? "plan-band--skeleton-compact" : ""}`} />}
    </div>
  );
}

// rows: /api/public/plans/ (null while loading). display: a resolveDisplay()
// object. persistCycle: remember the visitor's monthly/yearly choice (the
// admin preview does not). bleed: on a phone/tablet the carousel runs to
// the screen edges (the page's px-4 / sm:px-6 gutter); off inside a box.
export function PlanShowcase({ rows, error = false, display = DEFAULT_DISPLAY, compact = false, persistCycle = true, bleed = true }) {
  const { t } = useI18n();
  const cycles = useMemo(() => billingCycles(rows), [rows]);
  const [chosen, setChosen] = useState(() => (persistCycle && typeof window !== "undefined" ? readStoredCycle() : null));
  const cycle = resolveCycle(cycles, chosen, display.default_cycle);
  const plans = usePlanCatalog(rows, cycle);
  const onSwitchCycle = useCallback((next) => {
    setChosen(next);
    if (persistCycle) storeCycle(next);
  }, [persistCycle]);

  const selfHosted = display.show_self_hosted;
  if (plans === null) return <PlansSkeleton bleed={bleed} compact={compact} selfHosted={selfHosted} />;
  const Layout = TEMPLATES[display.template] || TEMPLATES.classic;
  return (
    <div className={Layout.isDeck ? "plan-showcase" : undefined} style={Layout.isDeck ? deckStyle(plans.length) : undefined}>
      {error && <p className="mb-4 text-center text-sm text-danger">{t("pricing.loadError")}</p>}
      {!error && plans.length === 0 && <p className="mb-4 text-center text-muted">{t("pricing.quoteOnly")}</p>}
      <CycleToggle value={cycle} options={cycles} onChange={onSwitchCycle} />
      {plans.length > 0 && <Layout plans={plans} compact={compact} onSwitchCycle={onSwitchCycle} bleed={bleed} />}
      {selfHosted && <StandaloneBand compact={compact} />}
      {display.show_compare && !Layout.isTable && <PlanCompareTable plans={plans} onSwitchCycle={onSwitchCycle} />}
    </div>
  );
}

// The pricing page: the saved layout, the plans, one skeleton until both.
export function PricingPlans({ display, ready }) {
  const { plans: rows, error } = usePublicPlans();
  if (!ready || rows === null) return <PlansSkeleton selfHosted={display.show_self_hosted} />;
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
