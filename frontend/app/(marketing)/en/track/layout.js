import { NOINDEX } from "@/lib/site";

// See app/(marketing)/track/layout.js: noindex and not in the sitemap.
export const metadata = {
  title: "Track an order or a request",
  description: "Follow your order from any store on Vezano Pro, or your registration, demo request or subscription payment, by reference, phone, email or name.",
  robots: NOINDEX,
};

export default function TrackLayout({ children }) {
  return children;
}
