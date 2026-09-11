// Set NEXT_PUBLIC_DEMO_URL on the hosted marketing build to point at the
// isolated Vezano trial deployment. The local fallback keeps the CTA useful
// before a public demo host is provisioned.
export const DEMO_URL = process.env.NEXT_PUBLIC_DEMO_URL || "/login?demo=1";
