import { NOINDEX } from "@/lib/site";

// A search box over people's own orders and requests: nothing to rank, so it
// stays out of search results and out of the sitemap (it is deliberately not
// in lib/marketingMeta's COPY, which feeds app/sitemap.js).
export const metadata = {
  title: "تتبّع طلبك",
  description: "تابع طلبك من أي متجر على فيزانو، أو طلب التسجيل أو العرض التجريبي أو دفعة الاشتراك، برقم الطلب أو الهاتف أو البريد أو الاسم.",
  robots: NOINDEX,
};

export default function TrackLayout({ children }) {
  return children;
}
