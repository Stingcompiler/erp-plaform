"use client";

import { usePathname } from "next/navigation";

import { I18nProvider } from "@/app/providers/I18nProvider";
import { DEFAULT_LANGUAGE, dirFor } from "@/lib/i18n";
import { marketingLanguage } from "@/lib/locale";

// The <html> element, rendered on the client side of the root layout so its
// lang/dir can follow the URL: /en/... is exported as lang="en" dir="ltr",
// everything else as Arabic. A server layout has no access to the pathname
// in a static export, and a crawler only sees the exported attributes (the
// provider's later setAttribute is invisible to it). Inside the app the
// provider still switches the attributes to the stored preference on mount.
export default function HtmlShell({ className, children }) {
  const pathname = usePathname();
  const language = marketingLanguage(pathname) ?? DEFAULT_LANGUAGE;
  return (
    <html lang={language} dir={dirFor(language)} suppressHydrationWarning className={className}>
      <body>
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
