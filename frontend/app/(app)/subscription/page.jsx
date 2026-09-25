"use client";

import { useCallback, useEffect, useState } from "react";
import { CreditCard, KeyRound, Lock } from "lucide-react";
import { useAuth } from "../../providers/AuthProvider";
import { errorText } from "@/lib/errors";
import { useI18n } from "../../providers/I18nProvider";
import { subscription as subscriptionApi } from "@/lib/api";
import { Badge, Button, Card, Input, PageHeader, Select } from "@/components/ui/kit";
import UsageMeter from "@/components/subscription/UsageMeter";
import DeviceList from "@/components/subscription/DeviceList";
import PlanChangePanel from "@/components/subscription/PlanChangePanel";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { currencyLabel, formatAmount, formatMoney } from "@/lib/money";
import { subscriptionStateLabel } from "@/lib/labels";
import { moduleLabel } from "@/lib/planModules";

// Digits in day/month/year order, Latin numerals: an Arabic-locale date
// inside an LTR span was bidi-reordered to "202026/9/".
const showDate = (value) => {
  if (!value) return "—";
  // A calendar day (an invoice period) is not a moment: parsing it as UTC
  // midnight would show the day before west of Greenwich.
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (day) return `${day[3]}/${day[2]}/${day[1]}`;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
};

// A subscription event as a sentence, not the code the server stores.
// Status codes and invoice numbers are the details a user can act on.
function EventRow({ row, t }) {
  const label = t(`subscription.eventTypes.${row.event_type}`);
  const details = [];
  if (row.from_status && row.to_status && row.from_status !== row.to_status) {
    details.push(<span key="status" dir="ltr">{row.from_status} → {row.to_status}</span>);
  }
  if (row.metadata?.invoice_number) details.push(t("subscription.eventInvoice", { number: row.metadata.invoice_number }));
  if (row.actor_name) details.push(t("subscription.eventBy", { name: row.actor_name }));
  if (row.reason) details.push(row.reason);
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 text-sm">
      <div>
        <span className="text-ink">{label.startsWith("subscription.") ? row.event_type.replace(/_/g, " ") : label}</span>
        {details.length > 0 && (
          <span className="ms-2 text-muted">
            {details.map((d, i) => <span key={i}>· {d} </span>)}
          </span>
        )}
      </div>
      <span className="tabular shrink-0 text-muted" dir="ltr">{showDate(row.created_at)}</span>
    </div>
  );
}

