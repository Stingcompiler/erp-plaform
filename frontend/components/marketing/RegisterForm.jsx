"use client";

// The public registration request, on its own page. `plan` preselects a
// hosted plan (from the pricing cards); `mode=standalone` turns the same form
// into an on-server quote request, which the platform inbox already knows
// how to handle (delivery_mode on RegistrationRequest).

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Mail } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import { registration } from "@/lib/api";
import { formatPrice, usePublicPlans } from "./PlanCards";

const inputClass = "w-full rounded-control border border-line bg-surface px-3 py-3 outline-none focus:border-accent";

export default function RegisterForm() {
  const { t, language, href } = useI18n();
  const params = useSearchParams();
  const { plans } = usePublicPlans();
  const [mode, setMode] = useState(params.get("mode") === "standalone" ? "standalone" : "saas");
  const [planId, setPlanId] = useState(params.get("plan") || "");
  // { reference, email } once the request is accepted.
  const [sent, setSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(null);

  // A preselected plan that is not (or no longer) public falls back to the
  // first published one rather than an empty select.
  useEffect(() => {
    if (!plans || !plans.length) return;
    if (!plans.some((plan) => String(plan.id) === String(planId))) setPlanId(String(plans[0].id));
  }, [plans, planId]);

  const selected = useMemo(() => (plans || []).find((plan) => String(plan.id) === String(planId)), [plans, planId]);
  const standalone = mode === "standalone";

  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    requestId.current ||= crypto.randomUUID();
    setBusy(true); setError("");
    try {
      const response = await registration.create({
        request_uuid: requestId.current,
        company_name: form.get("company_name"),
        contact_name: form.get("contact_name"),
        email: form.get("email"),
        phone: form.get("phone"),
        country: String(form.get("country") || "").toUpperCase(),
        timezone_name: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        estimated_users: Number(form.get("estimated_users")) || undefined,
        estimated_branches: Number(form.get("estimated_branches")) || undefined,
        delivery_mode: mode,
        plan_version: standalone ? undefined : Number(planId),
        message: form.get("message"),
        privacy_version: "2026-09",
      });
      setSent({ reference: response.data.reference, email: String(form.get("email") || "").trim() });
    } catch {
      setError(t("registration.publicError"));
    } finally { setBusy(false); }
  }

  if (sent) {
    return (
      <div className="mx-auto max-w-lg rounded-card border border-line bg-paper p-8 text-center shadow-card">
        <CheckCircle2 className="mx-auto text-ok" size={40} />
        <h2 className="mt-4 font-display text-xl font-semibold">{t("register.sentTitle")}</h2>
        <div role="status" className="mt-4 flex items-start gap-3 rounded-control border border-accent/30 bg-accent/5 p-4 text-start">
          <Mail size={20} className="mt-0.5 shrink-0 text-accent" />
          <div>
            <p className="font-medium text-ink">{t("register.checkEmailTitle")}</p>
            <p className="mt-1 text-sm text-muted">
              {t("register.checkEmailSentTo")}{" "}
              <bdi dir="ltr" className="whitespace-nowrap font-medium text-ink">{sent.email}</bdi>
            </p>
            <p className="mt-1 text-sm text-muted">{t("register.checkEmailNext")}</p>
          </div>
        </div>
        <p className="mt-4 text-sm text-muted">{t("register.sentBody")}</p>
        <p className="tabular mt-2 rounded-control bg-surface px-3 py-2 font-mono text-sm" dir="ltr">{sent.reference}</p>
        <Link href={href("/")} className="mt-6 inline-block rounded-control border border-line bg-surface px-5 py-3 font-medium hover:border-accent">
          {t("register.backHome")}
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1fr_320px]">
      <form onSubmit={onSubmit} className="rounded-card border border-line bg-paper p-6 shadow-card sm:p-8">
        {error && <p role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</p>}

        <fieldset className="mb-6">
          <legend className="mb-2 text-sm font-medium">{t("register.deliveryLabel")}</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {[["saas", "register.hosted", "register.hostedHint"], ["standalone", "register.standalone", "register.standaloneHint"]].map(([value, key, hint]) => (
              <label
                key={value}
                className={`flex cursor-pointer items-start gap-2 rounded-control border px-3 py-3 text-sm ${
                  mode === value ? "border-accent bg-accent/5" : "border-line bg-surface"
                }`}
              >
                <input type="radio" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} className="mt-1 accent-accent" />
                <span>
                  <span className="font-medium">{t(key)}</span>
                  <span className="mt-1 block text-xs leading-relaxed text-muted">{t(hint)}</span>
                </span>
              </label>
            ))}
          </div>
          <Link href={href("/register/hosting")} className="mt-2 inline-block text-sm text-accent hover:underline">
            {t("register.compareOptions")}
          </Link>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <input required name="company_name" maxLength={255} placeholder={t("registration.companyName")} className={inputClass} />
          <input required name="contact_name" maxLength={255} placeholder={t("registration.contactName")} className={inputClass} />
          <input required type="email" name="email" maxLength={254} placeholder={t("registration.email")} className={inputClass} />
          <input required name="phone" maxLength={64} placeholder={t("registration.phone")} className={inputClass} />
          <input required name="country" minLength={2} maxLength={2} placeholder={t("registration.country")} className={`${inputClass} uppercase`} />
          {!standalone && (
            <select required value={planId} onChange={(event) => setPlanId(event.target.value)} className={inputClass}>
              <option value="" disabled>{t("registration.plan")}</option>
              {(plans || []).map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.display?.name?.[language] || plan.plan_name} · {formatPrice(plan.price, plan.currency, language)}
                </option>
              ))}
            </select>
          )}
          <input type="number" min="1" name="estimated_users" placeholder={t("registration.estimatedUsers")} className={inputClass} />
          <input type="number" min="1" name="estimated_branches" placeholder={t("registration.estimatedBranches")} className={inputClass} />
        </div>
        <textarea rows={3} name="message" maxLength={4000} placeholder={t(standalone ? "register.serverNote" : "registration.message")} className={`${inputClass} mt-4`} />
        <p className="mt-3 text-xs text-muted">{t("registration.privacy")}</p>
        <button
          type="submit"
          disabled={busy || (!standalone && !planId)}
          className="mt-4 w-full rounded-control bg-accent py-3 font-medium text-white hover:bg-accent-strong disabled:opacity-50"
        >
          {busy ? t("registration.sending") : t(standalone ? "pricing.requestQuote" : "registration.submit")}
        </button>
      </form>

      <aside className="h-fit rounded-card border border-line bg-surface p-6">
        {standalone ? (
          <>
            <h3 className="font-display text-lg font-semibold">{t("pricing.standaloneName")}</h3>
            <p className="mt-2 text-sm text-muted">{t("pricing.standaloneTagline")}</p>
            <ul className="mt-4 space-y-2 text-sm">
              {(t("pricing.standaloneFeatures") || []).map((line) => <li key={line}>· {line}</li>)}
            </ul>
          </>
        ) : selected ? (
          <>
            <p className="text-xs uppercase tracking-wide text-muted">{t("register.selectedPlan")}</p>
            <h3 className="mt-1 font-display text-lg font-semibold">{selected.display?.name?.[language] || selected.plan_name}</h3>
            <p className="mt-2 font-display text-2xl font-bold">{formatPrice(selected.price, selected.currency, language)}
              <span className="ms-1 text-sm font-normal text-muted">{selected.billing_cycle === "yearly" ? t("pricing.perYear") : t("pricing.perMonth")}</span>
            </p>
            {selected.trial_days > 0 && <p className="mt-2 text-sm text-accent">{t("pricing.trialBadge", { days: selected.trial_days })}</p>}
            <p className="mt-4 text-sm text-muted">{t("registration.trialLength", { days: selected.trial_days })}</p>
            <Link href={href("/pricing")} className="mt-4 inline-block text-sm text-accent hover:underline">{t("register.changePlan")}</Link>
          </>
        ) : (
          <p className="text-sm text-muted">{t("pricing.quoteOnly")}</p>
        )}
      </aside>
    </div>
  );
}
