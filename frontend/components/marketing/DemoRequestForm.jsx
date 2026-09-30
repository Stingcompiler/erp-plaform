"use client";

// The walkthrough request on the home page (POST /api/public/demo-requests/,
// website.views.DemoRequestView). What the visitor sees when something is
// wrong follows lib/demoRequestForm.js:
//
//   - the form checks itself (noValidate: no browser bubbles, which speak
//     the browser's language, not the page's) and puts each message under
//     its field, linked with aria-describedby, the field aria-invalid, and
//     focus on the first one;
//   - a 400 from the server is mapped to the same field messages;
//   - only a 5xx or no answer at all offers "Try again", which resends with
//     the same request UUID, so a retry never files the request twice.
import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { useI18n } from "@/app/providers/I18nProvider";
import { ContactChannels } from "@/components/marketing/SiteContact";
import { demoRequests } from "@/lib/api";
import { LIMITS, classifyDemoError, firstInvalidField, validateDemoRequest } from "@/lib/demoRequestForm";

// Visible labels (not placeholder-only) so a field keeps its name once filled.
const LABEL = "mb-1.5 block text-sm font-medium text-ink";
const INPUT = "w-full rounded-control border bg-paper px-3 py-3 text-ink outline-none placeholder:text-muted focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/40";

function FieldError({ id, message }) {
  if (!message) return null;
  return <p id={id} className="mt-1.5 text-sm font-medium text-danger">{message}</p>;
}

