"use client";

import { Check, Minus } from "lucide-react";

import { useI18n } from "../providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import PlanCards from "@/components/marketing/PlanCards";

function Cell({ value }) {
  if (value === true) return <Check size={18} className="mx-auto text-accent" />;
  if (value === false) return <Minus size={18} className="mx-auto text-muted" />;
  return <span className="text-sm">{value}</span>;
}

function Compare() {
  const { t } = useI18n();
  const rows = t("pricing.compareRows");
  if (!Array.isArray(rows)) return null;
  return (
    <section className="mx-auto max-w-4xl px-4 py-16 sm:px-6">
      <h2 className="text-center font-display text-2xl font-bold tracking-tight">{t("pricing.compareTitle")}</h2>
      <div className="mt-8 overflow-x-auto rounded-card border border-line bg-paper shadow-card">
        <table className="w-full min-w-[520px] text-start">
          <thead className="bg-surface text-sm text-muted">
            <tr>
              <th className="px-4 py-3 text-start font-medium" />
              <th className="px-4 py-3 text-center font-medium">{t("pricing.compareHosted")}</th>
              <th className="px-4 py-3 text-center font-medium">{t("pricing.compareStandalone")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, hosted, standalone]) => (
              <tr key={label} className="border-t border-line">
                <td className="px-4 py-3 text-sm">{label}</td>
                <td className="px-4 py-3 text-center"><Cell value={hosted} /></td>
                <td className="px-4 py-3 text-center"><Cell value={standalone} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Faq() {
  const { t } = useI18n();
  const items = t("pricing.faq");
  if (!Array.isArray(items)) return null;
  return (
    <section className="border-t border-line bg-surface">
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <h2 className="text-center font-display text-2xl font-bold tracking-tight">{t("pricing.faqTitle")}</h2>
        <div className="mt-8 space-y-3">
          {items.map(([question, answer]) => (
            <details key={question} className="group rounded-card border border-line bg-paper p-5">
              <summary className="cursor-pointer list-none font-medium marker:content-none">{question}</summary>
              <p className="mt-3 text-sm text-muted">{answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function PricingPage() {
  const { t } = useI18n();
  return (
    <MarketingPage>
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-accent/10 to-transparent" />
        <div className="mx-auto max-w-6xl px-4 pb-8 pt-16 sm:px-6 sm:pt-20">
          <div className="mx-auto max-w-2xl text-center">
            <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">{t("pricing.pageTitle")}</h1>
            <p className="mt-4 text-muted sm:text-lg">{t("pricing.pageSubtitle")}</p>
          </div>
          <div className="mt-12">
            <PlanCards />
          </div>
        </div>
      </section>
      <Compare />
      <Faq />
    </MarketingPage>
  );
}
