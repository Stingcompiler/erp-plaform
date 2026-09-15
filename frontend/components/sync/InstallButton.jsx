"use client";

import { Download } from "lucide-react";

import { useInstallPrompt } from "@/lib/installPrompt";
import { useI18n } from "../../app/providers/I18nProvider";

// Sidebar entry offering to install the app. Only rendered when the browser
// has actually offered a prompt (Chromium) and the app is not already
// running installed; other browsers keep their own install menu and the
// sync drawer explains that route.
export default function InstallButton() {
  const { canPrompt, prompt } = useInstallPrompt();
  const { t } = useI18n();
  if (!canPrompt) return null;
  return (
    <button
      type="button"
      onClick={() => prompt()}
      className="mx-3 mb-1 flex w-[calc(100%-1.5rem)] items-center gap-2 rounded-control bg-accent/20 px-3 py-2 text-xs text-sidebarText hover:bg-accent/30"
    >
      <Download size={14} className="shrink-0" />
      <span className="min-w-0 flex-1 truncate text-start">{t("install.button")}</span>
    </button>
  );
}
