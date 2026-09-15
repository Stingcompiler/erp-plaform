"use client";

// Public marketing landing page for logged-out visitors (the app itself lives
// under /dashboard etc.). Rendered for everyone on the hosted platform; on a
// customer's standalone server there is nothing to market or register, so
// the root goes straight to sign-in.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useI18n } from "@/app/providers/I18nProvider";

import LandingPage from "@/components/landing/LandingPage";
import JsonLd from "@/components/seo/JsonLd";
import { homeFaqJsonLd } from "@/lib/seo";
import { cachedDeploymentMode, fetchDeploymentMode } from "@/lib/deploymentMode";

export default function Home() {
  const router = useRouter();
  const { language } = useI18n();
  const [mode, setMode] = useState(cachedDeploymentMode());

  useEffect(() => {
    let cancelled = false;
    fetchDeploymentMode().then((value) => { if (!cancelled) setMode(value); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (mode === "standalone") router.replace("/login");
  }, [mode, router]);

  if (mode === "standalone") return null;
  return (
    <>
      {/* Pre-rendered into the exported HTML (also under /en/), which is what
          a crawler reads; it lists the same questions the page shows. */}
      <JsonLd data={homeFaqJsonLd(language)} />
      <LandingPage />
    </>
  );
}
