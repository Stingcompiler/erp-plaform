"use client";

// The whole app's strings (lib/i18n.js) for the workspace and the other
// app routes: sign-in, owner activation, password reset. See
// components/i18n/PublicCatalog.jsx for the public pages.
import { I18nCatalog } from "@/app/providers/I18nProvider";
import { CATALOG } from "@/lib/i18n";

export default function AppCatalog({ children }) {
  return <I18nCatalog catalog={CATALOG}>{children}</I18nCatalog>;
}
