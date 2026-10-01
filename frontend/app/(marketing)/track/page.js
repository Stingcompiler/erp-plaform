"use client";

// vezano.app/track/ — two tabs.
//
// "Store order or payment": one search box for web orders from any store on
// Vezano and subscription payments, a POST to /api/public/track/ (the query
// never lands in a URL) rendering the masked results it returns (backend:
// website/platform_tracking.py) — unchanged.
//
// "Trial or demo request" (#requests): since 2026-10-01 those open only
// with a 6-digit code emailed to the address stored on the request
// (backend: website/request_tracking.py): search → code → the requests.

import { useEffect, useState } from "react";
import { ExternalLink, MailCheck, MessageCircle, PackageSearch, Search, ShieldCheck } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import CodeStep, { codeErrorText } from "@/components/marketing/CodeStep";
import { useSiteContact } from "@/components/marketing/SiteContact";
import SuccessCheck from "@/components/ui/SuccessCheck";
import { publicTrack } from "@/lib/api";
import { VIEW_KEY, codeError, isRequestReference, liveView, viewRecord } from "@/lib/otpCode";
import { useHashTab } from "@/lib/useHashTab";

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

function OrderTracker({ onRequest }) {
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
      setAnswer({ results: response.data.results || [], asRequest: isRequestReference(q), query: q });
    } catch (error) {
      setAnswer(error?.response?.status === 429 ? { limited: true } : { error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={onSubmit} className="enter-rise mt-6 rounded-card border border-line bg-surface p-5 shadow-card sm:p-6">
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
        {answer?.asRequest && (
          <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-accent/30 bg-accent/5 p-4 text-sm">
            <span>{t("track.looksLikeRequest")}</span>
            <button type="button" onClick={() => onRequest(answer.query)} className="inline-flex min-h-11 items-center gap-2 rounded-control bg-accent px-4 py-2 font-medium text-white hover:bg-accent-strong">
              <MailCheck size={15} aria-hidden="true" />{t("track.trackAsRequest")}
            </button>
          </div>
        )}
        {answer?.results && answer.results.length === 0 && !answer.asRequest && (
          <p role="status" className="rounded-control border border-dashed border-line bg-surface p-4 text-sm text-muted">{t("track.notFound")}</p>
        )}
        {answer?.results?.length > 0 && (
          <>
            <p className="text-sm text-muted">{t("track.count", { count: answer.results.length })}</p>
            {answer.results.map((item) => <ResultCard key={`${item.kind}-${item.reference}-${item.created_at}`} item={item} />)}
          </>
          )}
        </div>
    </>
  );
}

function readStoredView() {
  try {
    return liveView(JSON.parse(sessionStorage.getItem(VIEW_KEY) || "null"));
  } catch {
    return null;
  }
}

function storeView(record) {
  try {
    if (record) sessionStorage.setItem(VIEW_KEY, JSON.stringify(record));
    else sessionStorage.removeItem(VIEW_KEY);
  } catch { /* private mode: the view simply does not survive a reload */ }
}

// One trial or demo request, after the code: its stages with dates, the
// team's note and the next step. Only that email's own requests reach here.
function RequestCard({ item }) {
  const { t, language } = useI18n();
  return (
    <article className="enter-rise rounded-card border border-line bg-paper p-5 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">
            {t(`track.kinds.${item.kind}`)}
            {item.standalone && <> · {t("track.standalone")}</>}
          </p>
          <h3 className="mt-0.5 font-mono text-lg font-bold tracking-wide" dir="ltr">{item.reference}</h3>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${TONES[item.tone] || TONES.info}`}>{item.status_label}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        <span>{when(item.created_at, language)}</span>
        {item.customer && <span className="min-w-0 break-words">{t("track.for")} <bdi className="text-ink">{item.customer}</bdi></span>}
        {item.plan && <span>{t("track.plan")}: <bdi className="text-ink">{item.plan}</bdi></span>}
      </div>
      {item.timeline?.length > 0 && (
        <>
          <h4 className="mt-4 text-sm font-semibold text-muted">{t("track.stages")}</h4>
          <Timeline steps={item.timeline} language={language} />
        </>
      )}
      {item.note && (
        <div className={`mt-4 rounded-control px-3 py-2 text-sm ${item.tone === "closed" ? "bg-danger/10 text-danger" : "bg-warn/15 text-ink"}`}>
          <p className="font-semibold">{t("track.teamNote")}</p>
          <p className="mt-0.5 whitespace-pre-line break-words">{item.note}</p>
          {item.note_updated_at && <p className="mt-1 text-xs opacity-80">{t("track.updated")}: {when(item.note_updated_at, language)}</p>}
        </div>
      )}
      {item.next && (
        <p className="mt-3 text-sm">
          <b>{t("track.next")}:</b> <span className="text-muted">{item.next}</span>
        </p>
      )}
    </article>
  );
}

function WhatsAppLink() {
  const { t } = useI18n();
  const { whatsappHref } = useSiteContact();
  if (!whatsappHref) return null;
  return (
    <a href={whatsappHref} target="_blank" rel="noreferrer noopener" className="mt-2 inline-flex min-h-11 items-center gap-2 rounded-control border border-line bg-surface px-4 py-2 text-sm font-medium text-ink hover:border-accent">
      <MessageCircle size={15} aria-hidden="true" />{t("track.whatsapp")}
    </a>
  );
}

// Trial (R…) and demo (D…) requests: search → the emailed code → the
// requests. The search answers the same whether or not anything matched,
// so the code step always follows; a verified view lasts 30 minutes in
// this tab (sessionStorage), so a reload or a language switch shows it
// again without a new code.
function RequestTracker({ initialQuery }) {
  const { t, language } = useI18n();
  const [query, setQuery] = useState(initialQuery || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // { id, hint, resendAfter } while a code is awaited.
  const [challenge, setChallenge] = useState(null);
  // { token, until, emailMasked, results, fresh } once verified.
  const [view, setView] = useState(null);

  useEffect(() => { if (initialQuery) setQuery(initialQuery); }, [initialQuery]);

  // A stored view (a reload) or a language switch: fetch it again.
  useEffect(() => {
    const record = view || readStoredView();
    if (!record) return undefined;
    let cancelled = false;
    publicTrack.requests.view({ token: record.token, language })
      .then((response) => {
        if (cancelled) return;
        setView((current) => ({
          ...record, fresh: current?.fresh || false,
          emailMasked: response.data.email_masked, results: response.data.results || [],
        }));
      })
      .catch((failure) => {
        if (cancelled) return;
        if (codeError(failure).code === "view_expired") { storeView(null); setView(null); }
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

  async function search(event) {
    event.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true); setError(null);
    try {
      const response = await publicTrack.requests.start({ q, language });
      setChallenge({ id: response.data.challenge_id, hint: response.data.sent_hint, resendAfter: response.data.resend_after || 60 });
    } catch (failure) {
      setError(codeError(failure));
    } finally {
      setBusy(false);
    }
  }

  async function verify(code) {
    const response = await publicTrack.requests.verify({ challenge_id: challenge.id, code, language });
    const record = viewRecord(response.data.token, response.data.expires_in);
    storeView(record);
    setChallenge(null);
    setView({ ...record, fresh: true, emailMasked: response.data.email_masked, results: response.data.results || [] });
  }

  async function resend() {
    const response = await publicTrack.requests.resend({ challenge_id: challenge.id });
    return response.data.resend_after;
  }

  function reset() {
    storeView(null);
    setView(null); setChallenge(null); setError(null);
  }

  if (view) {
    return (
      <div aria-live="polite" className="mt-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {view.fresh && <SuccessCheck size={32} />}
            <div className="min-w-0">
              <h2 className="break-words font-display text-lg font-semibold">
                {t("track.verifiedFor", { email: `⁨${view.emailMasked || ""}⁩` })}
              </h2>
              <p className="text-xs text-muted">{t("track.viewLasts")}</p>
            </div>
          </div>
          <button type="button" onClick={reset} className="inline-flex min-h-11 items-center gap-2 rounded-control border border-line bg-surface px-4 py-2 text-sm font-medium hover:border-accent">
            <Search size={15} aria-hidden="true" />{t("track.newSearch")}
          </button>
        </div>
        {view.results?.length ? (
          view.results.map((item) => <RequestCard key={`${item.kind}-${item.reference}`} item={item} />)
        ) : (
          <p role="status" className="rounded-control border border-dashed border-line bg-surface p-4 text-sm text-muted">{t("track.noRequests", { days: LOOKUP_DAYS })}</p>
        )}
      </div>
    );
  }

  if (challenge) {
    return (
      <div className="mt-6">
        <CodeStep
          key={challenge.id}
          sentText={challenge.hint
            ? t("track.codeSentTo", { email: `⁨${challenge.hint}⁩` })
            : t("track.codeSentGeneric")}
          resendAfter={challenge.resendAfter}
          onVerify={verify}
          onResend={resend}
          onBack={() => setChallenge(null)}
          backLabel={t("track.newSearch")}
        >
          <div className="mt-4 rounded-control bg-surface p-3 text-sm text-muted">
            <p>{t("track.noEmailHelp")}</p>
            <WhatsAppLink />
          </div>
        </CodeStep>
      </div>
    );
  }

  const errorText = codeErrorText(t, error);
  return (
    <form onSubmit={search} noValidate className="enter-rise mt-6 rounded-card border border-line bg-surface p-5 shadow-card sm:p-6">
      <label htmlFor="track-r" className="mb-1.5 block text-sm font-medium text-ink">{t("track.requestsLabel")}</label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="track-r"
          value={query}
          onChange={(event) => { setQuery(event.target.value); if (error) setError(null); }}
          required
          maxLength={254}
          autoComplete="off"
          placeholder={t("track.requestsPlaceholder")}
          aria-invalid={errorText ? "true" : undefined}
          aria-describedby={errorText ? "track-r-error track-r-hint" : "track-r-hint"}
          className="min-w-0 flex-1 rounded-control border border-line bg-paper px-3 py-3 text-ink outline-none placeholder:text-muted focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/40"
        />
        <button
          type="submit"
          disabled={busy || !query.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-control bg-accent px-6 py-3 font-medium text-white hover:bg-accent-strong disabled:opacity-60"
        >
          <MailCheck size={17} aria-hidden="true" />
          {busy ? t("track.sendingCode") : t("track.sendCode")}
        </button>
      </div>
      {errorText && <p id="track-r-error" role="alert" className="mt-2 text-sm text-danger">{errorText}</p>}
      <p id="track-r-hint" className="mt-3 flex items-start gap-2 text-sm text-muted">
        <ShieldCheck size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
        {t("track.requestsHint")}
      </p>
    </form>
  );
}

const TABS = ["orders", "requests"];

export default function TrackPage() {
  const { t } = useI18n();
  const [tab, setTab] = useHashTab(TABS, "orders");
  const [handoff, setHandoff] = useState("");

  function openRequests(query) {
    setHandoff(query);
    setTab("requests");
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

        <div role="tablist" aria-label={t("track.title")} className="mt-8 grid grid-cols-2 gap-1 rounded-card border border-line bg-surface p-1">
          {TABS.map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`track-tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`track-panel-${id}`}
              onClick={() => setTab(id)}
              className={`min-h-11 rounded-control px-2 py-2 text-sm font-medium transition-colors sm:px-4 ${
                tab === id ? "bg-paper text-accent shadow-card" : "text-muted hover:text-ink"
              }`}
            >
              {t(id === "orders" ? "track.tabOrders" : "track.tabRequests")}
            </button>
          ))}
        </div>

        <div id={`track-panel-${tab}`} role="tabpanel" aria-labelledby={`track-tab-${tab}`}>
          {tab === "orders" ? <OrderTracker onRequest={openRequests} /> : <RequestTracker initialQuery={handoff} />}
        </div>
      </section>
    </MarketingPage>
  );
}
