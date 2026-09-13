"use client";

import { useCallback, useEffect, useState } from "react";
import { CreditCard, KeyRound, Lock } from "lucide-react";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { subscription as subscriptionApi } from "@/lib/api";
import { Badge, Button, Card, Input, PageHeader, Select } from "@/components/ui/kit";

const showDate = (value, language) => value ? new Date(value).toLocaleDateString(language === "ar" ? "ar" : "en") : "—";

export default function SubscriptionPage() {
  const { user } = useAuth();
  const { t, language } = useI18n();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [licenseText, setLicenseText] = useState("");
  const [payment, setPayment] = useState({ amount: "", currency: "USD", method: "bank_transfer", reference_last4: "", proof: null });

  const load = useCallback(async () => {
    try {
      const deployment = await subscriptionApi.deployment();
      const response = deployment.data.mode === "standalone" ? await subscriptionApi.license() : await subscriptionApi.company();
      setData(response.data);
    } catch { setError(t("subscription.loadError")); }
  }, [t]);
  useEffect(() => { if (user?.role_name === "Business Owner") load(); }, [load, user?.role_name]);

  const importLicense = async () => {
    setError(""); setNotice("");
    try {
      await subscriptionApi.importLicense(JSON.parse(licenseText));
      setNotice(t("subscription.licenseImported")); setLicenseText(""); await load();
    } catch { setError(t("subscription.invalidLicenseFile")); }
  };
  const submitPayment = async (event) => {
    event.preventDefault(); setError(""); setNotice("");
    try {
      const body = new FormData();
      Object.entries(payment).forEach(([key, value]) => {
        if (value !== null && value !== "") body.append(key, value);
      });
      await subscriptionApi.submitPayment(body);
      setNotice(t("subscription.paymentSent"));
      setPayment((current) => ({ ...current, amount: "", reference_last4: "", proof: null })); await load();
    } catch { setError(t("subscription.loadError")); }
  };

  if (user?.role_name !== "Business Owner") return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted"/><p className="mt-3 text-muted">{t("subscription.ownerOnly")}</p></Card>;
  if (!data && !error) return <Card className="p-8 text-center text-muted">{t("common.loading")}</Card>;

  const standalone = data?.deployment_mode === "standalone";
  const record = standalone ? data?.license : data?.subscription;
  const entitlements = data?.entitlements || {};
  const planName = standalone ? record?.organisation_name : record?.plan?.plan_name;
  return <div>
    <PageHeader title={t("subscription.title")} subtitle={t("subscription.subtitle")} />
    {error && <div role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</div>}
    {notice && <div role="status" className="mb-4 rounded-control bg-ok/10 p-3 text-sm text-ok">{notice}</div>}
    {data && <>
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5"><div className="flex items-center gap-2 text-muted">{standalone ? <KeyRound size={18}/> : <CreditCard size={18}/>} {t("subscription.deployment")}</div><div className="mt-3 font-display text-xl font-semibold">{t(standalone ? "subscription.standalone" : "subscription.saas")}</div></Card>
        <Card className="p-5"><div className="text-sm text-muted">{t("subscription.plan")}</div><div className="mt-3 font-display text-xl font-semibold">{planName || t("subscription.legacy")}</div></Card>
        <Card className="p-5"><div className="text-sm text-muted">{t("subscription.state")}</div><div className="mt-3"><Badge tone={entitlements.allow_writes ? "ok" : "warn"}>{entitlements.state}</Badge></div></Card>
      </div>
      {!standalone && record && <Card className="mt-5 p-5"><div className="grid gap-4 sm:grid-cols-3">{[["periodEnd", record.period_ends_at], ["trialEnd", record.trial_ends_at], ["graceEnd", record.grace_ends_at]].map(([key, value]) => <div key={key}><div className="text-xs text-muted">{t(`subscription.${key}`)}</div><div className="mt-1">{showDate(value, language)}</div></div>)}</div></Card>}
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card className="p-5"><h2 className="font-display font-semibold">{t("subscription.modules")}</h2><div className="mt-3 flex flex-wrap gap-2">{(entitlements.modules || []).map((item) => <Badge key={item} tone="accent">{item}</Badge>)}</div></Card>
        <Card className="p-5"><h2 className="font-display font-semibold">{t("subscription.limits")}</h2><div className="mt-3 space-y-2">{Object.entries(entitlements.limits || {}).map(([key, value]) => <div key={key} className="flex justify-between border-b border-line py-2"><span>{key}</span><span className="tabular font-semibold">{value}</span></div>)}</div></Card>
      </div>
      {standalone ? <Card className="mt-5 p-5"><h2 className="font-display font-semibold">{t("subscription.importLicense")}</h2><textarea className="mt-3 min-h-40 w-full rounded-control border border-line bg-surface p-3 font-mono text-xs" value={licenseText} onChange={(event) => setLicenseText(event.target.value)} placeholder={t("subscription.licenseFile")}/><Button className="mt-3" onClick={importLicense} disabled={!licenseText.trim()}>{t("subscription.importLicense")}</Button></Card> : <>
        <Card className="mt-5 p-5"><h2 className="font-display font-semibold">{t("subscription.invoices")}</h2>{data.invoices?.length ? <div className="mt-3 divide-y divide-line">{data.invoices.map((row) => <div key={row.id} className="flex flex-wrap justify-between gap-3 py-3"><span>{row.number}</span><span className="tabular">{row.amount} {row.currency}</span><Badge>{row.status}</Badge></div>)}</div> : <p className="mt-3 text-sm text-muted">{t("subscription.noInvoices")}</p>}</Card>
        <Card className="mt-5 p-5"><h2 className="font-display font-semibold">{t("subscription.payments")}</h2><form onSubmit={submitPayment} className="mt-3 grid gap-3 sm:grid-cols-4"><Input required type="number" min="0.01" step="0.01" placeholder={t("subscription.amount")} value={payment.amount} onChange={(event) => setPayment({...payment, amount: event.target.value})}/><Input required placeholder={t("subscription.currency")} value={payment.currency} onChange={(event) => setPayment({...payment, currency: event.target.value.toUpperCase()})}/><Select value={payment.method} onChange={(event) => setPayment({...payment, method: event.target.value})}><option value="bank_transfer">{t("common.bankTransfer")}</option><option value="cash">{t("common.cash")}</option></Select><Input required={payment.method === "bank_transfer"} maxLength={4} placeholder={t("subscription.reference")} value={payment.reference_last4} onChange={(event) => setPayment({...payment, reference_last4: event.target.value})}/><label className="sm:col-span-4 text-sm text-muted">{t("subscription.proof")}<Input className="mt-1" type="file" accept="image/*,.pdf" onChange={(event) => setPayment({...payment, proof: event.target.files?.[0] || null})}/></label><Button type="submit" className="sm:col-span-4 sm:justify-self-start">{t("subscription.submitPayment")}</Button></form>{data.payments?.length > 0 && <div className="mt-4 divide-y divide-line">{data.payments.map((row) => <div key={row.id} className="flex justify-between py-2 text-sm"><span>{row.amount} {row.currency}</span><Badge>{row.status}</Badge></div>)}</div>}</Card>
        <Card className="mt-5 p-5"><h2 className="font-display font-semibold">{t("subscription.events")}</h2>{data.events?.length ? <div className="mt-3 divide-y divide-line">{data.events.map((row) => <div key={row.id} className="py-3 text-sm"><span>{row.event_type}</span><span className="ms-3 text-muted">{showDate(row.created_at, language)}</span></div>)}</div> : <p className="mt-3 text-sm text-muted">{t("subscription.noEvents")}</p>}</Card>
      </>}
    </>}
  </div>;
}
