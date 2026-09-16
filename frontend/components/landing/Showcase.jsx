"use client";

// "Stores on Vezano": complete, listed customer pages, fetched at runtime
// from the public showcase feed. Renders nothing until there is at least one,
// so an empty platform never shows an empty strip.
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";
import { publicSite } from "@/lib/api";

export default function Showcase() {
  const { t, dir } = useI18n();
  const [sites, setSites] = useState([]);
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  useEffect(() => {
    let cancelled = false;
    publicSite
      .showcase()
      .then((response) => { if (!cancelled) setSites(response.data.sites || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (!sites.length) return null;

  return (
    <section className="border-t border-line bg-surface" id="stores">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-accent">{t("home.showcaseEyebrow")}</p>
            <h2 className="mt-2 font-display text-2xl font-bold tracking-tight sm:text-3xl">{t("home.showcaseTitle")}</h2>
            <p className="mt-2 max-w-2xl text-muted">{t("home.showcaseBody")}</p>
          </div>
          <a href="/s/" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">
            {t("home.showcaseAll")}<Arrow size={15} />
          </a>
        </div>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {sites.slice(0, 8).map((site) => (
            <a key={site.url} href={site.path} className="group overflow-hidden rounded-card border border-line bg-paper shadow-card transition-transform hover:-translate-y-0.5">
              <div className="relative aspect-[16/9] bg-ink/90">
                {site.cover && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={site.cover} alt="" loading="lazy" className="h-full w-full object-cover" />
                )}
                {site.logo && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={site.logo} alt={site.name} className="absolute -bottom-4 start-3 h-10 w-10 rounded-lg border-2 border-paper bg-paper object-cover" />
                )}
              </div>
              <div className="px-4 pb-4 pt-6">
                <h3 className="font-display font-semibold group-hover:text-accent">{site.name}</h3>
                {site.tagline && <p className="mt-1 line-clamp-2 text-sm text-muted">{site.tagline}</p>}
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-muted">
                  {site.category_label && <span className="rounded-full bg-surface px-2 py-0.5">{site.category_label}</span>}
                  {site.city && <span className="rounded-full bg-surface px-2 py-0.5">{site.city}</span>}
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
