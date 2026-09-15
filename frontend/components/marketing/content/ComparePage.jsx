"use client";

import { Check, Minus } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import { comparison } from "@/lib/content/compare";

import { Breadcrumbs, CtaBand, Eyebrow, MoreSolutions, useContentLanguage } from "./shared";

function Cell({ value }) {
  if (value === true) return <Check size={18} className="mx-auto text-accent" aria-label="yes" />;
  if (value === false) return <Minus size={18} className="mx-auto text-muted" aria-label="no" />;
  return <span className="text-sm">{value}</span>;
}

export default function ComparePage({ slug }) {
  const { t } = useI18n();
  const language = useContentLanguage();
  const item = comparison(slug);
  if (!item) return null;
  const copy = item[language];

  return (
    <MarketingPage>
      <article className="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
        <Breadcrumbs items={[[copy.title, `/compare/${slug}`]]} />
        <header className="mt-6 max-w-3xl">
          <Eyebrow>{t("content.compareEyebrow")}</Eyebrow>
          <h1 className="mt-4 font-display text-3xl font-bold tracking-tight sm:text-5xl">{copy.title}</h1>
          <p className="mt-5 text-lg text-muted">{copy.lead}</p>
        </header>

        <div className="mt-10 overflow-x-auto rounded-card border border-line bg-paper shadow-card">
          <table className="w-full min-w-[640px] text-start">
            <thead className="bg-surface text-sm text-muted">
              <tr>
                <th className="px-4 py-3 text-start font-medium" />
                {copy.columns.map((column, index) => (
                  <th key={column} className={`px-4 py-3 text-center font-medium ${index === copy.columns.length - 1 ? "text-accent" : ""}`}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {copy.rows.map(([criterion, ...cells]) => (
                <tr key={criterion}>
                  <th scope="row" className="px-4 py-3 text-start text-sm font-medium">{criterion}</th>
                  {cells.map((cell, index) => (
                    <td key={index} className={`px-4 py-3 text-center ${index === cells.length - 1 ? "bg-accent/5 font-medium" : "text-muted"}`}><Cell value={cell} /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-muted">{t("content.comparisonNote")}</p>

        <section className="mt-12 max-w-3xl space-y-5 leading-relaxed sm:text-lg">
          {copy.verdict.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
        </section>

        <CtaBand title={copy.cta} />
        <MoreSolutions language={language} />
      </article>
    </MarketingPage>
  );
}
