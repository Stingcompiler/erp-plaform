"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import { ToastProvider } from "@/components/ui/Toast";
import { SyncProvider } from "@/components/sync/SyncProvider";
import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";

export default function AppLayout({ children }) {
  const { user, loading } = useAuth();
  const { t } = useI18n();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="grid min-h-screen place-items-center text-muted">
        <div className="animate-pulse font-display">{t("common.loading")}</div>
      </div>
    );
  }

  return (
    <ToastProvider>
      <SyncProvider>
        <AppShell>{children}</AppShell>
      </SyncProvider>
    </ToastProvider>
  );
}
