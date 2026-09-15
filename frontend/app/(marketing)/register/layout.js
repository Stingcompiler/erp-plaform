const title = "ابدأ تجربة شركتك المجانية";
const description =
  "سجّل شركتك في فيزانو: تجربة 14 يومًا بلا بطاقة على السحابة، أو اطلب عرض رخصة دائمة لخادمك الخاص. نراجع الطلب وننشئ مساحة العمل ونرسل للمالك رابط التفعيل.";

export const metadata = {
  title,
  description,
  alternates: { canonical: "/register/" },
  openGraph: { title, description, url: "/register/" },
  twitter: { title, description },
};

export default function RegisterLayout({ children }) {
  return children;
}
