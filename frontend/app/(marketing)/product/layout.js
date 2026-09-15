import JsonLd from "@/components/seo/JsonLd";
import { webPageJsonLd } from "@/lib/seo";

const title = "المنتج — نقطة البيع والمخزون والمشتريات والديون والفروع في نظام واحد";
const description =
  "كل ما يفعله فيزانو وحدة بوحدة: كاشير يعمل بلا إنترنت، مخزون بالدفعات والصلاحية، مشتريات ومرتجعات، دفتر ديون العملاء، تقارير، فروع ومستودعات متعددة، موارد بشرية وعملاء.";

export const metadata = {
  title,
  description,
  alternates: { canonical: "/product/" },
  openGraph: { title, description, url: "/product/" },
  twitter: { title, description },
};

export default function ProductLayout({ children }) {
  return (
    <>
      <JsonLd data={webPageJsonLd({ path: "/product/", name: title, description })} />
      {children}
    </>
  );
}