export default function SubscriptionPage() {
  const { user } = useAuth();
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [licenseText, setLicenseText] = useState("");
  const [payment, setPayment] = useState({ amount: "", currency: "", method: "bank_transfer", transfer_reference: "", proof: null });
  const [devices, setDevices] = useState(null);
  const [deviceBusy, setDeviceBusy] = useState(null);

  const loadDevices = useCallback(async () => {
    try { const res = await subscriptionApi.devices(); setDevices(res.data); } catch { /* standalone or not owner */ }
  }, []);
  const deviceAction = async (fn, id) => {
    setDeviceBusy(id); setError("");
    try { await fn(); await loadDevices(); await load(); }
    catch (err) {
      const d = err?.response?.data;
      setError(d?.code === "plan_limit_reached"
        ? t("devices.noRoom", { limit: d.limit })
        : errorText(err, t, "subscription.loadError"));
    }
    finally { setDeviceBusy(null); }
  };

  const load = useCallback(async () => {
    try {
      const deployment = await subscriptionApi.deployment();
      const response = deployment.data.mode === "standalone" ? await subscriptionApi.license() : await subscriptionApi.company();
      setData(response.data);
    } catch { setError(t("subscription.loadError")); }
  }, [t]);
  useEffect(() => { if (user?.role_name === "Business Owner") { load(); loadDevices(); } }, [load, loadDevices, user?.role_name]);

  const importLicense = async () => {
    setError(""); setNotice("");
    let envelope;
    try { envelope = JSON.parse(licenseText); } catch { setError(t("subscription.invalidLicenseFile")); return; }
    try {
      await subscriptionApi.importLicense(envelope);
      setNotice(t("subscription.licenseImported")); setLicenseText(""); await load();
    } catch (requestError) {
      setError(errorText(requestError, t, "subscription.invalidLicenseFile"));
    }
  };
  // A licence arrives as a file from the vendor; reading it here avoids a
  // copy-paste that can silently truncate the signature.
  const readLicenseFile = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setLicenseText(String(reader.result || ""));
    reader.readAsText(file);
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
      setPayment((current) => ({ ...current, amount: "", transfer_reference: "", proof: null })); await load();
    } catch (requestError) { setError(errorText(requestError, t, "subscription.paymentError")); }
  };

  // The plan's currency plus any open invoice's: a plan change into another
  // currency is invoiced in that currency before the plan switches. Computed
  // before the early returns because the effect below is a hook.
  const planCurrency = (data?.deployment_mode === "standalone" ? data?.license : data?.subscription)?.plan?.currency;
  const payableCurrencies = Array.from(new Set([
    planCurrency,
    ...(data?.invoices || []).filter((i) => i.status === "issued").map((i) => i.currency),
  ].filter(Boolean)));
  const payableKey = payableCurrencies.join(",");
  useEffect(() => {
    if (payableCurrencies.length && !payableCurrencies.includes(payment.currency)) {
      setPayment((p) => ({ ...p, currency: payableCurrencies[0] }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payableKey]);
  // What the next renewal costs is what most owners pay; start from it.
  const renewalAmount = data?.subscription?.next_renewal?.amount;
  useEffect(() => {
    if (renewalAmount && Number(renewalAmount) > 0) {
      setPayment((p) => (p.amount ? p : { ...p, amount: renewalAmount }));
    }
  }, [renewalAmount]);

  if (user?.role_name !== "Business Owner") return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted"/><p className="mt-3 text-muted">{t("subscription.ownerOnly")}</p></Card>;
  if (!data && !error) return <SkeletonCard />;

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
        <Card className="p-5"><div className="text-sm text-muted">{t("subscription.state")}</div><div className="mt-3"><Badge tone={entitlements.allow_writes ? "ok" : "warn"}>{subscriptionStateLabel(t, entitlements.state)}</Badge></div></Card>
      </div>
      {standalone && <Card className="mt-5 p-5">
        <h2 className="font-display font-semibold">{t("subscription.licenceDetails")}</h2>
        {record ? (
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["licenceKind", t(`subscription.kind.${record.kind}`)],
              ["licenceUsableUntil", record.usable_until ? showDate(record.usable_until) : t("subscription.perpetualNoEnd")],
              ["licenceGraceUntil", record.grace_until ? showDate(record.grace_until) : "—"],
              ["licenceMaintenanceUntil", record.maintenance_until ? showDate(record.maintenance_until) : "—"],
              ["licenceMaxVersion", record.max_application_version || t("subscription.anyVersion")],
              ["licenceActivatedAt", showDate(record.activated_at)],
              ["licenceId", record.license_id],
              ["licenceKeyId", record.key_id],
            ].map(([key, value]) => <div key={key}><div className="text-xs text-muted">{t(`subscription.${key}`)}</div><div className="mt-1 break-all text-sm">{value}</div></div>)}
          </div>
        ) : <p className="mt-3 text-sm text-warn">{t("subscription.noLicence")}</p>}
        {entitlements.reason && <p className="mt-3 rounded-control bg-warn/10 p-3 text-sm text-ink">{entitlements.reason}</p>}
        {data.installation && <div className="mt-4 border-t border-line pt-3 text-xs text-muted">
          <div>{t("subscription.installationId")}: <code className="select-all">{data.installation.installation_id}</code></div>
          <div className="mt-1">{t("subscription.installationHint")}</div>
          {data.installation.application_version && <div className="mt-1">{t("subscription.appVersion")}: {data.installation.application_version}</div>}
        </div>}
      </Card>}
      {!standalone && record && <Card className="mt-5 p-5"><div className="grid gap-4 sm:grid-cols-3">{[["periodEnd", record.period_ends_at], ["trialEnd", record.trial_ends_at], ["graceEnd", record.grace_ends_at]].map(([key, value]) => <div key={key}><div className="text-xs text-muted">{t(`subscription.${key}`)}</div><div className="mt-1">{showDate(value)}</div></div>)}</div></Card>}
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card className="p-5"><h2 className="font-display font-semibold">{t("subscription.modules")}</h2><div className="mt-3 flex flex-wrap gap-2">{(entitlements.modules || []).map((item) => <Badge key={item} tone="accent">{moduleLabel(item, t)}</Badge>)}</div></Card>
        <Card className="p-5"><h2 className="font-display font-semibold">{t("subscription.limits")}</h2><p className="mt-1 text-sm text-muted">{t("usage.hint")}</p><div className="mt-4"><UsageMeter usage={data.usage} /></div></Card>
      </div>
      {!standalone && <PlanChangePanel onChanged={load} />}
      {!standalone && <Card className="mt-5 p-5">
        <h2 className="font-display font-semibold">{t("devices.title")}</h2>
        <p className="mt-1 text-sm text-muted">{t("devices.hint")}</p>
        <div className="mt-4">
          <DeviceList
            devices={devices?.devices}
            busyId={deviceBusy}
            onLabel={(id, label) => deviceAction(() => subscriptionApi.labelDevice(id, label), id)}
            onRevoke={async (d) => { if ((await confirm(t("devices.confirmRevoke", { name: d.label || d.device_id }), { tone: "danger" }))) deviceAction(() => subscriptionApi.revokeDevice(d.id), d.id); }}
            onReactivate={(d) => deviceAction(() => subscriptionApi.reactivateDevice(d.id), d.id)}
            onRemove={async (d) => { if ((await confirm(t("devices.confirmRemove", { name: d.label || d.device_id }), { tone: "danger" }))) deviceAction(() => subscriptionApi.removeDevice(d.id), d.id); }}
          />
        </div>
      </Card>}
      {standalone ? <Card className="mt-5 p-5"><h2 className="font-display font-semibold">{t("subscription.importLicense")}</h2><label className="mt-3 block text-sm text-muted">{t("subscription.licenceUpload")}<Input className="mt-1" type="file" accept=".json,application/json" onChange={(event) => readLicenseFile(event.target.files?.[0])}/></label><textarea className="mt-3 min-h-40 w-full rounded-control border border-line bg-surface p-3 font-mono text-xs" value={licenseText} onChange={(event) => setLicenseText(event.target.value)} placeholder={t("subscription.licenseFile")}/><Button className="mt-3" onClick={importLicense} disabled={!licenseText.trim()}>{t("subscription.importLicense")}</Button></Card> : <>
        {record?.next_renewal && <Card className="mt-5 p-5">
          <h2 className="font-display font-semibold">{t("subscription.nextRenewal")}</h2>
          <p className="mt-2 text-sm">{t("subscription.nextRenewalBody", {
            amount: record.next_renewal.amount, currency: record.next_renewal.currency,
            start: showDate(record.next_renewal.period_start), end: showDate(record.next_renewal.period_end),
          })}</p>
          {Number(record.next_renewal.open_balance) > 0 && (
            <p className="mt-2 rounded-control bg-warn/10 p-3 text-sm text-ink">
              {t("subscription.openBalance", { amount: record.next_renewal.open_balance, currency: record.next_renewal.currency })}
            </p>
          )}
        </Card>}
        <Card className="mt-5 p-5">
          <h2 className="font-display font-semibold">{t("subscription.invoices")}</h2>
          {data.invoices?.length ? <div className="mt-3 divide-y divide-line">{data.invoices.map((row) => (
            <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
              <div>
                <div>{row.number}</div>
                <div className="text-xs text-muted">{t("subscription.invoicePeriod", { start: showDate(row.period_start), end: showDate(row.period_end) })}</div>
              </div>
              <div className="text-end">
                <div className="tabular">{formatMoney(row.amount, { currency: row.currency, language })}</div>
                {row.status === "issued" && Number(row.allocated_amount) > 0 && (
                  <div className="text-xs text-warn">{t("subscription.invoicePaidOf", { paid: formatAmount(row.allocated_amount), amount: formatAmount(row.amount), currency: currencyLabel(row.currency, language) })}</div>
                )}
              </div>
              <Badge tone={row.status === "paid" ? "ok" : row.status === "issued" ? "warn" : "muted"}>{t(`subscription.invoiceStatus.${row.status}`)}</Badge>
            </div>
          ))}</div> : <p className="mt-3 text-sm text-muted">{t("subscription.noInvoices")}</p>}
        </Card>
        <Card className="mt-5 p-5">
          <h2 className="font-display font-semibold">{t("subscription.payments")}</h2>
          <form onSubmit={submitPayment} className="mt-3 grid gap-3 sm:grid-cols-4">
            <Input required type="number" min="0.01" step="0.01" dir="ltr" placeholder={t("subscription.amount")} value={payment.amount} onChange={(event) => setPayment({...payment, amount: event.target.value})}/>
            <Select required value={payment.currency} onChange={(event) => setPayment({...payment, currency: event.target.value})}>{payableCurrencies.map((c) => <option key={c} value={c}>{c}</option>)}</Select>
            <Select value={payment.method} onChange={(event) => setPayment({...payment, method: event.target.value})}><option value="bank_transfer">{t("common.bankTransfer")}</option><option value="cash">{t("common.cash")}</option></Select>
            <Input required={payment.method === "bank_transfer"} maxLength={64} dir="ltr" placeholder={t("subscription.reference")} value={payment.transfer_reference} onChange={(event) => setPayment({...payment, transfer_reference: event.target.value})}/>
            {planCurrency && <p className="sm:col-span-4 text-xs text-muted">{t("subscription.billedIn", { currency: planCurrency })}</p>}
            <label className="sm:col-span-4 text-sm text-muted">{t("subscription.proof")}<Input className="mt-1" type="file" accept="image/*,.pdf" onChange={(event) => setPayment({...payment, proof: event.target.files?.[0] || null})}/></label>
            <Button type="submit" className="sm:col-span-4 sm:justify-self-start">{t("subscription.submitPayment")}</Button>
          </form>
          {data.payments?.length > 0 && <div className="mt-4 divide-y divide-line">{data.payments.map((row) => (
            <div key={row.id} className="py-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="tabular">{formatMoney(row.amount, { currency: row.currency, language })} · {showDate(row.created_at)}</span>
                <Badge tone={row.status === "verified" ? "ok" : row.status === "rejected" ? "danger" : "warn"}>{t(`subscription.paymentStatus.${row.status}`)}</Badge>
              </div>
              {row.status === "rejected" && row.rejection_reason && <div className="mt-1 text-xs text-danger">{row.rejection_reason}</div>}
              {(row.allocations || []).map((line) => (
                <div key={line.invoice} className="mt-1 text-xs text-muted">
                  {t("subscription.paymentPaidFor", { invoice: line.invoice_number, start: showDate(line.period_start), end: showDate(line.period_end) })}
                  {line.invoice_status === "issued" && <> · {t("subscription.paymentPartialNote", { paid: line.amount, amount: line.invoice_amount })}</>}
                </div>
              ))}
            </div>
          ))}</div>}
        </Card>
        <Card className="mt-5 p-5"><h2 className="font-display font-semibold">{t("subscription.events")}</h2>{data.events?.length ? <div className="mt-3 divide-y divide-line">{data.events.map((row) => <EventRow key={row.id} row={row} t={t} />)}</div> : <p className="mt-3 text-sm text-muted">{t("subscription.noEvents")}</p>}</Card>
      </>}
    </>}
  </div>;
}
