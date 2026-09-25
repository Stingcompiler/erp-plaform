"use client";

// vezano.app/track/ — one search box for web orders from any store on Vezano
// and for the visitor's own registration / demo requests and subscription
// payments. The site is a static export, so the search is a POST to
// /api/public/track/ (the query never lands in a URL) and the page renders
// the masked results it returns (backend: website/platform_tracking.py).

import { useState } from "react";
import { ExternalLink, PackageSearch, Search, ShieldCheck } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import { publicTrack } from "@/lib/api";

const LOOKUP_DAYS = 90;

const TONES = {
  pending: "bg-warn/15 text-warn",
  warn: "bg-warn/15 text-warn",
  ok: "bg-ok/15 text-ok",
  closed: "bg-danger/10 text-danger",
  info: "bg-accent/10 text-accent",
};

function orderTone(item) {
  if (item.closed) return "closed";
  if (item.status === "completed") return "ok";
  if (item.status === "new") return "pending";
  return "info";
}

function when(value, language) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString(language === "ar" ? "ar-u-nu-latn" : "en-GB", {
      dateStyle: "medium", timeStyle: "short",
    });
  } catch {
    return String(value);
  }
}

function Timeline({ steps, language }) {
  return (
    <ol className="mt-2 space-y-1">
      {steps.map((step, index) => (
        <li
          key={`${step.label}-${index}`}
          aria-current={step.current ? "step" : undefined}
          className={`relative ps-6 ${step.done ? "text-ink" : "text-muted"}`}
        >
          <span
            aria-hidden="true"
            className={`absolute start-1 top-2 h-2.5 w-2.5 rounded-full border-2 ${
              step.closed ? "border-danger bg-danger" : step.done ? "border-accent bg-accent" : "border-line bg-paper"
            }`}
          />
          <span className={step.current ? `font-semibold ${step.closed ? "text-danger" : "text-accent"}` : ""}>{step.label}</span>
          {step.at && <span className="ms-2 text-xs text-muted">{when(step.at, language)}</span>}
        </li>
      ))}
    </ol>
  );
}

