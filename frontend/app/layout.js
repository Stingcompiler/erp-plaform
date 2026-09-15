import { Cairo, IBM_Plex_Mono, Inter, Sora, Tajawal } from "next/font/google";

import "./globals.css";
import { AuthProvider } from "./providers/AuthProvider";
import HtmlShell from "@/components/HtmlShell";
import JsonLd from "@/components/seo/JsonLd";
import { organizationJsonLd, softwareApplicationJsonLd } from "@/lib/seo";
import { OG_IMAGE, SITE_NAME, SITE_NAME_LATIN, SITE_URL } from "@/lib/site";

// Latin UI: Inter (body) + Sora (display). Arabic UI: Cairo (body) + Tajawal
// (headings/UI), per the design spec. The CSS variables are swapped onto the
// document by I18nProvider when the language flips, so the right script-specific
// pairing is always active.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const sora = Sora({
  subsets: ["latin"],
  variable: "--font-sora",
  weight: ["500", "600", "700"],
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
  display: "swap",
});
const cairo = Cairo({
  subsets: ["arabic"],
  variable: "--font-cairo",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});
const tajawal = Tajawal({
  subsets: ["arabic"],
  variable: "--font-tajawal",
  weight: ["400", "500", "700"],
  display: "swap",
});

// Site-wide defaults, reached by the routes that have no metadata of their
// own (sign-in, activation, the app — all noindex). The public pages set
// their own title, description, canonical, hreflang and Open Graph through
// lib/marketingMeta.js. The copy is Arabic first because that is the default
// document language and the market the platform sells into.
export const metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} | نظام إدارة المبيعات والمخزون ونقطة البيع للمحلات والموزعين`,
    template: `%s | ${SITE_NAME}`,
  },
  description:
    "فيزانو منصة سحابية لإدارة الأعمال: نقطة بيع تعمل بلا إنترنت، مخزون بالدفعات والصلاحية، دفتر ديون العملاء، فروع متعددة، بالعربية والإنجليزية. تجربة مجانية 14 يومًا بلا بطاقة.",
  keywords: [
    "نظام إدارة المبيعات",
    "نظام مخزون",
    "نقطة بيع بدون إنترنت",
    "برنامج كاشير",
    "نظام ERP عربي",
    "إدارة ديون العملاء",
    "برنامج محاسبة للمحلات",
    "نظام إدارة الفروع",
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
  applicationName: "Vezano",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "Vezano" },
  icons: {
    icon: [
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
    <HtmlShell className={`${inter.variable} ${sora.variable} ${mono.variable} ${cairo.variable} ${tajawal.variable}`}>
      <JsonLd data={[organizationJsonLd(), softwareApplicationJsonLd()]} />
      <AuthProvider>{children}</AuthProvider>
    </HtmlShell>
  );
}
