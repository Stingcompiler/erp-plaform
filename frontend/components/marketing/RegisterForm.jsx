"use client";

// The public registration request, on its own page. `plan` preselects a
// hosted plan (from the pricing cards); `mode=standalone` turns the same form
// into an on-server quote request, which the platform inbox already knows
// how to handle (delivery_mode on RegistrationRequest).
//
// Since 2026-10-01 the form is checked for a duplicate of an open request
// first (409: a friendly panel, the reference goes to that request's own
// email), then a 6-digit code goes to the email typed here (202), and the
// request is created when that code verifies (backend:
// website/trial_requests.py). The form keeps its values while the code step
// is open, so "change email" goes back without retyping anything.

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Mail, MessageCircle, PackageSearch, PencilLine, UserRoundCheck } from "lucide-react";

import { useI18n } from "../../app/providers/I18nProvider";
import SuccessCheck from "@/components/ui/SuccessCheck";
import { registration } from "@/lib/api";
import { codeError, fieldErrors } from "@/lib/otpCode";
import { whatsappUrl } from "@/lib/phone";
import { offerRows } from "@/lib/planCatalog";
import CodeStep, { codeErrorText } from "./CodeStep";
import { formatPrice, usePublicPlans } from "./PlanCards";
import { useSiteContact } from "./SiteContact";

// Placeholders use the muted token (≥ 4.5:1 on the field in light and dark),
// never the browser's pale default; every field also has a visible label.
const inputClass = "w-full rounded-control border border-line bg-surface px-3 py-3 text-ink outline-none placeholder:text-muted focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/40";
const labelClass = "mb-1.5 block text-sm font-medium text-ink";

// Where hosted customers come from first; the backend stores the ISO code.
const COUNTRIES = ["SD", "SS", "EG", "SA", "AE", "QA", "KW", "BH", "OM", "LY", "TD", "ET", "ER", "JO", "YE"];

function countryName(code, language) {
  try {
    return new Intl.DisplayNames([language], { type: "region" }).of(code) || code;
  } catch {
    return code;
  }
}

// The server's message for this field sits right under it.
function Field({ id, label, error, children }) {
  return (
    <div>
      <label htmlFor={id} className={labelClass}>{label}</label>
      {children}
      {error && <p id={`${id}-error`} role="alert" className="mt-1 text-sm text-danger">{error}</p>}
    </div>
  );
}

function fieldProps(id, error) {
  return error ? { "aria-invalid": "true", "aria-describedby": `${id}-error` } : {};
}

// A request is already open for these details: no reference here (it went
// to the email on that request), a way to follow it and a person to ask.
function DuplicatePanel({ whatsapp, onEdit }) {
  const { t, href } = useI18n();
  const contact = useSiteContact();
  const waHref = whatsapp ? whatsappUrl(whatsapp) : contact.whatsappHref;
  return (
    <div role="status" className="enter-rise mx-auto max-w-lg rounded-card border border-line bg-paper p-6 text-center shadow-card sm:p-8">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-accent/10 text-accent">
        <UserRoundCheck size={24} aria-hidden="true" />
      </span>
      <h2 className="mt-4 font-display text-xl font-semibold">{t("register.duplicateTitle")}</h2>
      <p className="mt-2 text-sm text-muted">{t("register.duplicateBody")}</p>
      <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
        <Link href={`${href("/track")}#requests`} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control bg-accent px-5 py-2.5 font-medium text-white hover:bg-accent-strong">
          <PackageSearch size={17} aria-hidden="true" />{t("register.duplicateTrack")}
        </Link>
        {waHref && (
          <a href={waHref} target="_blank" rel="noreferrer noopener" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control border border-line bg-surface px-5 py-2.5 font-medium text-ink hover:border-accent">
            <MessageCircle size={17} aria-hidden="true" />{t("register.duplicateWhatsApp")}
          </a>
        )}
      </div>
      <button type="button" onClick={onEdit} className="mt-4 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-muted hover:text-ink hover:underline">
        <PencilLine size={15} aria-hidden="true" />{t("register.duplicateEdit")}
      </button>
    </div>
  );
}