function OrderBody({ item }) {
  const { t, language } = useI18n();
  return (
    <>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        <span>{item.delivery ? t("track.delivery") : t("track.pickup")}</span>
        {item.branch_name && <span>{item.branch_name}</span>}
      </div>
      <Timeline steps={item.timeline || []} language={language} />
      {item.lines?.length > 0 && (
        <>
          <h4 className="mt-4 text-sm font-semibold text-muted">{t("track.items")}</h4>
          <ul className="mt-1 divide-y divide-line text-sm">
            {item.lines.map((line, index) => (
              <li key={`${line.name}-${index}`} className="flex justify-between gap-3 py-1.5">
                <span className="min-w-0 break-words">{line.name}</span>
                <span className="shrink-0 tabular-nums" dir="ltr">× {line.quantity}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {item.total_display && (
        <p className="mt-2 font-semibold">
          {item.tax_amount ? t("track.totalTaxed") : t("track.total")}:{" "}
          <bdi dir="ltr" className="tabular-nums">{item.total_display}</bdi>
        </p>
      )}
      {item.payment && (
        <p className={`mt-1 text-sm ${item.payment === "verified" ? "text-ok" : item.payment === "pending" ? "text-warn" : "text-danger"}`}>
          {t(`track.payment.${item.payment}`)}
        </p>
      )}
      {(item.branch_phone || item.branch_name) && (
        <p className="mt-3 text-sm text-muted">
          {t("track.questions")}{" "}
          {item.branch_phone && <a href={`tel:${item.branch_phone}`} dir="ltr" className="text-accent hover:underline">{item.branch_phone}</a>}
        </p>
      )}
      <a
        href={item.store_track_path}
        className="mt-4 inline-flex items-center gap-2 rounded-control border border-line bg-paper px-4 py-2.5 text-sm font-medium text-ink hover:border-accent"
      >
        <ExternalLink size={15} aria-hidden="true" />
        {t("track.openStore")}
      </a>
    </>
  );
}

function ResultCard({ item }) {
  const { t, language } = useI18n();
  const tone = item.kind === "order" ? orderTone(item) : item.tone;
  return (
    <article className="rounded-card border border-line bg-paper p-5 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">
            {t(`track.kinds.${item.kind}`)}
            {item.kind === "order" && item.store_name && <> · <bdi className="text-ink">{item.store_name}</bdi></>}
            {item.standalone && <> · {t("track.standalone")}</>}
          </p>
          <h3 className="mt-0.5 font-mono text-lg font-bold tracking-wide" dir="ltr">{item.reference}</h3>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${TONES[tone] || TONES.info}`}>{item.status_label}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        <span>{when(item.created_at, language)}</span>
        {item.customer && <span>{t("track.for")} <bdi>{item.customer}</bdi></span>}
        {item.kind === "subscription_payment" && item.total_display && (
          <span>{t("track.amount")}: <bdi dir="ltr" className="tabular-nums">{item.total_display}</bdi></span>
        )}
      </div>
      {item.reason && (
        <p className="mt-3 rounded-control bg-danger/10 px-3 py-2 text-sm text-danger">
          <b>{t("track.reason")}:</b> {item.reason}
        </p>
      )}
      {item.kind === "order" ? <OrderBody item={item} /> : item.next && (
        <p className="mt-3 text-sm">
          <b>{t("track.next")}:</b> <span className="text-muted">{item.next}</span>
        </p>
      )}
    </article>
  );
}

export default function TrackPage() {
  const { t, language } = useI18n();
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  // null before the first search; then { results } or { limited } or { error }.
  const [answer, setAnswer] = useState(null);

  async function onSubmit(event) {
    event.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    try {
      const response = await publicTrack.search({ q, language });
      setAnswer({ results: response.data.results || [] });
    } catch (error) {
      setAnswer(error?.response?.status === 429 ? { limited: true } : { error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <MarketingPage>
      <section className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <div className="text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-card bg-accent/10 text-accent">
            <PackageSearch size={24} aria-hidden="true" />
          </span>
          <h1 className="mt-4 font-display text-3xl font-bold tracking-tight sm:text-4xl">{t("track.title")}</h1>
          <p className="mx-auto mt-3 max-w-xl text-muted">{t("track.subtitle")}</p>
        </div>

        <form onSubmit={onSubmit} className="mt-8 rounded-card border border-line bg-surface p-5 shadow-card sm:p-6">
          <label htmlFor="track-q" className="mb-1.5 block text-sm font-medium text-ink">{t("track.label")}</label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              id="track-q"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              required
              maxLength={254}
              autoComplete="off"
              placeholder={t("track.placeholder")}
              className="min-w-0 flex-1 rounded-control border border-line bg-paper px-3 py-3 text-ink outline-none placeholder:text-muted focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/40"
            />
            <button
              type="submit"
              disabled={busy}
              className="inline-flex items-center justify-center gap-2 rounded-control bg-accent px-6 py-3 font-medium text-white hover:bg-accent-strong disabled:opacity-60"
            >
              <Search size={17} aria-hidden="true" />
              {busy ? t("track.searching") : t("track.search")}
            </button>
          </div>
          <p className="mt-3 text-sm text-muted">{t("track.hint", { days: LOOKUP_DAYS })}</p>
          <p className="mt-2 flex items-start gap-2 text-xs text-muted">
            <ShieldCheck size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
            {t("track.privacy")}
          </p>
        </form>

        <div aria-live="polite" className="mt-6 space-y-4">
          {answer?.limited && <p role="status" className="rounded-control bg-warn/15 p-4 text-sm text-warn">{t("track.limited")}</p>}
          {answer?.error && <p role="alert" className="rounded-control bg-danger/10 p-4 text-sm text-danger">{t("track.error")}</p>}
          {answer?.results && answer.results.length === 0 && (
            <p role="status" className="rounded-control border border-dashed border-line bg-surface p-4 text-sm text-muted">{t("track.notFound")}</p>
          )}
          {answer?.results?.length > 0 && (
            <>
              <p className="text-sm text-muted">{t("track.count", { count: answer.results.length })}</p>
              {answer.results.map((item) => <ResultCard key={`${item.kind}-${item.reference}-${item.created_at}`} item={item} />)}
            </>
          )}
        </div>
      </section>
    </MarketingPage>
  );
}
