"use client";

import { useState } from "react";
import { Building2, Store } from "lucide-react";

import { settings } from "@/lib/api";
import { useI18n } from "../app/providers/I18nProvider";
import { Button } from "@/components/ui/kit";

/**
 * The one-time question that decides how much of the app a tenant sees.
 *
 * Shop mode existed before this and nothing ever offered it: the field
 * defaulted to `enterprise`, so a corner grocery landed in the full
 * seventeen-page layout and would only have discovered the simpler one by
 * opening a settings form it had no reason to open. A feature nobody is
 * offered is a feature nobody has.
 *
 * Deliberately not dismissable. Skipping would leave the company in the
 * default it never chose — exactly the state this exists to end — and the
 * choice costs one click and is reversible from Settings at any time.
 *
 * Only shown to someone who can act on it (settings write); everyone else
 * works normally while the owner decides.
 */
function Choice({ icon: Icon, title, blurb, points, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`flex-1 rounded-card border p-4 text-start transition-colors ${
        selected
          ? "border-accent bg-accent/5"
          : "border-line bg-surface hover:bg-paper"
      }`}
    >
      <div className="flex items-center gap-2">
        <Icon size={18} className={selected ? "text-accent" : "text-muted"} />
        <span className="font-display font-semibold text-ink">{title}</span>
      </div>
      <p className="mt-1 text-sm text-muted">{blurb}</p>
      <ul className="mt-2 space-y-0.5 text-xs text-muted">
        {points.map((p) => (
          <li key={p}>· {p}</li>
        ))}
      </ul>
    </button>
  );
}

export default function SetupPrompt({ onDone }) {
  const { t } = useI18n();
  const [choice, setChoice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    if (!choice) return;
    setBusy(true);
    setError("");
    try {
      await settings.updateCompanyProfile({ business_type: choice });
      onDone?.(choice);
    } catch {
      setError(t("setup.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <div className="w-full max-w-2xl rounded-card border border-line bg-surface p-6 shadow-xl">
        <h2 className="font-display text-xl font-bold text-ink">
          {t("setup.title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("setup.subtitle")}</p>

        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <Choice
            icon={Store}
            title={t("setup.shopTitle")}
            blurb={t("setup.shopBlurb")}
            points={[
              t("setup.shopPoint1"),
              t("setup.shopPoint2"),
              t("setup.shopPoint3"),
            ]}
            selected={choice === "shop"}
            onSelect={() => setChoice("shop")}
          />
          <Choice
            icon={Building2}
            title={t("setup.enterpriseTitle")}
            blurb={t("setup.enterpriseBlurb")}
            points={[
              t("setup.enterprisePoint1"),
              t("setup.enterprisePoint2"),
              t("setup.enterprisePoint3"),
            ]}
            selected={choice === "enterprise"}
            onSelect={() => setChoice("enterprise")}
          />
        </div>

        <p className="mt-4 text-xs text-muted">{t("setup.reversible")}</p>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}

        <div className="mt-5 flex justify-end">
          <Button onClick={save} disabled={!choice || busy}>
            {busy ? t("common.saving") : t("setup.confirm")}
          </Button>
        </div>
      </div>
    </div>
  );
}
