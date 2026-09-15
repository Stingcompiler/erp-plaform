"use client";

import Link from "next/link";
import { Check, CloudOff, Database, ShieldCheck } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import Shot from "@/components/marketing/Shot";

const SHOTS = {
  dashboard: { light: "/marketing/dashboard.png", dark: "/marketing/dashboard-dark.png" },
  pos: { light: "/marketing/pos.png", dark: "/marketing/pos-dark.png" },
  inventory: { light: "/marketing/inventory.png", dark: "/marketing/inventory.png" },
  debts: { light: "/marketing/debts.png", dark: "/marketing/debts.png" },
  users: { light: "/marketing/users.png", dark: "/marketing/users.png" },
};

function ModuleSection({ module, index }) {
  const shot = SHOTS[module.shot] || SHOTS.dashboard;
  const flip = index % 2 === 1;
  return (
    <section id={module.id} className="scroll-mt-24 border-t border-line py-14 first:border-t-0 sm:py-20">
      <div className={`grid items-start gap-8 lg:grid-cols-2 lg:gap-14 ${flip ? "lg:[&>*:first-child]:order-2" : ""}`}>
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{module.title}</h2>
          <p className="mt-3 text-muted sm:text-lg">{module.intro}</p>
          <ul className="mt-6 space-y-2.5">
            {module.points.map((line) => (
              <li key={line} className="flex items-start gap-2 text-sm sm:text-base">
                <Check size={18} className="mt-0.5 shrink-0 text-accent" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
        <Shot light={shot.light} dark={shot.dark} alt={module.title} priority={index === 0} />
      </div>
    </section>
  );
}

function Offline() {
  const { t } = useI18n();
  const steps = t("product.offlineSteps");
  return (
    <section className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <span className="grid h-10 w-10 place-items-center rounded-control bg-accent/10 text-accent"><CloudOff size={20} /></span>
            <h2 className="mt-4 font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("product.offlineTitle")}</h2>
            <p className="mt-4 text-muted sm:text-lg">{t("product.offlineBody")}</p>
          </div>
          <ol className="space-y-3">
            {Array.isArray(steps) && steps.map((step, index) => (
              <li key={step} className="flex items-start gap-3 rounded-card border border-line bg-paper p-4 shadow-card">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-white">{index + 1}</span>
                <span className="text-sm sm:text-base">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Security() {
  const { t } = useI18n();
  const rows = t("product.security");
  return (
    <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-control bg-accent/10 text-accent"><ShieldCheck size={20} /></span>
        <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("product.securityTitle")}</h2>
      </div>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {Array.isArray(rows) && rows.map(([title, body]) => (
          <div key={title} className="rounded-card border border-line bg-paper p-5 shadow-card">
            <h3 className="font-display font-semibold">{title}</h3>
            <p className="mt-2 text-sm text-muted">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Deploy() {
  const { t, href: localize } = useI18n();
  const options = t("product.deploy");
  const tech = t("product.tech");
  return (
    <section className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <h2 className="text-center font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("product.deployTitle")}</h2>
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          {Array.isArray(options) && options.map(([title, body, href, cta], index) => (
            <div key={title} className={`flex flex-col rounded-card border p-6 shadow-card ${index === 1 ? "border-line bg-ink text-paper" : "border-line bg-paper"}`}>
              <h3 className="font-display text-xl font-semibold">{title}</h3>
              <p className={`mt-2 ${index === 1 ? "text-paper/70" : "text-muted"}`}>{body}</p>
              <Link href={localize(href)} className={`mt-auto pt-6 font-medium ${index === 1 ? "text-accent" : "text-accent"} hover:underline`}>{cta} →</Link>
            </div>
          ))}
        </div>
        <div className="mt-10 flex items-center justify-center gap-2 text-sm text-muted">
          <Database size={16} /> {t("product.techTitle")}
        </div>
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {Array.isArray(tech) && tech.map((item) => (
            <span key={item} className="rounded-full border border-line bg-paper px-3 py-1 text-xs text-muted">{item}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function ProductPage() {
  const { t, href } = useI18n();
  const modules = t("product.modules");
  const list = Array.isArray(modules) ? modules : [];
  return (
    <MarketingPage>
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-accent/10 to-transparent" />
        <div className="mx-auto max-w-6xl px-4 pb-6 pt-16 sm:px-6 sm:pt-20">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="font-display text-3xl font-bold tracking-tight sm:text-5xl">{t("product.pageTitle")}</h1>
            <p className="mt-4 text-muted sm:text-lg">{t("product.pageSubtitle")}</p>
          </div>
          <nav className="mt-8 flex flex-wrap justify-center gap-2" aria-label={t("product.jump")}>
            {list.map((module) => (
              <a key={module.id} href={`#${module.id}`} className="rounded-full border border-line bg-paper px-3.5 py-1.5 text-sm text-ink hover:border-accent">{module.title}</a>
            ))}
          </nav>
        </div>
      </section>
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        {list.map((module, index) => <ModuleSection key={module.id} module={module} index={index} />)}
      </div>
      <Offline />
      <Security />
      <Deploy />
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="rounded-card border border-line bg-paper p-8 text-center shadow-card sm:p-12">
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("product.ctaTitle")}</h2>
          <p className="mx-auto mt-3 max-w-xl text-muted">{t("product.ctaBody")}</p>
          <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href={href("/register")} className="w-full rounded-control bg-accent px-6 py-3 font-medium text-white hover:bg-accent-strong sm:w-auto">{t("home.finalPrimary")}</Link>
            <Link href={href("/#contact")} className="w-full rounded-control border border-line bg-surface px-6 py-3 font-medium text-ink hover:border-accent sm:w-auto">{t("home.finalSecondary")}</Link>
          </div>
        </div>
      </section>
    </MarketingPage>
  );
}
