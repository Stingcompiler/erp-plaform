"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { useI18n } from "@/app/providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import RegisterForm from "@/components/marketing/RegisterForm";

function HeadingView({ standalone }) {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-2xl text-center">
      <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
        {t(standalone ? "register.standaloneTitle" : "register.pageTitle")}
      </h1>
      <p className="mt-4 text-muted sm:text-lg">
        {t(standalone ? "register.standaloneSubtitle" : "register.pageSubtitle")}
      </p>
    </div>
  );
}

function Heading() {
  const params = useSearchParams();
  return <HeadingView standalone={params.get("mode") === "standalone"} />;
}

export default function RegisterPage() {
  return (
    <MarketingPage>
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        {/* useSearchParams needs a Suspense boundary for the static export,
            and whatever sits inside one is missing from the exported HTML.
            The fallback is the default (trial) heading, so crawlers and the
            first paint get the page's real <h1>; ?mode=standalone swaps it
            once the client reads the query. */}
        <Suspense fallback={<HeadingView standalone={false} />}>
          <Heading />
        </Suspense>
        <div className="mt-10">
          <Suspense fallback={null}>
            <RegisterForm />
          </Suspense>
        </div>
      </section>
    </MarketingPage>
  );
}
