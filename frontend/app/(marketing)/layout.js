import { marketingMetadata } from "@/lib/marketingMeta";

// The public pages, Arabic at the root and English under /en/. This layout
// carries the Arabic home metadata (app/page.js is a client component and
// cannot export any); every other page overrides it in its own layout.
export const metadata = marketingMetadata("/", "ar");

export default function MarketingLayout({ children }) {
  return children;
}
