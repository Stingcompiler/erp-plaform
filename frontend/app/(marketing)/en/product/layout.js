import JsonLd from "@/components/seo/JsonLd";
import { marketingMetadata } from "@/lib/marketingMeta";
import { webPageJsonLd } from "@/lib/seo";

export const metadata = marketingMetadata("/product", "en");

export default function ProductLayout({ children }) {
  return (
    <>
      <JsonLd data={webPageJsonLd("/product", "en")} />
      {children}
    </>
  );
}