export default function DemoRequestForm() {
  const { t, href } = useI18n();
  const [sent, setSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  // { kind, key } from classifyDemoError when the send itself failed.
  const [failure, setFailure] = useState(null);
  const requestId = useRef(null);
  const formRef = useRef(null);
  const retryRef = useRef(null);

  // A failed send that no field explains keeps the keyboard where the
  // visitor can act: on "Try again" when there is one, else on the button.
  // (Submitting disables the button, which drops focus to the page.)
  useEffect(() => {
    if (!failure || failure.kind === "fields" || busy) return;
    (retryRef.current || formRef.current?.querySelector("button[type=submit]"))?.focus();
  }, [failure, busy]);

  const focusField = (field) => {
    const input = field && formRef.current?.elements.namedItem(field);
    if (input && typeof input.focus === "function") input.focus();
  };

  const fieldProps = (field) => ({
    name: field,
    "aria-invalid": errors[field] ? true : undefined,
    "aria-describedby": errors[field] ? `demo-${field}-error` : undefined,
    className: `${INPUT} ${errors[field] ? "border-danger" : "border-line"}`,
    onChange: () => errors[field] && setErrors((current) => ({ ...current, [field]: undefined })),
  });

  async function send() {
    const form = new FormData(formRef.current);
    const values = Object.fromEntries(["name", "phone", "email", "message", "website", "preferred_channel"].map((key) => [key, form.get(key) || ""]));
    const invalid = validateDemoRequest(values);
    setFailure(null);
    if (Object.keys(invalid).length) {
      setErrors(invalid);
      focusField(firstInvalidField(invalid));
      return;
    }
    setErrors({});
    requestId.current ||= crypto.randomUUID();
    setBusy(true);
    try {
      const res = await demoRequests.create({
        request_uuid: requestId.current,
        name: values.name.trim(), phone: values.phone.trim(), email: values.email.trim(),
        preferred_channel: values.preferred_channel || "whatsapp",
        message: values.message, website: values.website,
      });
      setSent(res.data.public_reference || res.data.reference);
    } catch (error) {
      const verdict = classifyDemoError(error);
      if (verdict.kind === "fields") {
        setErrors(verdict.fields);
        focusField(firstInvalidField(verdict.fields));
      }
      setFailure(verdict);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event) {
    event.preventDefault();
    if (!busy) send();
  }

  if (sent) {
    return (
      <div className="mt-8 rounded-control bg-ok/10 px-4 py-6 text-center font-medium text-ok" role="status">
        {t("landing.contactSent")}
        <span className="mt-3 block text-sm">{t("track.referenceLabel")}</span>
        <bdi dir="ltr" className="mt-1 block font-mono text-lg font-bold tracking-wide text-ink">{sent}</bdi>
        <Link href={href("/track")} className="mt-3 inline-block text-sm text-accent hover:underline">{t("track.thankYouTrack")}</Link>
      </div>
    );
  }

  const alert = failure && (
    failure.kind === "retry" ? t(failure.key)
      : failure.kind === "fields" ? t("home.formErrors.summary")
        : failure.kind === "throttled" ? t("home.formErrors.throttled")
          : t("home.formErrors.rejected")
  );
  const optional = <span className="font-normal text-muted"> ({t("home.formOptional")})</span>;

  return (
    <>
      <form ref={formRef} onSubmit={onSubmit} noValidate className="mt-8 space-y-4">
        <div className="hidden" aria-hidden="true"><input name="website" tabIndex={-1} autoComplete="off" /></div>
        {alert && (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-danger/40 bg-danger/5 px-4 py-3 text-sm font-medium text-danger">
            <span>{alert}</span>
            {failure.kind === "retry" && (
              <button ref={retryRef} type="button" onClick={send} disabled={busy} className="min-h-11 rounded-control border border-danger/40 bg-paper px-4 text-sm font-medium text-ink hover:border-danger">
                {t("home.formErrors.retry")}
              </button>
            )}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="demo-name" className={LABEL}>{t("landing.contactName")}</label>
            <input id="demo-name" required aria-required="true" maxLength={LIMITS.name} autoComplete="name" {...fieldProps("name")} />
            <FieldError id="demo-name-error" message={errors.name && t(`home.formErrors.${errors.name}`)} />
          </div>
          <div>
            <label htmlFor="demo-phone" className={LABEL}>{t("landing.contactPhone")}</label>
            <input
              id="demo-phone" type="tel" required aria-required="true" maxLength={LIMITS.phone} inputMode="tel" dir="ltr" autoComplete="tel"
              {...fieldProps("phone")}
              className={`${fieldProps("phone").className} text-start`}
            />
            <FieldError id="demo-phone-error" message={errors.phone && t(`home.formErrors.${errors.phone}`)} />
          </div>
        </div>
        <div>
          <label htmlFor="demo-email" className={LABEL}>{t("landing.contactEmail")}{optional}</label>
          <input id="demo-email" type="email" maxLength={LIMITS.email} dir="ltr" autoComplete="email" {...fieldProps("email")} className={`${fieldProps("email").className} text-start`} />
          <FieldError id="demo-email-error" message={errors.email && t(`home.formErrors.${errors.email}`)} />
        </div>
        <fieldset className="flex flex-wrap items-center gap-x-5 text-sm">
          <legend className="mb-1 font-medium text-ink">{t("landing.contactChannel")}</legend>
          {["whatsapp", "call", "email"].map((channel) => (
            <label key={channel} className="inline-flex min-h-11 cursor-pointer items-center gap-2 pe-1">
              <input type="radio" name="preferred_channel" value={channel} defaultChecked={channel === "whatsapp"} className="h-4 w-4 accent-accent" />
              {t(`landing.channels.${channel}`)}
            </label>
          ))}
        </fieldset>
        <div>
          <label htmlFor="demo-message" className={LABEL}>{t("landing.contactMessage")}{optional}</label>
          <textarea id="demo-message" rows={4} maxLength={LIMITS.message} {...fieldProps("message")} />
          <FieldError id="demo-message-error" message={errors.message && t(`home.formErrors.${errors.message}`)} />
        </div>
        <button
          type="submit" disabled={busy}
          className="w-full rounded-control bg-accent py-3 font-medium text-white hover:bg-accent-strong disabled:opacity-70"
        >
          {busy ? t("improvements.contactSending") : t("landing.contactSend")}
        </button>
      </form>
      <ContactChannels lead={t("home.supportDirect")} className="mt-6 border-t border-line pt-5" />
    </>
  );
}
