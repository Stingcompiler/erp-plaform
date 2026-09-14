"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { useI18n } from "../providers/I18nProvider";
import { MarketingPage } from "@/components/marketing/Chrome";
import RegisterForm from "@/components/marketing/RegisterForm";

function Heading() {
  const { t } = useI18n();
  const params = useSearchParams();
  const standalone = params.get("mode") === "standalone";
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

export default function RegisterPage() {
  return (
    <MarketingPage>
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        {/* useSearchParams needs a Suspense boundary for the static export. */}
        <Suspense fallback={null}>
          <Heading />
          <div className="mt-10">
            <RegisterForm />
          </div>
        </Suspense>
      </section>
    </MarketingPage>
  );
}
