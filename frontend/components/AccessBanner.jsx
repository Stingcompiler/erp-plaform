"use client";

import { KeyRound, Lock } from "lucide-react";
import Link from "next/link";

import { useAuth } from "../app/providers/AuthProvider";
import { useI18n } from "../app/providers/I18nProvider";

const SOON_DAYS = 30;

// One line at the top of every screen when access is limited or about to
// be: licence in grace, lapsed subscription, release above the licence
// ceiling, or an end date inside 30 days. Silent otherwise. The owner gets
// a link to the page where it is fixed; everyone else just learns why a
// save was refused before they try.
export default function AccessBanner() {
  const { user } = useAuth();
  const { t, language } = useI18n();
  const ent = user?.entitlements;
  if (!ent || ent.state === "active" && ent.allow_writes && !endsSoon(ent.valid_until)) return null;
  if (ent.source === "policy_disabled" || ent.source === "platform") return null;

  const locked = !ent.allow_writes;
  const until = ent.valid_until
    ? new Date(ent.valid_until).toLocaleDateString(language === "ar" ? "ar" : "en", { dateStyle: "medium" })
    : null;
  const key = locked ? `access.locked.${ent.state}` : `access.warn.${ent.state}`;
  const fallback = locked ? "access.locked.generic" : "access.warn.generic";
  const text = pick(t, key, fallback, { date: until });
  const owner = user?.role_name === "Business Owner";
  return (
    <div
      role="alert"
      className={`flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-sm ${
        locked ? "border-danger/40 bg-danger/10 text-ink" : "border-warn/40 bg-warn/10 text-ink"
      }`}
    >
      <span className="inline-flex items-center gap-2">
        {locked ? <Lock size={16} className="text-danger" /> : <KeyRound size={16} className="text-warn" />}
        <span className="font-medium">{text}</span>
        {ent.reason && <span className="text-muted">— {ent.reason}</span>}
      </span>
      {owner && (
        <Link href="/subscription" className="tap inline-flex items-center rounded-control border border-line bg-surface px-3 py-1 text-sm font-medium hover:border-accent">
          {t(ent.source === "standalone" ? "access.manageLicence" : "access.manageSubscription")}
        </Link>
      )}
    </div>
  );
}

function endsSoon(iso) {
  if (!iso) return false;
  const days = (new Date(iso).getTime() - Date.now()) / 86400000;
  return days >= 0 && days <= SOON_DAYS;
}

function pick(t, key, fallback, vars) {
  const value = t(key, vars);
  return value === key ? t(fallback, vars) : value;
}
