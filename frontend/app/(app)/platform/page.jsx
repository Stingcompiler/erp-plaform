"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CreditCard, Inbox, Lock, ShieldCheck } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformLeads, platformSubscriptions } from "@/lib/api";
import { Badge, Card, PageHeader } from "@/components/ui/kit";

export default function PlatformPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const [counts, setCounts] = useState({ leads: null, subscriptions: null, payments: null });

  useEffect(() => {
    if (!user?.is_platform_admin) return;
    Promise.all([platformLeads.list(), platformSubscriptions.list(), platformSubscriptions.payments()])
      .then(([leads, subscriptions, payments]) => setCounts({
        leads: leads.data.count ?? leads.data.length,
        subscriptions: subscriptions.data.count ?? subscriptions.data.length,
        payments: (payments.data.results || payments.data).filter((row) => row.status === "pending").length,
      }))
      .catch(() => setCounts({ leads: "—", subscriptions: "—", payments: "—" }));
  }, [user?.is_platform_admin]);

  if (!user?.is_platform_admin) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">
          {t("shell.noAccessBody", { module: t("nav.platform") })}
        </p>
      </Card>
    );
  }

  return (
    <div>
      <PageHeader title={t("platform.title")} subtitle={t("platform.subtitle")} actions={<Badge tone="accent"><ShieldCheck size={14} /> {t("shell.platformOperator")}</Badge>} />
      <div className="grid gap-5 md:grid-cols-2">
        <Link href="/platform-leads">
          <Card className="h-full p-6 transition-transform hover:-translate-y-0.5">
            <Inbox className="text-accent" />
            <div className="mt-5 text-3xl font-bold tabular-nums">{counts.leads ?? "…"}</div>
            <h2 className="mt-2 font-display text-lg font-semibold">{t("nav.platformLeads")}</h2>
            <p className="mt-1 text-sm text-muted">{t("platform.leadsDescription")}</p>
          </Card>
        </Link>
        <Link href="/platform-subscriptions">
          <Card className="h-full p-6 transition-transform hover:-translate-y-0.5">
            <CreditCard className="text-accent" />
            <div className="mt-5 flex items-end gap-3">
              <span className="text-3xl font-bold tabular-nums">{counts.subscriptions ?? "…"}</span>
              <Badge tone={Number(counts.payments) > 0 ? "warn" : "muted"}>{t("platform.pendingPayments", { count: counts.payments ?? "…" })}</Badge>
            </div>
            <h2 className="mt-2 font-display text-lg font-semibold">{t("nav.platformSubscriptions")}</h2>
            <p className="mt-1 text-sm text-muted">{t("platform.subscriptionsDescription")}</p>
          </Card>
        </Link>
      </div>
    </div>
  );
}
