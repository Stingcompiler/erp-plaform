import { Cairo, IBM_Plex_Mono, Inter, Sora, Tajawal } from "next/font/google";

import "./globals.css";
import { I18nProvider } from "./providers/I18nProvider";
import { AuthProvider } from "./providers/AuthProvider";

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

export const metadata = {
  title: "VEZANO | Business Management Platform",
  description: "Run your business. Simply.",
};

export default function RootLayout({ children }) {
  return (
    <html
      lang="ar"
      dir="rtl"
      suppressHydrationWarning
      className={`${inter.variable} ${sora.variable} ${mono.variable} ${cairo.variable} ${tajawal.variable}`}
    >
      <body>
        <I18nProvider>
          <AuthProvider>{children}</AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
