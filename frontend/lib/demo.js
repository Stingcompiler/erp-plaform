// Set NEXT_PUBLIC_DEMO_URL on the hosted marketing build to point at an
// isolated, seeded Vezano demo deployment. Until one exists, the CTA sends
// visitors to the free-trial form instead of a login screen they have no
// account for — the trial *is* the demo in the current commercial model.
export const LIVE_DEMO_URL = process.env.NEXT_PUBLIC_DEMO_URL || "";
export const HAS_LIVE_DEMO = LIVE_DEMO_URL.startsWith("http");
export const DEMO_URL = HAS_LIVE_DEMO ? LIVE_DEMO_URL : "#trial";
