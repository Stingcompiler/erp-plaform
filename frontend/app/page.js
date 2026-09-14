"use client";

// Public marketing landing page for logged-out visitors (the app itself lives
// under /dashboard etc.). Rendered for everyone on the hosted platform; on a
// customer's standalone server there is nothing to market or register, so
// the root goes straight to sign-in.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import LandingPage from "@/components/landing/LandingPage";
import { cachedDeploymentMode, fetchDeploymentMode } from "@/lib/deploymentMode";

export default function Home() {
  const router = useRouter();
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
  return <LandingPage />;
}
