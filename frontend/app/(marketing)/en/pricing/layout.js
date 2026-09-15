import JsonLd from "@/components/seo/JsonLd";
import { marketingMetadata } from "@/lib/marketingMeta";
import { pricingFaqJsonLd, webPageJsonLd } from "@/lib/seo";

export const metadata = marketingMetadata("/pricing", "en");

export default function PricingLayout({ children }) {
  return (
    <>
      <JsonLd data={[webPageJsonLd("/pricing", "en"), pricingFaqJsonLd("en")]} />
      {children}
    </>
  );
}
