"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import PlatformShell, { isPlatformPath } from "@/components/PlatformShell";
import { ToastProvider } from "@/components/ui/Toast";
import { SyncProvider } from "@/components/sync/SyncProvider";
import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";

export default function AppLayout({ children }) {
  const { user, loading } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!loading && user?.is_platform_admin && !isPlatformPath(pathname)) {
      router.replace("/platform");
    }
  }, [loading, user, pathname, router]);

  if (loading || !user) {
    return (
      <div className="grid min-h-screen place-items-center text-muted">
        <div className="animate-pulse font-display">{t("common.loading")}</div>
      </div>
    );
  }

  if (user.is_platform_admin) {
    if (!isPlatformPath(pathname)) {
      return (
        <div className="grid min-h-screen place-items-center text-muted">
          <div className="animate-pulse font-display">{t("common.loading")}</div>
        </div>
      );
    }
    return (
      <ToastProvider>
        <PlatformShell>{children}</PlatformShell>
      </ToastProvider>
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
