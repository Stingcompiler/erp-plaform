import JsonLd from "@/components/seo/JsonLd";
import { marketingMetadata } from "@/lib/marketingMeta";
import { webPageJsonLd } from "@/lib/seo";

export const metadata = marketingMetadata("/product", "ar");

export default function ProductLayout({ children }) {
  return (
    <>
      <JsonLd data={webPageJsonLd("/product", "ar")} />
      {children}
    </>
  );
}
