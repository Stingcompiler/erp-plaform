"use client";

import Link from "next/link";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import { GUIDES_INDEX_PATH, INDEX_COPY, SOLUTIONS_INDEX_PATH } from "@/lib/content";
import { COMPARISONS } from "@/lib/content/compare";
import { GUIDES } from "@/lib/content/guides";
import { SOLUTIONS } from "@/lib/content/solutions";

import { Breadcrumbs, CtaBand, GuideCard, SolutionCard, useContentLanguage } from "./shared";

function IndexHeader({ path }) {
  const language = useContentLanguage();
  const copy = INDEX_COPY[path][language];
  return (
    <>
      <Breadcrumbs items={[[copy.title, path]]} />
      <header className="mt-6 max-w-3xl">
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-5xl">{copy.title}</h1>
        <p className="mt-5 text-lg text-muted">{copy.description}</p>
      </header>
    </>
  );
}

export function SolutionsIndexPage() {
  const { t, href } = useI18n();
  const language = useContentLanguage();
  return (
    <MarketingPage>
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <IndexHeader path={SOLUTIONS_INDEX_PATH} />
        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          {SOLUTIONS.map((item) => <SolutionCard key={item.slug} item={item} language={language} />)}
        </div>
        <section className="mt-12">
          <h2 className="font-display text-2xl font-bold tracking-tight">{t("content.compareEyebrow")}</h2>
          <ul className="mt-4 space-y-2">
            {COMPARISONS.map((item) => (
              <li key={item.slug}>
                <Link href={href(`/compare/${item.slug}`)} className="font-medium text-accent hover:underline">{item[language].title}</Link>
                <p className="text-sm text-muted">{item[language].description}</p>
              </li>
            ))}
          </ul>
        </section>
        <CtaBand title={t("home.finalTitle")} />
      </div>
    </MarketingPage>
  );
}

export function GuidesIndexPage() {
  const { t } = useI18n();
  const language = useContentLanguage();
  return (
    <MarketingPage>
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <IndexHeader path={GUIDES_INDEX_PATH} />
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {GUIDES.map((item) => <GuideCard key={item.slug} item={item} language={language} />)}
        </div>
        <CtaBand title={t("home.finalTitle")} />
      </div>
    </MarketingPage>
  );
}
