import { NOINDEX } from "@/lib/site";

// Sign-in is not a landing page: keep it out of search results so the brand
// query lands on the marketing pages instead.
export const metadata = { title: "تسجيل الدخول", robots: NOINDEX };

export default function LoginLayout({ children }) {
  return children;
}
