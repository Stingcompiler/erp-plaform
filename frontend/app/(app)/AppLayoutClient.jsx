"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import PlatformShell, { isPlatformPath } from "@/components/PlatformShell";
import { ToastProvider } from "@/components/ui/Toast";
import { SyncProvider } from "@/components/sync/SyncProvider";
import { AttentionProvider } from "@/components/attention/AttentionProvider";
import ForcedPasswordChange from "@/components/auth/ForcedPasswordChange";
import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";

export default function AppLayoutClient({ children }) {
  const { user, loading } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  // On a standalone server there is no platform to operate: a superuser
  // created by the installer is just an administrator of this company's
  // system and gets the normal workspace, not the SaaS operator console.
  const platformOperator = user?.is_platform_admin && user?.deployment_mode !== "standalone";

  useEffect(() => {
    if (!loading && platformOperator && !isPlatformPath(pathname)) {
      router.replace("/platform");
    }
  }, [loading, platformOperator, pathname, router]);

  if (loading || !user) {
    return (
      <div className="grid min-h-screen place-items-center text-muted">
        <div className="animate-pulse font-display">{t("common.loading")}</div>
      </div>
    );
  }

  // A password an administrator handed out opens nothing but this screen;
  // the server enforces the same (accounts.authentication).
  if (user.must_change_password) {
    return <ForcedPasswordChange />;
  }

  if (platformOperator) {
    if (!isPlatformPath(pathname)) {
      return (
        <div className="grid min-h-screen place-items-center text-muted">
          <div className="animate-pulse font-display">{t("common.loading")}</div>
        </div>
      );
    }
    return (
      <ToastProvider>
        <AttentionProvider>
          <PlatformShell>{children}</PlatformShell>
        </AttentionProvider>
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <SyncProvider>
        <AttentionProvider>
          <AppShell>{children}</AppShell>
        </AttentionProvider>
      </SyncProvider>
    </ToastProvider>
  );
}
