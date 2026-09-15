"use client";

import Link from "next/link";
import { Check } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import Shot from "@/components/marketing/Shot";
import { SOLUTIONS_INDEX_PATH } from "@/lib/content";
import { solution } from "@/lib/content/solutions";
import { INDEX_COPY } from "@/lib/content";

import { Breadcrumbs, CtaBand, Eyebrow, Faq, MoreSolutions, useContentLanguage } from "./shared";

export default function SolutionPage({ slug }) {
  const { t, href } = useI18n();
  const language = useContentLanguage();
  const item = solution(slug);
  if (!item) return null;
  const copy = item[language];
  const shot = { light: `/marketing/${item.shot}.png`, dark: `/marketing/${item.shot}${item.shot === "pos" || item.shot === "dashboard" ? "-dark" : ""}.png` };

  return (
    <MarketingPage>
      <article className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <Breadcrumbs items={[[INDEX_COPY[SOLUTIONS_INDEX_PATH][language].title.split(" — ")[0], SOLUTIONS_INDEX_PATH], [copy.title, `${SOLUTIONS_INDEX_PATH}/${slug}`]]} />
        <header className="mt-6 grid items-center gap-8 lg:grid-cols-2 lg:gap-14">
          <div>
            <Eyebrow>{t("content.solutionsEyebrow")}</Eyebrow>
            <h1 className="mt-4 font-display text-3xl font-bold tracking-tight sm:text-5xl">{copy.title}</h1>
            <p className="mt-5 text-lg text-muted">{copy.lead}</p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link href={href("/register")} className="rounded-control bg-accent px-6 py-3 text-center font-medium text-white shadow-card hover:bg-accent-strong">{t("content.startTrial")}</Link>
              <Link href={href("/product")} className="rounded-control border border-line bg-surface px-6 py-3 text-center font-medium text-ink hover:border-accent">{t("landing.navFeatures")}</Link>
            </div>
          </div>
          <Shot light={shot.light} dark={shot.dark} alt={copy.title} priority />
        </header>

        <div className="mt-16 grid gap-10 lg:grid-cols-[1fr_280px] lg:gap-16">
          <div className="space-y-12">
            {copy.sections.map((section) => (
              <section key={section.heading}>
                <h2 className="font-display text-2xl font-bold tracking-tight">{section.heading}</h2>
                <p className="mt-3 leading-relaxed text-muted sm:text-lg">{section.body}</p>
                {section.bullets && (
                  <ul className="mt-4 space-y-2">
                    {section.bullets.map((bullet) => (
                      <li key={bullet} className="flex items-start gap-2"><Check size={18} className="mt-1 shrink-0 text-accent" /><span>{bullet}</span></li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
            <Faq items={copy.faq} />
          </div>
          <aside className="lg:sticky lg:top-24 lg:self-start">
            <div className="rounded-card border border-line bg-surface p-5 shadow-card">
              <h2 className="font-display font-semibold">{copy.cta}</h2>
              <p className="mt-2 text-sm text-muted">{t("home.heroNote")}</p>
              <Link href={href("/register")} className="mt-4 block rounded-control bg-accent px-4 py-3 text-center font-medium text-white hover:bg-accent-strong">{t("content.startTrial")}</Link>
              <Link href={href("/pricing")} className="mt-2 block rounded-control border border-line px-4 py-3 text-center font-medium hover:border-accent">{t("content.seePricing")}</Link>
            </div>
          </aside>
        </div>

        <CtaBand title={copy.cta} />
        <MoreSolutions exclude={slug} language={language} />
      </article>
    </MarketingPage>
  );
}
