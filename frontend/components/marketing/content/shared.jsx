"use client";

// Building blocks shared by the generated content pages (solutions, guides,
// comparisons). All client-side: they read the language from the URL through
// the provider and prefix links with href().
import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { SOLUTIONS_INDEX_PATH, GUIDES_INDEX_PATH } from "@/lib/content";
import { GUIDES } from "@/lib/content/guides";
import { SOLUTIONS } from "@/lib/content/solutions";

export function useContentLanguage() {
  const { language } = useI18n();
  return language === "en" ? "en" : "ar";
}

export function Eyebrow({ children }) {
  return <span className="inline-block rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">{children}</span>;
}

export function Breadcrumbs({ items }) {
  // items: [[label, path]]; the last one is the current page.
  const { t, href } = useI18n();
  const all = [[t("content.breadcrumbHome"), "/"], ...items];
  return (
    <nav aria-label="breadcrumb" className="text-sm text-muted">
      <ol className="flex flex-wrap items-center gap-1.5">
        {all.map(([label, path], index) => {
          const last = index === all.length - 1;
          return (
            <li key={path} className="flex items-center gap-1.5">
              {index > 0 && <span aria-hidden="true">/</span>}
              {last ? <span className="text-ink">{label}</span> : <Link href={href(path)} className="hover:text-ink hover:underline">{label}</Link>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function Faq({ items }) {
  const { t } = useI18n();
  if (!items?.length) return null;
  return (
    <section className="mt-14">
      <h2 className="font-display text-2xl font-bold tracking-tight">{t("content.faqTitle")}</h2>
      <div className="mt-6 divide-y divide-line rounded-card border border-line bg-surface">
        {items.map(([question, answer]) => (
          <details key={question} className="group px-5 py-4">
            <summary className="cursor-pointer list-none font-medium marker:hidden">{question}</summary>
            <p className="mt-2 text-muted">{answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

export function CtaBand({ title }) {
  const { t, href } = useI18n();
  return (
    <section className="mt-14 rounded-card bg-ink p-8 text-paper sm:p-10">
      <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{title}</h2>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Link href={href("/register")} className="rounded-control bg-accent px-6 py-3 text-center font-medium text-white hover:bg-accent-strong">{t("content.startTrial")}</Link>
        <Link href={href("/pricing")} className="rounded-control border border-white/20 px-6 py-3 text-center font-medium text-paper hover:bg-white/10">{t("content.seePricing")}</Link>
      </div>
    </section>
  );
}

export function SolutionCard({ item, language }) {
  const { href, dir } = useI18n();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;
  const copy = item[language];
  return (
    <Link href={href(`${SOLUTIONS_INDEX_PATH}/${item.slug}`)} className="group flex h-full flex-col rounded-card border border-line bg-surface p-6 shadow-card transition-transform hover:-translate-y-0.5 hover:border-accent">
      <h3 className="font-display text-lg font-semibold">{copy.title}</h3>
      <p className="mt-2 flex-1 text-sm text-muted">{copy.description}</p>
      <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent">{copy.cta}<Arrow size={15} /></span>
    </Link>
  );
}

export function GuideCard({ item, language }) {
  const { t, href, dir } = useI18n();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;
  const copy = item[language];
  return (
    <Link href={href(`${GUIDES_INDEX_PATH}/${item.slug}`)} className="group flex h-full flex-col rounded-card border border-line bg-surface p-6 shadow-card transition-transform hover:-translate-y-0.5 hover:border-accent">
      <span className="text-xs text-muted">{t("content.minutes", { minutes: item.minutes })}</span>
      <h3 className="mt-2 font-display text-lg font-semibold">{copy.title}</h3>
      <p className="mt-2 flex-1 text-sm text-muted">{copy.description}</p>
      <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent">{t("content.guidesEyebrow")}<Arrow size={15} /></span>
    </Link>
  );
}

export function MoreSolutions({ exclude, language }) {
  const { t, href } = useI18n();
  const others = SOLUTIONS.filter((item) => item.slug !== exclude);
  if (!others.length) return null;
  return (
    <section className="mt-14">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-display text-2xl font-bold tracking-tight">{t("content.moreSolutions")}</h2>
        <Link href={href(SOLUTIONS_INDEX_PATH)} className="text-sm font-medium text-accent hover:underline">{t("content.allSolutions")}</Link>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {others.map((item) => <SolutionCard key={item.slug} item={item} language={language} />)}
      </div>
    </section>
  );
}

export function MoreGuides({ exclude, language }) {
  const { t, href } = useI18n();
  const others = GUIDES.filter((item) => item.slug !== exclude);
  if (!others.length) return null;
  return (
    <section className="mt-14">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-display text-2xl font-bold tracking-tight">{t("content.moreGuides")}</h2>
        <Link href={href(GUIDES_INDEX_PATH)} className="text-sm font-medium text-accent hover:underline">{t("content.allGuides")}</Link>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {others.map((item) => <GuideCard key={item.slug} item={item} language={language} />)}
      </div>
    </section>
  );
}
