import { marketingMetadata } from "@/lib/marketingMeta";

// English edition of the public pages. The page components are the same
// files as the Arabic ones; the language comes from the URL (lib/locale.js),
// which is what makes each language crawlable at its own address.
export const metadata = marketingMetadata("/", "en");

export default function EnglishMarketingLayout({ children }) {
  return children;
}
