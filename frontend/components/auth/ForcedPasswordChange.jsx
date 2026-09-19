"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";

import VezanoMark from "@/components/brand/VezanoMark";
import PasswordInput from "@/components/ui/PasswordInput";
import { Button, Field, controlClass as INPUT_CLASS } from "@/components/ui/kit";
import { auth } from "@/lib/api";
import { useAuth } from "../../app/providers/AuthProvider";
import { useI18n } from "../../app/providers/I18nProvider";

// Shown in place of the workspace while the password in use was set by an
// administrator. The server refuses every other call until it is replaced
// (accounts.authentication), so there is nothing else this screen could
// let the person do — except sign out.
export default function ForcedPasswordChange() {
  const { t } = useI18n();
  const { refresh, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (password !== confirm) return setError(t("ownerActivation.mismatch"));
    setBusy(true);
    try {
      await auth.changePassword(current, password);
      await refresh();
    } catch (err) {
      const data = err?.response?.data || {};
      const first = data.current_password || data.new_password || data.detail;
      setError(Array.isArray(first) ? first.join(" ") : first || t("passwordChange.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-paper p-6">
      <section className="w-full max-w-md rounded-card border border-line bg-surface p-6 shadow-card sm:p-8">
        <div className="mb-7 inline-flex items-center gap-2 font-display text-lg font-bold">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white"><VezanoMark size={21} /></span>
          {t("common.appName")}
        </div>
        <form onSubmit={submit}>
          <KeyRound className="mb-4 text-accent" size={32} />
          <h1 className="font-display text-2xl font-semibold">{t("passwordChange.requiredTitle")}</h1>
          <p className="mt-2 text-sm text-muted">{t("passwordChange.requiredBody")}</p>
          <div className="mt-6 space-y-4">
            <Field label={t("passwordChange.current")}>
              <PasswordInput autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required className={INPUT_CLASS} />
            </Field>
            <Field label={t("passwordChange.new")} hint={t("users.passwordMin")}>
              <PasswordInput autoComplete="new-password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required className={INPUT_CLASS} />
            </Field>
            <Field label={t("ownerActivation.confirmPassword")}>
              <PasswordInput autoComplete="new-password" minLength={10} value={confirm} onChange={(e) => setConfirm(e.target.value)} required className={INPUT_CLASS} />
            </Field>
            {error && <p role="alert" className="rounded-control border border-danger/25 bg-danger/10 p-3 text-sm text-danger">{error}</p>}
            <Button type="submit" className="w-full" disabled={busy || !current || password.length < 10 || confirm.length < 10}>
              {busy ? t("common.saving") : t("passwordChange.submit")}
            </Button>
            <button type="button" onClick={logout} className="block w-full text-center text-sm text-muted hover:text-ink">
              {t("common.signOut")}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