// Three steps before the form, so nobody expects an instant workspace: the
// request is reviewed and activated the same day.
function Flow({ standalone }) {
  const { t } = useI18n();
  const steps = t(standalone ? "register.standaloneFlow" : "register.flow");
  if (!Array.isArray(steps)) return null;
  return (
    <section aria-labelledby="register-flow" className="mx-auto mb-8 max-w-5xl">
      <h2 id="register-flow" className="sr-only">{t("register.flowTitle")}</h2>
      <ol className="grid gap-3 sm:grid-cols-3">
        {steps.map(([title, body], index) => (
          <li key={title} className="flex items-start gap-3 rounded-card border border-line bg-surface p-4">
            <span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent font-display text-sm font-bold text-white">{index + 1}</span>
            <span>
              <span className="block font-semibold text-ink">{title}</span>
              <span className="mt-1 block text-sm text-muted">{body}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function RegisterForm() {
  const { t, language, href } = useI18n();
  const params = useSearchParams();
  const { plans: rows } = usePublicPlans();
  // One option per offer: a plan sold monthly and yearly is two, so the
  // version a pricing card links to is always in the list.
  const plans = useMemo(() => (rows ? offerRows(rows) : null), [rows]);
  const [mode, setMode] = useState(params.get("mode") === "standalone" ? "standalone" : "saas");
  const [planId, setPlanId] = useState(params.get("plan") || "");
  // { reference, email } once the request is accepted.
  const [sent, setSent] = useState(null);
  // { pendingId, emailMasked, resendAfter } while the emailed code is awaited.
  const [pending, setPending] = useState(null);
  // { whatsapp } when an open request already has these details.
  const [duplicate, setDuplicate] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState({});
  // What was typed, so going back from the code step loses nothing.
  const [draft, setDraft] = useState({});
  const requestId = useRef(null);
  const formRef = useRef(null);
  const contact = useSiteContact();
  // Each step (code, duplicate, done) replaces the form where it stood: bring
  // its top into view, below the sticky header, or a phone stays scrolled
  // at the old submit button.
  const stage = duplicate ? "duplicate" : pending ? `code-${pending.pendingId}` : sent ? "sent" : "form";
  const firstStage = useRef(true);
  useEffect(() => {
    if (firstStage.current) { firstStage.current = false; return; }
    if (stage === "form") return;
    document.getElementById("register-step")?.scrollIntoView({ block: "start" });
  }, [stage]);

  // A preselected plan that is not (or no longer) public falls back to the
  // first published one rather than an empty select.
  useEffect(() => {
    if (!plans || !plans.length) return;
    if (!plans.some((plan) => String(plan.id) === String(planId))) setPlanId(String(plans[0].id));
  }, [plans, planId]);

  const selected = useMemo(() => (plans || []).find((plan) => String(plan.id) === String(planId)), [plans, planId]);
  const standalone = mode === "standalone";

  function backToForm(focusEmail) {
    setPending(null); setDuplicate(null); setError("");
    if (focusEmail) {
      requestAnimationFrame(() => {
        const field = formRef.current?.elements?.namedItem("email");
        field?.focus(); field?.select?.();
      });
    }
  }

  function accepted(response, email) {
    setPending(null);
    setSent({ reference: response.data.public_reference || response.data.reference, email });
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(form.entries());
    setDraft(values);
    requestId.current ||= crypto.randomUUID();
    setBusy(true); setError(""); setErrors({});
    const email = String(values.email || "").trim();
    try {
      const response = await registration.create({
        request_uuid: requestId.current,
        company_name: values.company_name,
        contact_name: values.contact_name,
        email,
        phone: values.phone,
        country: String(values.country || "SD").toUpperCase(),
        timezone_name: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        estimated_users: Number(values.estimated_users) || undefined,
        estimated_branches: Number(values.estimated_branches) || undefined,
        delivery_mode: mode,
        plan_version: standalone ? undefined : Number(planId),
        message: values.message,
        privacy_version: "2026-09",
      });
      if (response.status === 202) {
        setPending({
          pendingId: response.data.pending_id,
          emailMasked: response.data.email_masked || email,
          resendAfter: response.data.resend_after || 60,
          email,
        });
      } else {
        // A replay of a request that already exists answers with it.
        accepted(response, email);
      }
    } catch (failure) {
      const parsed = codeError(failure);
      if (parsed.code === "duplicate_request") setDuplicate({ whatsapp: parsed.whatsapp });
      else if (parsed.code === "invalid") {
        const found = fieldErrors(parsed.fields);
        setErrors(found);
        setError(found.non_field_errors || t(Object.keys(found).length ? "otp.errors.invalid" : "registration.publicError"));
      } else {
        setError(codeErrorText(t, parsed));
      }
    } finally { setBusy(false); }
  }

  async function verifyCode(code) {
    const response = await registration.verifyCode({ pending_id: pending.pendingId, code }).catch((failure) => {
      if (codeError(failure).code === "duplicate_request") {
        setDuplicate({ whatsapp: failure.response.data.whatsapp || "" });
        setPending(null);
        return null;
      }
      throw failure;
    });
    if (response) accepted(response, pending.email);
  }

  async function resendCode() {
    const response = await registration.resendCode({ pending_id: pending.pendingId });
    return response.data.resend_after;
  }

  if (duplicate) {
    return (
      <div id="register-step" className="scroll-mt-24">
        <DuplicatePanel whatsapp={duplicate.whatsapp} onEdit={() => backToForm(false)} />
      </div>
    );
  }

  if (pending) {
    // The address is isolated (FSI…PDI) so it reads left-to-right in Arabic.
    return (
      <div id="register-step" className="mx-auto max-w-lg scroll-mt-24">
        <CodeStep
          key={pending.pendingId}
          title={t("register.codeTitle")}
          sentText={t("register.codeSentTo", { email: `\u2068${pending.emailMasked}\u2069` })}
          resendAfter={pending.resendAfter}
          onVerify={verifyCode}
          onResend={resendCode}
          onBack={() => backToForm(true)}
          backLabel={t("register.changeEmail")}
        />
      </div>
    );
  }

  if (sent) {
    return (
      <div id="register-step" className="mx-auto max-w-lg scroll-mt-24 rounded-card border border-line bg-paper p-8 text-center shadow-card">
        <SuccessCheck size={56} className="mx-auto block" label={t("register.sentTitle")} />
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
        <p className="tabular mt-2 rounded-control bg-surface px-3 py-2 font-mono text-lg font-bold tracking-wide" dir="ltr">{sent.reference}</p>
        <Link href={`${href("/track")}#requests`} className="mt-3 inline-block text-sm font-medium text-accent hover:underline">
          {t("track.thankYouTrack")}
        </Link>
        <br />
        <Link href={href("/")} className="mt-6 inline-block rounded-control border border-line bg-surface px-5 py-3 font-medium hover:border-accent">
          {t("register.backHome")}
        </Link>
      </div>
    );
  }

  return (
    <>
    <Flow standalone={standalone} />
    <div className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1fr_320px]">
      <form ref={formRef} onSubmit={onSubmit} className="rounded-card border border-line bg-paper p-6 shadow-card sm:p-8">
        {error && (
          <div role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">
            <p>{error}</p>
            {contact.whatsappHref && (
              <a href={contact.whatsappHref} target="_blank" rel="noreferrer noopener" className="mt-1 inline-flex min-h-11 items-center gap-2 font-medium underline">
                <MessageCircle size={15} aria-hidden="true" />{t("register.duplicateWhatsApp")}
              </a>
            )}
          </div>
        )}

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

        <p className="mb-4 text-sm text-muted">{t("register.requiredNote")}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="reg-company" label={t("registration.companyName")} error={errors.company_name}>
            <input id="reg-company" required name="company_name" maxLength={255} autoComplete="organization" defaultValue={draft.company_name} {...fieldProps("reg-company", errors.company_name)} className={inputClass} />
          </Field>
          <Field id="reg-contact" label={t("registration.contactName")} error={errors.contact_name}>
            <input id="reg-contact" required name="contact_name" maxLength={255} autoComplete="name" defaultValue={draft.contact_name} {...fieldProps("reg-contact", errors.contact_name)} className={inputClass} />
          </Field>
          <Field id="reg-email" label={t("registration.email")} error={errors.email}>
            <input id="reg-email" required type="email" name="email" maxLength={254} autoComplete="email" dir="ltr" defaultValue={draft.email} {...fieldProps("reg-email", errors.email)} className={`${inputClass} text-start`} />
          </Field>
          <Field id="reg-phone" label={t("registration.phone")} error={errors.phone}>
            <input id="reg-phone" required type="tel" inputMode="tel" name="phone" maxLength={64} autoComplete="tel" dir="ltr" placeholder="+249 9…" defaultValue={draft.phone} {...fieldProps("reg-phone", errors.phone)} className={`${inputClass} text-start`} />
          </Field>
          <Field id="reg-country" label={t("register.countryLabel")} error={errors.country}>
            <select id="reg-country" required name="country" defaultValue={draft.country || "SD"} autoComplete="country" className={inputClass}>
              {COUNTRIES.map((code) => <option key={code} value={code}>{countryName(code, language)}</option>)}
            </select>
          </Field>
          {!standalone && (
            <Field id="reg-plan" label={t("register.planLabel")} error={errors.plan_version}>
              <select id="reg-plan" required value={planId} onChange={(event) => setPlanId(event.target.value)} className={inputClass}>
                <option value="" disabled>{t("registration.plan")}</option>
                {(plans || []).map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.display?.name?.[language] || plan.plan_name} · {formatPrice(plan.price, plan.currency, language)} · {t(plan.billing_cycle === "yearly" ? "pricing.perYearLine" : "pricing.perMonthLine")}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
        {/* Not needed to open the request (the serializer marks them
            optional), so they wait behind a disclosure. */}
        <details className="mt-5 rounded-control border border-line bg-surface p-4">
          <summary className="cursor-pointer text-sm font-medium text-ink">{t("register.moreDetails")}</summary>
          <p className="mt-2 text-xs text-muted">{t("register.moreDetailsHint")}</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field id="reg-users" label={t("registration.estimatedUsers")}>
              <input id="reg-users" type="number" min="1" name="estimated_users" defaultValue={draft.estimated_users} className={inputClass} />
            </Field>
            <Field id="reg-branches" label={t("registration.estimatedBranches")}>
              <input id="reg-branches" type="number" min="1" name="estimated_branches" defaultValue={draft.estimated_branches} className={inputClass} />
            </Field>
          </div>
          <div className="mt-4">
            <Field id="reg-message" label={t(standalone ? "register.serverNote" : "registration.message")}>
              <textarea id="reg-message" rows={3} name="message" maxLength={4000} defaultValue={draft.message} className={inputClass} />
            </Field>
          </div>
        </details>
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
    </>
  );
}
