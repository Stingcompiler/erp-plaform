"use client";

import { useEffect, useState } from "react";
import { Download, Smartphone, X } from "lucide-react";

import { installRoute } from "@/lib/installRoute";
import { useInstallPrompt } from "@/lib/installPrompt";
import { useI18n } from "../../app/providers/I18nProvider";

const DISMISS_KEY = "vezano.installCard.dismissed";

/**
 * "Install Vezano" offer shown before sign-in, so a new till sees it the
 * moment the link is opened rather than after finding the sync drawer.
 *
 * What it shows depends on the browser, because installation is the
 * browser's feature, not ours:
 *   - Chromium (Chrome, Edge, Android): a real button once the browser has
 *     fired `beforeinstallprompt`. That happens only after the service
 *     worker is active, typically a second or two after first load.
 *   - Safari / Firefox for Android: the one-line manual route.
 *   - Desktop Firefox: nothing — it cannot install web apps, and a card
 *     that says so on every visit would just be noise on the login screen.
 * Hidden when already running installed, and after the user closes it.
 */
export default function InstallCard({ className = "" }) {
  const { canPrompt, installed, prompt } = useInstallPrompt();
  const { t } = useI18n();
  const [route, setRoute] = useState(null);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    setRoute(installRoute());
    try {
      setDismissed(window.localStorage.getItem(DISMISS_KEY) === "1");
    } catch {
      setDismissed(false);
    }
  }, []);

  if (route === null || installed || dismissed) return null;
  const manual = !canPrompt && (route === "safari-ios" || route === "safari-mac" || route === "firefox-android");
  if (!canPrompt && !manual) return null;

  const dismiss = () => {
    setDismissed(true);
    try { window.localStorage.setItem(DISMISS_KEY, "1"); } catch { /* ignore */ }
  };

  return (
    <div
      role="region"
      aria-label={t("install.cardTitle")}
      className={`flex items-start gap-3 rounded-card border border-line bg-surface p-3 text-sm shadow-card ${className}`}
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-accent/15 text-accent">
        <Smartphone size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink">{t("install.cardTitle")}</p>
        <p className="mt-0.5 text-muted">
          {canPrompt ? t("install.cardBody") : t(`install.route.${route}`)}
        </p>
        {canPrompt && (
          <button
            type="button"
            onClick={() => prompt()}
            className="mt-2 inline-flex items-center gap-1.5 rounded-control bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-strong"
          >
            <Download size={14} /> {t("install.button")}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("common.close")}
        className="shrink-0 rounded-control p-1 text-muted hover:bg-paper hover:text-ink"
      >
        <X size={16} />
      </button>
    </div>
  );
}
