// Server layout: the page itself is a client component (it fetches live
// plans), and only server files may export metadata.
import JsonLd from "@/components/seo/JsonLd";
import { marketingMetadata } from "@/lib/marketingMeta";
import { pricingFaqJsonLd, webPageJsonLd } from "@/lib/seo";

export const metadata = marketingMetadata("/pricing", "ar");

export default function PricingLayout({ children }) {
  return (
    <>
      <JsonLd data={[webPageJsonLd("/pricing", "ar"), pricingFaqJsonLd("ar")]} />
      {children}
    </>
  );
}
