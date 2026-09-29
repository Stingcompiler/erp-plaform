"use client";

// The public marketing pages' strings (lib/publicI18n.js) for everything
// under app/(marketing). A client module on purpose: the catalog is bundled
// with these pages' JavaScript instead of being serialized into every HTML
// page as a server component prop.
import { I18nCatalog } from "@/app/providers/I18nProvider";
import { PUBLIC_CATALOG } from "@/lib/publicI18n";

export default function PublicCatalog({ children }) {
  return <I18nCatalog catalog={PUBLIC_CATALOG}>{children}</I18nCatalog>;
}
