import "./globals.css";
import { AuthProvider } from "./providers/AuthProvider";
import HtmlShell from "@/components/HtmlShell";
import { fontVariables } from "./fonts/fonts";
import JsonLd from "@/components/seo/JsonLd";
import { organizationJsonLd, softwareApplicationJsonLd } from "@/lib/seo";
import { OG_IMAGE, SITE_NAME, SITE_NAME_LATIN, SITE_URL } from "@/lib/site";

// Fonts are self-hosted (app/fonts/fonts.js). Latin UI: Inter (body) + Sora
// (display). Arabic UI: Tajawal for body and headings — the same face the
// public company pages (/s/<slug>/) load. Readex Pro is the wordmark's face
// only. The CSS variables are swapped by [dir="rtl"] in globals.css when the
// language flips, so the right script-specific pairing is always active.

// Site-wide defaults, reached by the routes that have no metadata of their
// own (sign-in, activation, the app — all noindex). The public pages set
// their own title, description, canonical, hreflang and Open Graph through
// lib/marketingMeta.js. The copy is Arabic first because that is the default
// document language and the market the platform sells into.
export const metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} | نظام إدارة متكامل للمتاجر والشركات بفرع أو عدة فروع — يعمل بلا إنترنت`,
    template: `%s | ${SITE_NAME}`,
  },
  description:
    "فيزانو برو نظام واحد يدير متجرك أو شركتك بكل فروعها: نقطة البيع والمخزون والمشتريات والعملاء والموظفون والرواتب والإدارة المالية والتقارير، بصلاحيات لكل دور وفرع، والبيع يستمر حين تنقطع الشبكة. بالعربية والإنجليزية. تجربة مجانية 14 يومًا بلا بطاقة، وتفعيل في نفس اليوم بعد المراجعة.",
  keywords: [
    "نظام إدارة المبيعات",
    "نظام مخزون",
    "نقطة بيع بدون إنترنت",
    "برنامج كاشير",
    "نظام ERP عربي",
    "إدارة ديون العملاء",
    "نظام إدارة الفروع",
    "نظام موارد بشرية ورواتب",
    "إدارة مالية وموازنات",
    "Vezano Pro",
    "فيزانو برو",
    "Vezano",
    "ERP",
    "POS",
    "offline point of sale",
    "inventory management",
  ],
  openGraph: {
    type: "website",
    siteName: SITE_NAME_LATIN,
    locale: "ar_AR",
    alternateLocale: ["en_US"],
    images: [OG_IMAGE],
  },
  twitter: { card: "summary_large_image", images: [OG_IMAGE.url] },
  robots: { index: true, follow: true },
  category: "business",
  // Installable app: the manifest is what lets a browser offer "install",
  // and an installed app is what gets durable storage for queued sales
  // (see lib/installPrompt.js).
  manifest: "/manifest.webmanifest",
  applicationName: SITE_NAME_LATIN,
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: SITE_NAME_LATIN },
  icons: {
    // Tab-sized icons use the small variant of the mark (scripts/brand-icons.mjs).
    icon: [
      { url: "/favicon.ico", sizes: "16x16 32x32" },
      { url: "/icons/favicon.svg", type: "image/svg+xml" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: "/icons/apple-touch-icon.png",
  },
};

export const viewport = {
  themeColor: "#0f1d2c",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }) {
  return (
    <HtmlShell className={fontVariables}>
      <JsonLd data={[organizationJsonLd(), softwareApplicationJsonLd()]} />
      <AuthProvider>{children}</AuthProvider>
    </HtmlShell>
  );
}
