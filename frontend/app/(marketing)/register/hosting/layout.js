import JsonLd from "@/components/seo/JsonLd";
import { marketingMetadata } from "@/lib/marketingMeta";
import { webPageJsonLd } from "@/lib/seo";

export const metadata = marketingMetadata("/register/hosting", "ar");

export default function HostingLayout({ children }) {
  return (
    <>
      <JsonLd data={webPageJsonLd("/register/hosting", "ar")} />
      {children}
    </>
  );
}
