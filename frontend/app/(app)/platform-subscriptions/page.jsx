"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FileText, Lock, XCircle } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { platformSubscriptions as api } from "@/lib/api";
import { Badge, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";
import PlanChangeRequests from "@/components/subscription/PlanChangeRequests";

const STATES = ["trialing", "active", "grace", "read_only", "suspended", "cancelled"];

function localDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function initialDraft(row) {
  const endField = {
    trialing: "trial_ends_at",
    active: "period_ends_at",
    grace: "grace_ends_at",
  }[row.status];
  return {
    plan_version: String(row.plan_version || ""),
    status: row.status === "legacy" ? "active" : row.status,
    end: localDateTime(endField ? row[endField] : ""),
    cancel_at_period_end: Boolean(row.cancel_at_period_end),
  };
}

function dateInputValue(date = new Date()) {
  return date.toISOString().slice(0, 10);
}

function invoiceDefaultsForSubscription(subscription) {
  const now = new Date();
  const currentEnd = subscription?.period_ends_at ? new Date(subscription.period_ends_at) : null;
  const start = currentEnd && currentEnd > now
    ? new Date(currentEnd.getFullYear(), currentEnd.getMonth(), currentEnd.getDate() + 1)
    : now;
  const end = new Date(start);
  if (subscription?.plan?.billing_cycle === "yearly") end.setFullYear(end.getFullYear() + 1);
  else end.setMonth(end.getMonth() + 1);
  end.setDate(end.getDate() - 1);
  return {
    subscription: subscription ? String(subscription.id) : "",
    amount: subscription?.recurring_amount || subscription?.plan?.price || "",
    period_start: dateInputValue(start),
    period_end: dateInputValue(end),
    due_at: localDateTime(now),
  };
}

export default function PlatformSubscriptionsPage() {
  const { user, can } = useAuth();
  const canView = can("platform.subscriptions.view");
  const canManageSubs = can("platform.subscriptions.manage");
  const canBill = can("platform.billing.review");
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [plans, setPlans] = useState([]);
  const [payments, setPayments] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [paymentDrafts, setPaymentDrafts] = useState({});
  const [invoiceDraft, setInvoiceDraft] = useState({});
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const versions = useMemo(
    () => plans.flatMap((plan) => (plan.versions || []).filter((version) => version.published_at)),
    [plans],
  );

  const canSeePlans = can("platform.plans.view");
  const canSeeBilling = can("platform.billing.view");

  const load = useCallback(async () => {
    setError("");
    try {
      // Plans, payments and invoices are separate areas; a member who may
      // see subscriptions but not money (or not the price list) gets an
      // empty list for those instead of a failed page.
      const empty = { data: [] };
      const [subscriptionsResponse, plansResponse, paymentsResponse, invoicesResponse] =
        await Promise.all([
          api.list(),
          canSeePlans ? api.plans() : empty,
          canSeeBilling ? api.payments() : empty,
          canSeeBilling ? api.invoices() : empty,
        ]);
      const nextRows = subscriptionsResponse.data.results || subscriptionsResponse.data;
      const nextPayments = paymentsResponse.data.results || paymentsResponse.data;
      setRows(nextRows);
      setPlans(plansResponse.data.results || plansResponse.data);
      setPayments(nextPayments.filter((payment) => payment.status === "pending"));
      setInvoices(invoicesResponse.data.results || invoicesResponse.data);
      setDrafts(Object.fromEntries(nextRows.map((row) => [row.id, initialDraft(row)])));
      setPaymentDrafts((current) => Object.fromEntries(nextPayments.map((payment) => [
        payment.id,
        current[payment.id] || { invoice: "", amount: payment.amount },
      ])));
      setInvoiceDraft((current) => current.subscription ? current : invoiceDefaultsForSubscription(nextRows[0]));
    } catch {
      setError(t("subscription.loadError"));
    }
  }, [t, canSeePlans, canSeeBilling]);

  useEffect(() => {
    if (canView) load();
  }, [load, canView]);

  const updateDraft = (id, field, value) => {
    setDrafts((current) => ({
      ...current,
      [id]: { ...current[id], [field]: value, ...(field === "status" ? { end: "" } : {}) },
    }));
  };

  const save = async (row) => {
    const draft = drafts[row.id];
    const endField = {
      trialing: "trial_ends_at",
      active: "period_ends_at",
      grace: "grace_ends_at",
    }[draft.status];
    const body = {
      plan_version: Number(draft.plan_version),
      status: draft.status,
      cancel_at_period_end: Boolean(draft.cancel_at_period_end),
    };
    if (endField && draft.end) body[endField] = new Date(draft.end).toISOString();
    setSaving(row.id);
    setError("");
    setSuccess("");
    try {
      await api.configure(row.id, body);
      setSuccess(t("subscription.configurationSaved"));
      await load();
    } catch (requestError) {
      const data = requestError?.response?.data;
      const first = data && Object.values(data).flat()[0];
      setError(typeof first === "string" ? first : t("subscription.loadError"));
    } finally {
      setSaving(null);
    }
  };

  const verifyPayment = async (payment) => {
    const draft = paymentDrafts[payment.id];
    setSaving(`payment-${payment.id}`);
    setError("");
    setSuccess("");
    try {
      await api.verifyPayment(payment.id, [{
        invoice_id: Number(draft.invoice),
        amount: draft.amount,
      }]);
      setSuccess(t("subscription.paymentVerified"));
      await load();
    } catch (requestError) {
      const data = requestError?.response?.data;
      const first = Array.isArray(data) ? data[0] : data?.detail || (data && Object.values(data).flat()[0]);
      setError(typeof first === "string" ? first : t("subscription.loadError"));
    } finally {
      setSaving(null);
    }
  };

  const rejectPayment = async (payment) => {
    const reason = window.prompt(t("subscription.rejectReasonPrompt"), "");
    if (reason === null || !reason.trim()) return;
    setSaving(`payment-${payment.id}`);
    setError("");
    setSuccess("");
    try {
      await api.rejectPayment(payment.id, reason.trim());
      setSuccess(t("subscription.paymentRejected"));
      await load();
    } catch (requestError) {
      const data = requestError?.response?.data;
      const first = Array.isArray(data) ? data[0] : data?.detail || data?.reason?.[0] || (data && Object.values(data).flat()[0]);
      setError(typeof first === "string" ? first : t("subscription.loadError"));
    } finally {
      setSaving(null);
    }
  };

  const createInvoice = async () => {
    const subscription = rows.find((row) => row.id === Number(invoiceDraft.subscription));
    if (!subscription) return;
    setSaving("invoice");
    setError("");
    setSuccess("");
    try {
      await api.createInvoice({
        company: subscription.company,
        subscription: subscription.id,
        amount: invoiceDraft.amount,
        currency: subscription.plan?.currency || "USD",
        period_start: invoiceDraft.period_start,
        period_end: invoiceDraft.period_end,
        due_at: new Date(invoiceDraft.due_at).toISOString(),
      });
      setSuccess(t("subscription.invoiceIssued"));
      await load();
    } catch (requestError) {
      const data = requestError?.response?.data;
      const first = data?.detail || (data && Object.values(data).flat()[0]);
      setError(typeof first === "string" ? first : t("subscription.loadError"));
    } finally {
      setSaving(null);
    }
  };

  if (!canView) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-8 text-center">
        <Lock className="mx-auto text-muted" />
        <p className="mt-3 text-muted">
          {t("shell.noAccessBody", { module: t("nav.platformSubscriptions") })}
        </p>
      </Card>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("subscription.platformTitle")}
        subtitle={t("subscription.platformSubtitle")}
        actions={
          <Badge tone="accent">
            {t("subscription.activeSubscriptions", { count: rows.length })}
          </Badge>
        }
      />
      {error && <div className="mb-4 rounded-control bg-danger/10 p-3 text-danger">{error}</div>}
      {success && <div className="mb-4 rounded-control bg-ok/10 p-3 text-ok">{success}</div>}
      <PlanChangeRequests canManage={canManageSubs} onChanged={load} />
      {canBill && <Card id="renewal-invoice" className="mb-6 p-5">
        <h2 className="font-display text-xl font-semibold">{t("subscription.createInvoice")}</h2>
        {rows.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("subscription.noSubscriptionsToInvoice")}</p>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <Field label={t("subscription.company")}>
              <Select
                value={invoiceDraft.subscription || ""}
                onChange={(event) => {
                  const subscription = rows.find((row) => row.id === Number(event.target.value));
                  setInvoiceDraft(invoiceDefaultsForSubscription(subscription));
                }}
              >
                {rows.map((row) => <option key={row.id} value={row.id}>{row.company_name}</option>)}
              </Select>
            </Field>
            <Field label={t("subscription.amount")}>
              <Input type="number" min="0" step="0.01" value={invoiceDraft.amount || ""} onChange={(event) => setInvoiceDraft((current) => ({ ...current, amount: event.target.value }))} />
            </Field>
            <Field label={t("subscription.invoicePeriodStart")}>
              <Input type="date" value={invoiceDraft.period_start || ""} onChange={(event) => setInvoiceDraft((current) => ({ ...current, period_start: event.target.value }))} />
            </Field>
            <Field label={t("subscription.invoicePeriodEnd")}>
              <Input type="date" value={invoiceDraft.period_end || ""} onChange={(event) => setInvoiceDraft((current) => ({ ...current, period_end: event.target.value }))} />
            </Field>
            <Field label={t("subscription.invoiceDueAt")}>
              <Input type="datetime-local" value={invoiceDraft.due_at || ""} onChange={(event) => setInvoiceDraft((current) => ({ ...current, due_at: event.target.value }))} />
            </Field>
            <div className="flex items-end"><Button className="w-full" disabled={saving === "invoice" || !invoiceDraft.subscription || !invoiceDraft.amount || !invoiceDraft.period_start || !invoiceDraft.period_end || !invoiceDraft.due_at} onClick={createInvoice}>{t("subscription.createInvoice")}</Button></div>
          </div>
        )}
      </Card>}
      <div className="grid gap-4">
        {rows.map((row) => {
          const draft = drafts[row.id] || initialDraft(row);
          const needsEnd = ["trialing", "active", "grace"].includes(draft.status);
          return (
            <Card key={row.id} className="p-5">
              <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                <div className="min-w-48">
                  <div className="font-display text-lg font-semibold">{row.company_name}</div>
                  {row.company_phone && <PhoneLink phone={row.company_phone} className="text-sm text-muted" />}
                  <div className="mt-1 text-sm text-muted">
                    {row.plan?.plan_name} · {row.plan?.billing_cycle}
                  </div>
                  <Badge tone={row.status === "active" || row.status === "legacy" ? "ok" : "warn"}>
                    {row.status}
                  </Badge>
                  <label className="mt-3 flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={draft.cancel_at_period_end}
                      onChange={(event) => updateDraft(row.id, "cancel_at_period_end", event.target.checked)}
                    />
                    <span>
                      {t("subscription.cancelAtPeriodEnd")}
                      <span className="block text-xs text-muted">{t("subscription.cancelAtPeriodEndHint")}</span>
                    </span>
                  </label>
                </div>
                <div className="grid flex-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <Field label={t("subscription.selectPlan")}>
                    <Select
                      value={draft.plan_version}
                      onChange={(event) => updateDraft(row.id, "plan_version", event.target.value)}
                    >
                      {versions.map((version) => (
                        <option key={version.id} value={version.id}>
                          {version.plan_name} v{version.version} · {version.price} {version.currency}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label={t("subscription.state")}>
                    <Select
                      value={draft.status}
                      onChange={(event) => updateDraft(row.id, "status", event.target.value)}
                    >
                      {STATES.map((state) => <option key={state} value={state}>{t(`platformCompanies.status.${state}`)}</option>)}
                    </Select>
                  </Field>
                  <Field label={t("subscription.endDate")}>
                    <Input
                      type="datetime-local"
                      value={draft.end}
                      disabled={!needsEnd}
                      required={needsEnd}
                      onChange={(event) => updateDraft(row.id, "end", event.target.value)}
                    />
                  </Field>
                  <div className="flex items-end">
                    <Button
                      className="w-full"
                      disabled={!canManageSubs || saving === row.id || !draft.plan_version || (needsEnd && !draft.end)}
                      onClick={() => save(row)}
                    >
                      {t("subscription.configure")}
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
      <h2 className="mb-4 mt-8 font-display text-xl font-semibold">
        {t("subscription.pendingPayments")}
      </h2>
      {payments.length === 0 ? (
        <Card className="p-6 text-sm text-muted">{t("subscription.noPendingPayments")}</Card>
      ) : (
        <div className="grid gap-4">
          {payments.map((payment) => {
            const draft = paymentDrafts[payment.id] || { invoice: "", amount: payment.amount };
            const availableInvoices = invoices.filter(
              (invoice) => invoice.company === payment.company && invoice.status === "issued",
            );
            const subscription = rows.find((row) => row.company === payment.company);
            const planCurrency = subscription?.plan?.currency;
            const wrongCurrency = planCurrency && planCurrency !== payment.currency;
            const issueForCompany = () => {
              if (!subscription) return;
              setInvoiceDraft(invoiceDefaultsForSubscription(subscription));
              document.getElementById("renewal-invoice")?.scrollIntoView({ behavior: "smooth", block: "start" });
            };
            return (
              <Card key={payment.id} className="p-5">
                <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-end">
                  <div>
                    <div className="font-semibold">{payment.company_name}</div>
                    <div className="mt-1 text-sm text-muted">
                      {payment.amount} {payment.currency} · {payment.method}
                    </div>
                    <div className="text-xs text-muted">
                      {t("subscription.submittedBy")}: {payment.recorded_by_name || "—"}
                      {payment.sender_bank_name && <> · {payment.sender_bank_name}</>}
                      {(payment.transfer_reference || payment.reference_last4) && (
                        <> · <span dir="ltr">{payment.transfer_reference || `****${payment.reference_last4}`}</span></>
                      )}
                    </div>
                    {payment.proof_available ? (
                      <a
                        href={api.paymentProofUrl(payment.id)}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex items-center gap-1 text-sm text-accent hover:underline"
                      >
                        <FileText size={14} />{t("subscription.viewProof")}
                      </a>
                    ) : (
                      <div className="mt-2 text-xs text-muted">{t("subscription.noProof")}</div>
                    )}
                  </div>
                  <Field label={t("subscription.invoice")}>
                    <Select
                      value={draft.invoice}
                      onChange={(event) => setPaymentDrafts((current) => ({
                        ...current,
                        [payment.id]: { ...draft, invoice: event.target.value },
                      }))}
                    >
                      <option value="">—</option>
                      {availableInvoices.map((invoice) => (
                        <option key={invoice.id} value={invoice.id}>
                          {invoice.number} · {invoice.amount} {invoice.currency}
                        </option>
                      ))}
                    </Select>
                    {!availableInvoices.length && (
                      <p className="mt-1 text-xs text-warn">
                        {t("subscription.noOpenInvoice")}
                        {canBill && subscription && <> <button type="button" className="font-semibold underline" onClick={issueForCompany}>{t("subscription.issueForCompany")}</button></>}
                      </p>
                    )}
                    {wrongCurrency && (
                      <p className="mt-1 text-xs text-danger">{t("subscription.currencyMismatch", { paid: payment.currency, billed: planCurrency })}</p>
                    )}
                  </Field>
                  <Field label={t("subscription.allocationAmount")}>
                    <Input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={draft.amount}
                      onChange={(event) => setPaymentDrafts((current) => ({
                        ...current,
                        [payment.id]: { ...draft, amount: event.target.value },
                      }))}
                    />
                  </Field>
                  {canBill && <div className="flex flex-col gap-2">
                    <Button
                      disabled={!draft.invoice || !draft.amount || saving === `payment-${payment.id}`}
                      onClick={() => verifyPayment(payment)}
                    >
                      {t("subscription.verifyPayment")}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={saving === `payment-${payment.id}`}
                      onClick={() => rejectPayment(payment)}
                    >
                      <XCircle size={15} />{t("subscription.rejectPayment")}
                    </Button>
                  </div>}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
