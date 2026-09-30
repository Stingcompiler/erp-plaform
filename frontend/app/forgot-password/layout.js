import AppCatalog from "@/components/i18n/AppCatalog";
import { NOINDEX } from "@/lib/site";

export const metadata = { title: "استعادة كلمة المرور", robots: NOINDEX };

export default function ForgotPasswordLayout({ children }) {
  return <AppCatalog>{children}</AppCatalog>;
}
