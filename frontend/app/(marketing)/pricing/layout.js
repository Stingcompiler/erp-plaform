// Server layout: the page itself is a client component (it fetches live
// plans), and only server files may export metadata.
import JsonLd from "@/components/seo/JsonLd";
import { pricingFaqJsonLd, webPageJsonLd } from "@/lib/seo";

const title = "الأسعار والباقات — تجربة مجانية 14 يومًا أو رخصة دائمة لخادمك";
const description =
  "باقات فيزانو للمحلات والموزعين: أسعار واضحة بلا رسوم على كل عملية. كل باقة تشمل العربية والإنجليزية ونقطة بيع تعمل بلا اتصال وصلاحيات حسب الدور، أو رخصة دائمة على خادمك الخاص.";

export const metadata = {
  title,
  description,
  alternates: { canonical: "/pricing/" },
  openGraph: { title, description, url: "/pricing/" },
  twitter: { title, description },
};

export default function PricingLayout({ children }) {
  return (
    <>
      <JsonLd data={[webPageJsonLd({ path: "/pricing/", name: title, description }), pricingFaqJsonLd()]} />
      {children}
    </>
  );
}
