"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import { GUIDES_INDEX_PATH, INDEX_COPY, SOLUTIONS_INDEX_PATH } from "@/lib/content";
import { guide } from "@/lib/content/guides";
import { solution } from "@/lib/content/solutions";

import { Breadcrumbs, CtaBand, Eyebrow, MoreGuides, useContentLanguage } from "./shared";

export default function GuidePage({ slug }) {
  const { t, href, dir } = useI18n();
  const language = useContentLanguage();
  const item = guide(slug);
  if (!item) return null;
  const copy = item[language];
  const related = item.related ? solution(item.related) : null;
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;
  const date = new Date(item.published).toLocaleDateString(language === "ar" ? "ar" : "en", { dateStyle: "long" });

  return (
    <MarketingPage>
      <article className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <Breadcrumbs items={[[INDEX_COPY[GUIDES_INDEX_PATH][language].title, GUIDES_INDEX_PATH], [copy.title, `${GUIDES_INDEX_PATH}/${slug}`]]} />
        <header className="mt-6">
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
            <Eyebrow>{t("content.guidesEyebrow")}</Eyebrow>
            <span>{t("content.minutes", { minutes: item.minutes })}</span>
            <span>·</span>
            <time dateTime={item.published}>{t("content.published", { date })}</time>
          </div>
          <h1 className="mt-4 font-display text-3xl font-bold tracking-tight sm:text-4xl">{copy.title}</h1>
        </header>

        <div className="mt-8 space-y-5 text-lg leading-relaxed text-muted">
          {copy.intro.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
        </div>

        <div className="mt-12 space-y-12">
          {copy.sections.map((section) => (
            <section key={section.heading}>
              <h2 className="font-display text-2xl font-bold tracking-tight">{section.heading}</h2>
              <div className="mt-3 space-y-4 leading-relaxed sm:text-lg">
                {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
              </div>
              {section.bullets && (
                <ul className="mt-4 space-y-2">
                  {section.bullets.map((bullet) => (
                    <li key={bullet} className="flex items-start gap-2"><Check size={18} className="mt-1 shrink-0 text-accent" /><span>{bullet}</span></li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>

        <aside className="mt-12 rounded-card border-s-4 border-accent bg-surface p-6 shadow-card">
          <div className="text-xs font-semibold uppercase tracking-wide text-accent">{t("content.takeaway")}</div>
          <p className="mt-2 text-lg font-medium">{copy.takeaway}</p>
        </aside>

        {related && (
          <section className="mt-12 rounded-card border border-line bg-paper p-6">
            <div className="text-xs text-muted">{t("content.relatedSolution")}</div>
            <Link href={href(`${SOLUTIONS_INDEX_PATH}/${related.slug}`)} className="mt-2 inline-flex items-center gap-2 font-display text-lg font-semibold text-accent hover:underline">
              {related[language].title}<Arrow size={16} />
            </Link>
            <p className="mt-2 text-sm text-muted">{related[language].description}</p>
          </section>
        )}

        <CtaBand title={copy.cta} />
        <MoreGuides exclude={slug} language={language} />
      </article>
    </MarketingPage>
  );
}
