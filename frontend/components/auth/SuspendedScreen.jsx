"use client";

import { useEffect } from "react";
import { LogOut, PauseCircle } from "lucide-react";

import LogoMark from "@/components/brand/LogoMark";
import Wordmark from "@/components/brand/Wordmark";
import { useOptionalSync } from "@/components/sync/SyncProvider";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";

// Shown in place of the workspace while the platform has suspended the
// company until it pays (core.company_access). The owner gets the notice and
// the subscription page (`children`: next renewal, invoices, record a
// payment) — nothing else works server-side either. Anyone else still signed
// in gets the refusal; their device keeps uploading what it captured before
// the suspension (the sync provider stays mounted around this screen).
export default function SuspendedScreen({ access, children }) {
  const { t, language } = useI18n();
  const { logout, refresh } = useAuth();
  // Once the platform approves the payment the suspension is lifted; look
  // again every two minutes so the workspace comes back by itself.
  useEffect(() => {
    const timer = setInterval(() => refresh(), 120000);
    return () => clearInterval(timer);
  }, [refresh]);
  const sync = useOptionalSync();
  const pending = sync?.pending || 0;
  const since = access?.since
    ? new Date(access.since).toLocaleDateString(language === "ar" ? "ar" : "en", { dateStyle: "medium" })
    : null;
  const owner = Boolean(access?.is_owner);

  return (
    <div className="min-h-screen bg-paper">
      <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2 font-display font-semibold">
          <LogoMark size={28} decorative />
          <Wordmark />
        </div>
        <button
          type="button"
          onClick={logout}
          className="inline-flex min-h-10 items-center gap-2 rounded-control border border-line px-3 text-sm hover:bg-paper"
        >
          <LogOut size={16} />{t("companyAccess.signOut")}
        </button>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <section role="alert" className="mb-6 rounded-card border border-danger/30 bg-danger/10 p-5">
          <div className="flex items-start gap-3">
            <PauseCircle className="mt-0.5 shrink-0 text-danger" />
            <div className="min-w-0">
              <h1 className="font-display text-xl font-semibold text-ink">
                {t(owner ? "companyAccess.suspendedTitle" : "companyAccess.staffTitle")}
              </h1>
              <p className="mt-2 text-sm text-ink">
                {t(owner ? "companyAccess.suspendedOwnerBody" : "companyAccess.staffBody")}
              </p>
              {access?.reason && (
                <p className="mt-3 text-sm">
                  <span className="font-semibold">{t("companyAccess.reasonLabel")}:</span> {access.reason}
                </p>
              )}
              {since && <p className="mt-1 text-xs text-muted">{t("companyAccess.since", { date: since })}</p>}
              {pending > 0 && <p className="mt-2 text-xs text-muted">{t("companyAccess.pendingSync", { n: pending })}</p>}
            </div>
          </div>
        </section>
        {owner && children}
      </main>
    </div>
  );
}
