"use client";

import { useEffect, useState } from "react";
import { Database, Lock } from "lucide-react";

import { settings } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";

const bytes = (n) => (n > 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`);

export default function SettingsPage() {
  const { canRead, canWrite } = useAuth();
  const { t, language } = useI18n();
  const writable = canWrite("settings");
  const [profile, setProfile] = useState(null);
  const [company, setCompany] = useState(null);
  const [handlers, setHandlers] = useState([]);
  const [backups, setBackups] = useState([]);
  const [savingTax, setSavingTax] = useState(false);
  const [savingCompany, setSavingCompany] = useState(false);
  const [companyMsg, setCompanyMsg] = useState("");
  const [backingUp, setBackingUp] = useState(false);
  const [msg, setMsg] = useState("");

  const loadBackups = () =>
    settings.backups().then((r) => setBackups(r.data)).catch(() => setBackups([]));

  useEffect(() => {
    if (!canRead("settings")) return;
    settings.taxProfile().then((r) => setProfile(r.data)).catch(() => setProfile(null));
    settings.taxHandlers().then((r) => setHandlers(r.data)).catch(() => setHandlers([]));
    settings.companyProfile().then((r) => setCompany(r.data)).catch(() => setCompany(null));
    loadBackups();
  }, [canRead]);

  if (!canRead("settings")) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-card border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <h1 className="mt-3 font-display text-xl font-semibold">{t("shell.noAccessTitle")}</h1>
        <p className="mt-1 text-muted">{t("settings.noAccess")}</p>
      </div>
    );
  }

  const set = (key) => (e) =>
    setProfile((p) => ({
      ...p,
      [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    }));

  async function saveTax() {
    setMsg("");
    setSavingTax(true);
    try {
      const r = await settings.updateTaxProfile({
        country: profile.country,
        invoice_format: profile.invoice_format,
        flat_tax_rate: profile.flat_tax_rate,
        e_invoicing_enabled: profile.e_invoicing_enabled,
      });
      setProfile(r.data);
      setMsg(t("settings.taxSaved"));
    } catch (err) {
      const data = err?.response?.data;
      setMsg(typeof data === "object" && data ? Object.values(data).flat().join(" ") : t("settings.saveFailed"));
    } finally {
      setSavingTax(false);
    }
  }

  const setCo = (key) => (e) =>
    setCompany((c) => ({ ...c, [key]: e.target.value }));

  async function saveCompany() {
    setCompanyMsg("");
    setSavingCompany(true);
    try {
      const r = await settings.updateCompanyProfile(company);
      setCompany(r.data);
      setCompanyMsg(t("settings.companySaved"));
    } catch (err) {
      const data = err?.response?.data;
      setCompanyMsg(
        typeof data === "object" && data
          ? Object.values(data).flat().join(" ")
          : t("settings.saveFailed"),
      );
    } finally {
      setSavingCompany(false);
    }
  }

  async function makeBackup() {
    setBackingUp(true);
    try {
      await settings.createBackup();
      await loadBackups();
    } finally {
      setBackingUp(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title={t("settings.title")} subtitle={t("settings.subtitle")} />

      {/* Issuer identity — printed at the top of every document. */}
      <Card className="mb-6 p-6">
        <h2 className="mb-1 font-display text-sm font-semibold uppercase tracking-wide text-muted">
          {t("settings.companyProfile")}
        </h2>
        <p className="mb-4 text-sm text-muted">{t("settings.companyProfileHint")}</p>
        {!company ? (
          <p className="text-muted">{t("common.loading")}</p>
        ) : (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("settings.companyName")}>
                <Input value={company.name || ""} onChange={setCo("name")} disabled={!writable} />
              </Field>
              <Field label={t("settings.legalName")} hint={t("settings.legalNameHint")}>
                <Input
                  value={company.legal_name || ""}
                  onChange={setCo("legal_name")}
                  disabled={!writable}
                />
              </Field>
            </div>
            <Field label={t("settings.address")}>
              <Input
                value={company.address || ""}
                onChange={setCo("address")}
                disabled={!writable}
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("settings.phone")}>
                <Input value={company.phone || ""} onChange={setCo("phone")} disabled={!writable} />
              </Field>
              <Field label={t("settings.email")}>
                <Input
                  type="email"
                  value={company.email || ""}
                  onChange={setCo("email")}
                  disabled={!writable}
                />
              </Field>
            </div>
            <Field
              label={t("settings.businessType")}
              hint={t("settings.businessTypeHint")}
            >
              <Select
                value={company.business_type || "enterprise"}
                onChange={setCo("business_type")}
                disabled={!writable}
              >
                <option value="shop">{t("settings.typeShop")}</option>
                <option value="enterprise">{t("settings.typeEnterprise")}</option>
              </Select>
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("doc.taxNumber")} hint={t("settings.taxNumberHint")}>
                <Input
                  value={company.tax_number || ""}
                  onChange={setCo("tax_number")}
                  disabled={!writable}
                />
              </Field>
              <Field label={t("doc.registrationNumber")}>
                <Input
                  value={company.registration_number || ""}
                  onChange={setCo("registration_number")}
                  disabled={!writable}
                />
              </Field>
            </div>
            {companyMsg && <p className="text-sm text-muted">{companyMsg}</p>}
            {writable && (
              <Button onClick={saveCompany} disabled={savingCompany}>
                {savingCompany ? t("common.saving") : t("common.save")}
              </Button>
            )}
          </div>
        )}
      </Card>

      {/* Tax profile */}
      <Card className="p-6">
        <h2 className="mb-4 font-display text-sm font-semibold uppercase tracking-wide text-muted">
          {t("settings.taxInvoicing")}
        </h2>
        {!profile ? (
          <p className="text-muted">{t("common.loading")}</p>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("settings.country")}>
                <Input value={profile.country || ""} onChange={set("country")} disabled={!writable} />
              </Field>
              <Field label={t("settings.flatTaxRate")}>
                <Input
                  type="number"
                  value={profile.flat_tax_rate ?? ""}
                  onChange={set("flat_tax_rate")}
                  disabled={!writable}
                />
              </Field>
            </div>
            <Field label={t("settings.invoiceFormat")} hint={t("settings.invoiceFormatHint")}>
              <Select value={profile.invoice_format} onChange={set("invoice_format")} disabled={!writable}>
                {handlers.map((h) => (
                  <option key={h.code} value={h.code}>
                    {h.label}
                  </option>
                ))}
              </Select>
            </Field>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={Boolean(profile.e_invoicing_enabled)}
                onChange={set("e_invoicing_enabled")}
                disabled={!writable}
              />
              {t("settings.eInvoicingLabel")}
            </label>
            {msg && <p className="text-sm text-muted">{msg}</p>}
            {writable && (
              <Button onClick={saveTax} disabled={savingTax}>
                {savingTax ? t("common.saving") : t("settings.saveTaxProfile")}
              </Button>
            )}
          </div>
        )}
      </Card>

      {/* Backups */}
      <Card className="mt-6 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">
            {t("settings.backups")}
          </h2>
          {writable && (
            <Button variant="outline" onClick={makeBackup} disabled={backingUp}>
              <Database size={15} />
              {backingUp ? t("settings.backingUp") : t("settings.backUpNow")}
            </Button>
          )}
        </div>
        {backups.length === 0 ? (
          <p className="text-sm text-muted">{t("settings.noBackups")}</p>
        ) : (
          <div className="divide-y divide-line">
            {backups.slice(0, 8).map((b) => (
              <div key={b.id} className="flex items-center justify-between py-2 text-sm">
                <div className="flex items-center gap-2">
                  <Badge tone={b.status === "success" ? "ok" : "danger"}>{b.kind}</Badge>
                  <span className="tabular text-muted">
                    {new Date(b.created_at).toLocaleString(language === "ar" ? "ar" : "en")}
                  </span>
                </div>
                <span className="flex items-center gap-2 tabular text-muted">
                  {b.storage_key && <Badge tone="accent">{t("settings.offSite")}</Badge>}
                  {b.record_count} {t("settings.records")} · {bytes(b.size_bytes)}
                </span>
              </div>
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-muted">{t("settings.backupsNote")}</p>
      </Card>
    </div>
  );
}
