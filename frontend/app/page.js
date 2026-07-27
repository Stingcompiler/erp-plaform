"use client";

// Public marketing landing page for logged-out visitors (the app itself lives
// under /dashboard etc.). Rendered for everyone; the header/hero CTAs point a
// logged-in visitor to their dashboard instead of the sign-in page.
import LandingPage from "@/components/landing/LandingPage";

export default function Home() {
  return <LandingPage />;
}
