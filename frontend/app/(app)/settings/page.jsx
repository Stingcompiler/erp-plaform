"use client";

import { useEffect, useState } from "react";
import { Database, Download, Lock, Printer, RotateCcw, TrendingUp, Upload } from "lucide-react";

import { settings, users } from "@/lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { errorText } from "@/lib/errors";
import { useI18n } from "../../providers/I18nProvider";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";

const bytes = (n) => (n > 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`);

// The zones a Vezano customer is likely in; any IANA name is accepted.
const TIMEZONES = [
  "Africa/Khartoum", "Africa/Cairo", "Africa/Nairobi", "Africa/Addis_Ababa", "Africa/Juba",
  "Asia/Riyadh", "Asia/Dubai", "Asia/Qatar", "Asia/Kuwait", "Asia/Amman", "Europe/London", "UTC",
];

export default function SettingsPage() {
  const { user, canRead, canWrite, refresh, can } = useAuth();
  const { t, language } = useI18n();
  const writable = canWrite("settings");
  const canApprove = can("finance.approve");
  const [profile, setProfile] = useState(null);
  const [company, setCompany] = useState(null);
  const [handlers, setHandlers] = useState([]);
  const [backups, setBackups] = useState([]);
  const [restoring, setRestoring] = useState(false);
  const [restoreMsg, setRestoreMsg] = useState(null);
  const [savingTax, setSavingTax] = useState(false);
  const [savingCompany, setSavingCompany] = useState(false);
  const [companyMsg, setCompanyMsg] = useState("");
  const [backingUp, setBackingUp] = useState(false);
  const [msg, setMsg] = useState("");
  const [storeMode, setStoreMode] = useState(null);
  const [exceptionUsers, setExceptionUsers] = useState([]);
  const [exceptionRoles, setExceptionRoles] = useState([]);
  const [modeUsers, setModeUsers] = useState([]);
  const [modeRoles, setModeRoles] = useState([]);
  const [pendingMode, setPendingMode] = useState(null);
  const [savingMode, setSavingMode] = useState(false);
  const ownerControlsMode = Boolean(user?.can_manage_system_mode);

  // Exchange rate: the company row carries the current rate; the list is the
  // history. Recording goes through /exchange-rates/ so each change is kept.
  const [rates, setRates] = useState([]);
  const [newRate, setNewRate] = useState("");
  const [rateMsg, setRateMsg] = useState("");
  const [savingRate, setSavingRate] = useState(false);
  const loadRates = () =>
    settings.exchangeRates().then((r) => setRates((r.data.results || r.data).slice(0, 8))).catch(() => setRates([]));

  async function recordRate() {
    setRateMsg("");
    setSavingRate(true);
    try {
      await settings.recordExchangeRate({ rate: newRate });
      setNewRate("");
      setRateMsg(t("settings.rateRecorded"));
      const r = await settings.companyProfile();
      setCompany(r.data);
      loadRates();
    } catch (err) {
      setRateMsg(errorText(err, t, "settings.saveFailed"));
    } finally {
      setSavingRate(false);
    }
  }

  const loadBackups = () =>
    settings.backups().then((r) => setBackups(r.data)).catch(() => setBackups([]));

  useEffect(() => {
    if (!canRead("settings")) return;
    settings.taxProfile().then((r) => setProfile(r.data)).catch(() => setProfile(null));
    settings.taxHandlers().then((r) => setHandlers(r.data)).catch(() => setHandlers([]));
    settings.companyProfile().then((r) => setCompany(r.data)).catch(() => setCompany(null));
    loadBackups();
    loadRates();
  }, [canRead]);

  useEffect(() => {
    if (!ownerControlsMode) return;
    settings.storeMode().then((r) => {
      setStoreMode(r.data);
      setExceptionUsers(r.data.additional_user_ids || []);
      setExceptionRoles(r.data.additional_role_ids || []);
    }).catch(() => setStoreMode(null));
    users.list({ page_size: 100 }).then((r) => setModeUsers(r.data.results || r.data || [])).catch(() => setModeUsers([]));
    users.roles().then((r) => setModeRoles(r.data.results || r.data || [])).catch(() => setModeRoles([]));
  }, [ownerControlsMode]);

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
      setMsg(errorText(err, t, "settings.saveFailed"));
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
      const r = await settings.updateCompanyProfile({
        name: company.name,
        legal_name: company.legal_name,
        address: company.address,
        phone: company.phone,
        email: company.email,
        tax_number: company.tax_number,
        registration_number: company.registration_number,
        currency: company.currency,
        timezone: company.timezone,
        reference_currency: company.reference_currency,
        receipt_paper: company.receipt_paper,
        receipt_footer: company.receipt_footer,
        default_payment_terms_days: company.default_payment_terms_days,
        ...(canApprove ? {
          payment_approval_threshold: company.payment_approval_threshold,
          stock_adjustment_approval_threshold: company.stock_adjustment_approval_threshold,
        } : {}),
      });
      setCompany(r.data);
      setCompanyMsg(t("settings.companySaved"));
    } catch (err) {
      setCompanyMsg(errorText(err, t, "settings.saveFailed"));
    } finally {
      setSavingCompany(false);
    }
  }

  async function restore(body) {
    if (!window.confirm(t("settings.restoreConfirm"))) return;
    setRestoring(true);
    setRestoreMsg(null);
    try {
      const r = await settings.restoreBackup(body);
      setRestoreMsg({ ok: true, text: t("settings.restoreDone", { count: r.data.restored }) });
      await loadBackups();
    } catch (err) {
      const data = err?.response?.data;
      setRestoreMsg({ ok: false, text: data?.detail || (Array.isArray(data) ? data.join(" ") : t("settings.restoreFailed")) });
    } finally {
      setRestoring(false);
    }
  }

  async function restoreFromFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      await restore({ data: parsed.data ?? parsed });
    } catch {
      setRestoreMsg({ ok: false, text: t("settings.restoreBadFile") });
    }
  }

  async function makeBackup() {
    setBackingUp(true);
    try {
      const response = await settings.createBackup();
      // The dump only exists in this response unless off-site storage is
      // configured — hand it to the owner as a file, so every manual
      // backup is actually IN their hands, restorable from any install.
      try {
        const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "-");
        const blob = new Blob(
          [JSON.stringify(response.data.data ?? response.data, null, 1)],
          { type: "application/json" },
        );
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `vezano-backup-${stamp}.json`;
        link.click();
        URL.revokeObjectURL(link.href);
      } catch { /* recording succeeded; the download is best-effort */ }
      await loadBackups();
    } finally {
      setBackingUp(false);
    }
  }

  const toggle = (setter, id) => () => setter((current) =>
    current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
  );

  async function saveStoreMode() {
    setSavingMode(true);
    try {
      const [config, profile] = await Promise.all([
        settings.updateStoreMode({
          additional_user_ids: exceptionUsers,
          additional_role_ids: exceptionRoles,
        }),
        settings.updateCompanyProfile({ business_type: pendingMode }),
      ]);
      setStoreMode(config.data);
      setCompany(profile.data);
      setPendingMode(null);
      await refresh?.();
    } catch (err) {
      setCompanyMsg(errorText(err, t, "settings.saveFailed"));
    } finally {
      setSavingMode(false);
    }
  }

  async function saveExceptions() {
    setSavingMode(true);
    try {
      const response = await settings.updateStoreMode({
        additional_user_ids: exceptionUsers,
        additional_role_ids: exceptionRoles,
      });
      setStoreMode(response.data);
      setCompanyMsg(t("settings.storeModeExceptionsSaved"));
    } catch {
      setCompanyMsg(t("settings.saveFailed"));
    } finally {
      setSavingMode(false);
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
            <Field label={t("settings.defaultTerms")} hint={t("settings.defaultTermsHint")}>
              <Input
                type="number" inputMode="numeric" min="0" max="365"
                value={company.default_payment_terms_days ?? ""}
                onChange={setCo("default_payment_terms_days")}
                disabled={!writable}
                className="w-32"
              />
            </Field>
            {canApprove && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("settings.paymentThreshold")} hint={t("settings.paymentThresholdHint")}>
                  <Input type="number" inputMode="decimal" min="0" step="0.01"
                    value={company.payment_approval_threshold ?? ""}
                    onChange={setCo("payment_approval_threshold")} disabled={!writable} />
                </Field>
                <Field label={t("settings.adjustmentThreshold")} hint={t("settings.adjustmentThresholdHint")}>
                  <Input type="number" inputMode="decimal" min="0" step="0.01"
                    value={company.stock_adjustment_approval_threshold ?? ""}
                    onChange={setCo("stock_adjustment_approval_threshold")} disabled={!writable} />
                </Field>
              </div>
            )}
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
              <Field label={t("settings.timezone")} hint={t("settings.timezoneHint")}>
                <Input
                  list="timezone-options"
                  value={company.timezone || ""}
                  onChange={setCo("timezone")}
                  disabled={!writable}
                  dir="ltr"
                />
                <datalist id="timezone-options">
                  {TIMEZONES.map((z) => <option key={z} value={z} />)}
                </datalist>
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

      {company && (
        <Card className="mb-6 p-6">
          <h2 className="mb-1 flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wide text-muted">
            <Printer size={16} /> {t("settings.receiptPrinting")}
          </h2>
          <p className="mb-4 text-sm text-muted">{t("settings.receiptPrintingHint")}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("settings.receiptPaper")}>
              <Select value={company.receipt_paper || "a4"} onChange={setCo("receipt_paper")} disabled={!writable}>
                <option value="a4">{t("settings.receiptPaperA4")}</option>
                <option value="80mm">{t("settings.receiptPaper80")}</option>
                <option value="58mm">{t("settings.receiptPaper58")}</option>
              </Select>
            </Field>
            <Field label={t("settings.receiptFooter")} hint={t("settings.receiptFooterHint")}>
              <Input value={company.receipt_footer || ""} onChange={setCo("receipt_footer")} disabled={!writable} maxLength={240} />
            </Field>
          </div>
          {writable && (
            <Button className="mt-4" onClick={saveCompany} disabled={savingCompany}>
              {savingCompany ? t("common.saving") : t("common.save")}
            </Button>
          )}
        </Card>
      )}

      {company && (
        <Card className="mb-6 p-6">
          <h2 className="mb-1 flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wide text-muted">
            <TrendingUp size={16} /> {t("settings.exchangeRate")}
          </h2>
          <p className="mb-4 text-sm text-muted">{t("settings.exchangeRateHint")}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("settings.referenceCurrency")}>
              <Input
                value={company.reference_currency || ""}
                onChange={setCo("reference_currency")}
                disabled={!writable}
                className="w-32 uppercase"
                maxLength={8}
              />
            </Field>
            <Field label={t("settings.currentRate")}>
              <div className="min-h-10 py-2 text-sm">
                {company.exchange_rate ? (
                  <>
                    <span className="tabular text-lg font-semibold text-ink">
                      {Number(company.exchange_rate).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                    </span>
                    <span className="ms-2 text-muted">
                      {company.currency} / 1 {company.reference_currency}
                      {company.exchange_rate_at && (
                        <> · {t("settings.rateRecordedAt", { when: new Date(company.exchange_rate_at).toLocaleString(language === "ar" ? "ar" : "en") })}</>
                      )}
                    </span>
                  </>
                ) : (
                  <span className="text-muted">{t("settings.noRateYet")}</span>
                )}
              </div>
            </Field>
          </div>
          {canApprove ? (
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <Field label={t("settings.newRate", { local: company.currency, currency: company.reference_currency })}>
                <Input
                  type="number" inputMode="decimal" min="0" step="0.0001"
                  value={newRate} onChange={(e) => setNewRate(e.target.value)} className="w-44"
                />
              </Field>
              <Button onClick={recordRate} disabled={savingRate || !newRate}>
                {savingRate ? t("common.saving") : t("settings.recordRate")}
              </Button>
              {rateMsg && <p className="text-sm text-muted">{rateMsg}</p>}
            </div>
          ) : (
            <p className="mt-4 text-sm text-muted">{t("settings.rateOnlyApprovers")}</p>
          )}
          {rates.length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">{t("settings.rateHistory")}</p>
              <ul className="divide-y divide-line text-sm">
                {rates.map((r) => (
                  <li key={r.id} className="flex items-center justify-between py-1.5">
                    <span className="tabular text-ink">{Number(r.rate).toLocaleString(undefined, { maximumFractionDigits: 4 })} <span className="text-muted">{r.currency}</span></span>
                    <span className="text-muted">
                      {new Date(r.recorded_at).toLocaleString(language === "ar" ? "ar" : "en")}
                      {r.recorded_by_name ? ` · ${r.recorded_by_name}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {ownerControlsMode && (
        <Card className="mb-6 p-6">
          <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-muted">{t("settings.systemMode")}</h2>
          <p className="mt-1 text-sm text-muted">{t("settings.systemModeHint")}</p>
          {!storeMode ? <p className="mt-4 text-sm text-muted">{t("common.loading")}</p> : <>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <button onClick={() => setPendingMode("shop")} className={`rounded-control border p-4 text-start ${company?.business_type === "shop" ? "border-accent bg-accent/5" : "border-line hover:border-accent/50"}`}><div className="font-semibold">{t("settings.typeShop")}</div><p className="mt-1 text-xs text-muted">{t("settings.shopModeEffect")}</p></button>
              <button onClick={() => setPendingMode("enterprise")} className={`rounded-control border p-4 text-start ${company?.business_type === "enterprise" ? "border-accent bg-accent/5" : "border-line hover:border-accent/50"}`}><div className="font-semibold">{t("settings.typeEnterprise")}</div><p className="mt-1 text-xs text-muted">{t("settings.companyModeEffect")}</p></button>
            </div>
            <div className="mt-6 border-t border-line pt-5">
              <h3 className="font-semibold text-ink">{t("settings.additionalRequirements")}</h3>
              <p className="mt-1 text-sm text-muted">{t("settings.additionalRequirementsHint")}</p>
              <div className="mt-4 grid gap-5 lg:grid-cols-2">
                <div><p className="mb-2 text-sm font-medium">{t("settings.allowedRoles")}</p><div className="max-h-48 space-y-2 overflow-y-auto rounded-control border border-line p-3">{modeRoles.map((role) => <label key={role.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={exceptionRoles.includes(role.id)} onChange={toggle(setExceptionRoles, role.id)} />{role.name}</label>)}</div></div>
                <div><p className="mb-2 text-sm font-medium">{t("settings.allowedUsers")}</p><div className="max-h-48 space-y-2 overflow-y-auto rounded-control border border-line p-3">{modeUsers.map((modeUser) => <label key={modeUser.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={exceptionUsers.includes(modeUser.id)} onChange={toggle(setExceptionUsers, modeUser.id)} />{modeUser.full_name || modeUser.email}<span className="text-xs text-muted">{modeUser.role_name}</span></label>)}</div></div>
              </div>
              <Button className="mt-4" variant="outline" onClick={saveExceptions} disabled={savingMode}>{savingMode ? t("common.saving") : t("settings.saveAdditionalRequirements")}</Button>
            </div>
          </>}
        </Card>
      )}

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

      {pendingMode && <div className="fixed inset-0 z-50 grid place-items-center bg-ink/50 p-4"><Card className="w-full max-w-lg p-6"><h2 className="font-display text-xl font-bold">{pendingMode === "shop" ? t("settings.confirmShopModeTitle") : t("settings.confirmCompanyModeTitle")}</h2><p className="mt-3 text-sm leading-6 text-muted">{pendingMode === "shop" ? t("settings.confirmShopModeBody") : t("settings.confirmCompanyModeBody")}</p><div className="mt-6 flex justify-end gap-2"><Button variant="ghost" onClick={() => setPendingMode(null)}>{t("common.cancel")}</Button><Button onClick={saveStoreMode} disabled={savingMode}>{savingMode ? t("common.saving") : pendingMode === "shop" ? t("settings.activateShopMode") : t("settings.activateCompanyMode")}</Button></div></Card></div>}

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
                  {b.downloadable && (
                    <a
                      href={settings.backupDownloadUrl(b.id)}
                      download
                      className="inline-flex items-center gap-1 rounded-control border border-line px-2 py-1 text-xs text-ink hover:bg-paper"
                      title={t("settings.downloadBackup")}
                    >
                      <Download size={13} />{t("settings.downloadBackup")}
                    </a>
                  )}
                  {b.downloadable && writable && b.kind !== "restore" && (
                    <button
                      type="button"
                      onClick={() => restore({ backup_id: b.id })}
                      disabled={restoring}
                      className="inline-flex items-center gap-1 rounded-control border border-line px-2 py-1 text-xs text-ink hover:bg-paper disabled:opacity-50"
                      title={t("settings.restoreThis")}
                    >
                      <RotateCcw size={13} />{t("settings.restoreThis")}
                    </button>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-muted">{t("settings.backupsNote")}</p>
        {writable && (
          <div className="mt-4 rounded-control border border-line bg-paper p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-ink">{t("settings.restoreTitle")}</div>
                <p className="mt-0.5 text-xs text-muted">{t("settings.restoreHint")}</p>
              </div>
              <label className={`inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-control border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink shadow-sm hover:bg-paper ${restoring ? "pointer-events-none opacity-50" : ""}`}>
                <Upload size={15} />{restoring ? t("settings.restoring") : t("settings.restoreFromFile")}
                <input type="file" accept="application/json,.json" className="hidden" onChange={restoreFromFile} disabled={restoring} />
              </label>
            </div>
            {restoreMsg && (
              <p role="alert" className={`mt-3 text-sm ${restoreMsg.ok ? "text-ok" : "text-danger"}`}>{restoreMsg.text}</p>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
