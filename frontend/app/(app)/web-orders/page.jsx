"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Globe, Lock, MessageCircle, Truck, Store, Landmark, FileText, ShieldAlert } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { useAttention } from "@/components/attention/AttentionProvider";
import { webOrders as api, inventory as inventoryApi } from "@/lib/api";
import { whatsappUrl } from "@/lib/phone";
import { Badge, Button, Card, Input, PageHeader } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";
import Drawer from "@/components/ui/Drawer";
import PushPrompt from "@/components/orders/PushPrompt";
import { errorText } from "@/lib/errors";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { SkeletonTableRows } from "@/components/ui/Skeleton";
import { EmptyTableRow } from "@/components/ui/EmptyState";

const TABS = ["new", "confirmed", "rejected", "all"];
const TONE = { new: "warn", confirmed: "ok", rejected: "danger", cancelled: "muted" };
const PAY_TONE = { verifying: "warn", confirmed: "ok", rejected: "danger", fraud: "danger" };
const payState = (r) => (r.payments || []).reduce((best, p) => {
  const rank = { confirmed: 3, verifying: 2, fraud: 1, rejected: 0 };
  return best == null || rank[p.status] > rank[best] ? p.status : best;
}, null);

function money(v, c) {
  return `${Number(v || 0).toLocaleString("en", { maximumFractionDigits: 2 })} ${c}`;
}

function WebOrders() {
  const { canRead, canWrite } = useAuth();
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const { markSeen } = useAttention();
  const params = useSearchParams();
  const [tab, setTab] = useState("new");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [warehouses, setWarehouses] = useState([]);
  const [warehouse, setWarehouse] = useState("");
  const [payNote, setPayNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.list(tab === "all" ? {} : { status: tab });
      setRows(res.data.results || res.data);
    } catch (err) {
      setRows([]);
      setError(errorText(err, t, "webOrders.loadError"));
    } finally { setLoading(false); }
  }, [tab, t]);
  useEffect(() => { if (canRead("sales")) load(); }, [canRead, load]);
  useEffect(() => { markSeen?.("web-orders"); }, [markSeen]);
  useEffect(() => { inventoryApi.warehouses().then((r) => setWarehouses((r.data.results || r.data).filter((w) => w.is_active !== false))).catch(() => {}); }, []);

  // Arriving from the notification email: open that order.
  useEffect(() => {
    const ref = params.get("ref");
    if (!ref) return;
    api.list({ ref }).then((res) => {
      const found = (res.data.results || res.data)[0];
      if (found) { setOpen(found); if (found.status !== "new") setTab("all"); }
    }).catch(() => {});
  }, [params]);

  const fmt = (v) => v ? new Date(v).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }) : "—";
  const decide = async (fn) => {
    setBusy(true); setError("");
    try { const res = await fn(open.id, note); setOpen(res.data); setNote(""); await load(); }
    catch (err) { setError(errorText(err, t, "webOrders.decideError")); }
    finally { setBusy(false); }
  };
  const decidePayment = async (claim, kind) => {
    const labels = { confirm: "webOrders.pay.confirmAsk", reject: "webOrders.pay.rejectAsk", fraud: "webOrders.pay.fraudAsk" };
    if (!(await confirm(t(labels[kind], { amount: money(claim.amount, open.currency), last4: claim.reference_last4 })))) return;
    setBusy(true); setError("");
    try {
      const res = kind === "confirm"
        ? await api.confirmPayment(open.id, claim.id, { note: payNote, warehouse: warehouse || undefined })
        : kind === "reject" ? await api.rejectPayment(open.id, claim.id, payNote) : await api.fraudPayment(open.id, claim.id, payNote);
      setOpen(res.data); setPayNote(""); await load();
    } catch (err) {
      const d = err?.response?.data;
      setError(d?.code === "approval_required" ? t("webOrders.pay.approvalRequired") : errorText(err, t, "webOrders.decideError"));
    } finally { setBusy(false); }
  };
  const customerMessage = (order, kind) => {
    const name = order.contact_name;
    const map = {
      confirmed: language === "ar" ? `مرحباً ${name}، تأكّد طلبك رقم ${order.reference} وسنجهّزه.` : `Hello ${name}, your order ${order.reference} is confirmed and being prepared.`,
      rejected: language === "ar" ? `مرحباً ${name}، نعتذر، لم نتمكن من تنفيذ طلبك رقم ${order.reference}.${order.decision_note ? ` السبب: ${order.decision_note}` : ""}` : `Hello ${name}, sorry, we could not fulfil order ${order.reference}.${order.decision_note ? ` Reason: ${order.decision_note}` : ""}`,
      new: language === "ar" ? `مرحباً ${name}، بخصوص طلبك رقم ${order.reference} من موقعنا:` : `Hello ${name}, about your order ${order.reference} from our page:`,
      paid: language === "ar" ? `مرحباً ${name}، وصل تحويلك لطلب ${order.reference} وسنجهّزه للتسليم.` : `Hello ${name}, your transfer for order ${order.reference} arrived; we are preparing it.`,
      payRejected: language === "ar" ? `مرحباً ${name}، لم نجد التحويل المسجّل لطلب ${order.reference}. راجع البيانات وسجّله مجددًا.` : `Hello ${name}, we could not find the transfer declared for order ${order.reference}. Please check and declare it again.`,
    };
    const pay = payState(order);
    if (pay === "confirmed") return map.paid;
    if (pay === "rejected") return map.payRejected;
    return map[kind] || map.new;
  };

  const counts = useMemo(() => rows.length, [rows]);
  if (!canRead("sales")) return <Card className="mx-auto mt-16 max-w-md p-8 text-center"><Lock className="mx-auto text-muted" /><p className="mt-3 text-muted">{t("webOrders.noAccess")}</p></Card>;
  const writable = canWrite("sales");

  return (
    <div>
      <PageHeader title={t("webOrders.title")} subtitle={t("webOrders.subtitle")} actions={<Link href="/website" className="text-sm text-accent hover:underline">{t("webOrders.settingsLink")}</Link>} />
      <PushPrompt />
      <div className="mb-4 flex flex-wrap gap-2">
        {TABS.map((key) => <Button key={key} variant={tab === key ? "primary" : "outline"} onClick={() => setTab(key)}>{t(`webOrders.tab.${key}`)}</Button>)}
        <span className="ms-auto self-center text-sm text-muted">{t("webOrders.count", { n: counts })}</span>
      </div>
      {error && <div role="alert" className="mb-4 rounded-control bg-danger/10 p-3 text-sm text-danger">{error}</div>}
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-muted">
            <tr><th className="px-4 py-3 text-start">{t("webOrders.reference")}</th><th className="px-3 py-3 text-start">{t("webOrders.customer")}</th><th className="px-3 py-3 text-start">{t("webOrders.branch")}</th><th className="px-3 py-3 text-start">{t("webOrders.items")}</th><th className="px-3 py-3 text-end">{t("webOrders.total")}</th><th className="px-3 py-3 text-start">{t("webOrders.received")}</th><th className="px-3 py-3 text-start">{t("common.status")}</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {loading && <SkeletonTableRows cols={7} />}
            {!loading && !rows.length && (
              <EmptyTableRow
                cols={7}
                icon={Globe}
                title={tab === "new" ? t("webOrders.emptyNewTitle") : t("webOrders.empty")}
                body={tab === "new" || tab === "all" ? t("webOrders.emptyBody") : ""}
                action={(tab === "new" || tab === "all") && <Link href="/website/" className="tap inline-flex min-h-10 items-center gap-2 rounded-control border border-line bg-surface px-4 text-sm font-semibold text-ink hover:bg-paper"><Globe size={16} /> {t("webOrders.openWebsite")}</Link>}
              />
            )}
            {!loading && rows.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-paper" onClick={() => setOpen(r)}>
                <td className="px-4 py-3 font-mono font-semibold">{r.reference}</td>
                <td className="px-3 py-3"><div>{r.contact_name}</div><div className="text-xs text-muted" dir="ltr">{r.phone}</div></td>
                <td className="px-3 py-3">{r.branch_name || "—"}</td>
                <td className="px-3 py-3 text-muted">{r.lines.map((l) => `${l.name} ×${Number(l.quantity)}`).join("، ")}</td>
                <td className="px-3 py-3 text-end tabular">{r.total == null ? <span className="text-muted">{t("webOrders.askPrice")}</span> : money(r.total, r.currency)}</td>
                <td className="px-3 py-3 text-muted">{fmt(r.created_at)}</td>
                <td className="px-3 py-3"><Badge tone={TONE[r.status]}>{t(`webOrders.status.${r.status}`)}</Badge> {payState(r) && <Badge tone={PAY_TONE[payState(r)]}>{t(`webOrders.pay.status.${payState(r)}`)}</Badge>} {r.delivery_mode === "delivery" ? <Truck size={14} className="inline text-muted" /> : <Store size={14} className="inline text-muted" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Drawer open={Boolean(open)} onClose={() => { setOpen(null); setNote(""); }} title={open ? `${t("webOrders.order")} ${open.reference}` : ""}>
        {open && (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap items-center gap-2"><Badge tone={TONE[open.status]}>{t(`webOrders.status.${open.status}`)}</Badge><span className="text-muted">{fmt(open.created_at)}</span>{open.branch_name && <Badge tone="muted">{open.branch_name}</Badge>}</div>
            <div className="rounded-control border border-line p-3">
              <div className="font-medium">{open.contact_name}</div>
              <div className="mt-1"><PhoneLink phone={open.phone} /></div>
              <div className="mt-2 text-muted">{open.delivery_mode === "delivery" ? <><Truck size={14} className="inline" /> {t("webOrders.delivery")}: {open.address}</> : <><Store size={14} className="inline" /> {t("webOrders.pickup")}</>}</div>
              {open.note && <div className="mt-2 rounded-control bg-paper p-2">«{open.note}»</div>}
            </div>
            <ul className="divide-y divide-line rounded-control border border-line">
              {open.lines.map((l) => <li key={l.id} className="flex justify-between gap-3 px-3 py-2"><span>{l.name} <span className="text-muted">×{Number(l.quantity)}</span></span><span className="tabular">{l.unit_price == null ? <span className="text-muted">{t("webOrders.askPrice")}</span> : money(Number(l.unit_price) * Number(l.quantity), open.currency)}</span></li>)}
              <li className="flex justify-between px-3 py-2 font-semibold"><span>{t("webOrders.total")}</span><span className="tabular">{open.total == null ? t("webOrders.confirmPrices") : money(open.total, open.currency)}</span></li>
            </ul>
            {open.payments?.length > 0 && (
              <div className="space-y-3">
                <h3 className="flex items-center gap-2 font-display font-semibold"><Landmark size={16} className="text-accent" />{t("webOrders.pay.title")}</h3>
                {open.payments.map((c) => (
                  <div key={c.id} className="rounded-control border border-line p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={PAY_TONE[c.status]}>{t(`webOrders.pay.status.${c.status}`)}</Badge>
                      <span className="font-semibold tabular">{money(c.amount, open.currency)}</span>
                      <span className="text-muted">{c.sender_bank_name} → {c.bank_name || "—"} · ****{c.reference_last4}</span>
                      <span className="text-xs text-muted">{fmt(c.created_at)}</span>
                    </div>
                    {c.proof_available && <a href={api.proofUrl(open.id, c.id)} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm text-accent hover:underline"><FileText size={14} />{t("webOrders.pay.viewProof")}</a>}
                    {c.status === "verifying" && writable && (
                      <div className="mt-3 space-y-2 rounded-control bg-paper p-3">
                        <p className="text-xs text-muted">{t("webOrders.pay.confirmHint")}</p>
                        {warehouses.length > 1 ? (
                          <select value={warehouse} onChange={(e) => setWarehouse(e.target.value)} className="w-full rounded-control border border-line bg-surface px-3 py-2 text-sm">
                            <option value="">{t("webOrders.pay.warehouseAuto")}</option>
                            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                          </select>
                        ) : null}
                        <Input placeholder={t("webOrders.pay.notePlaceholder")} value={payNote} onChange={(e) => setPayNote(e.target.value)} />
                        <div className="flex flex-wrap gap-2">
                          <Button disabled={busy} onClick={() => decidePayment(c, "confirm")}>{t("webOrders.pay.confirm")}</Button>
                          <Button variant="outline" disabled={busy} onClick={() => decidePayment(c, "reject")}>{t("webOrders.pay.reject")}</Button>
                          <Button variant="outline" className="text-danger" disabled={busy} onClick={() => decidePayment(c, "fraud")}><ShieldAlert size={14} />{t("webOrders.pay.fraud")}</Button>
                        </div>
                      </div>
                    )}
                    {c.status !== "verifying" && (
                      <div className="mt-1 text-xs text-muted">
                        {t("webOrders.decidedBy", { name: c.decided_by_name || "—", date: fmt(c.decided_at) })}
                        {c.decision_note && <> · «{c.decision_note}»</>}
                        {c.invoice_number && <> · {t("webOrders.pay.invoice", { n: c.invoice_number })}</>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <a href={whatsappUrl(open.phone) + `?text=${encodeURIComponent(customerMessage(open, open.status))}`} target="_blank" rel="noreferrer" className="tap inline-flex items-center gap-2 rounded-control border border-line px-3 py-2 text-sm font-medium hover:bg-paper"><MessageCircle size={16} className="text-ok" />{t("webOrders.whatsappCustomer")}</a>
            {open.status === "new" && writable && (
              <div className="space-y-2 rounded-control bg-paper p-3">
                <p className="text-muted">{t("webOrders.confirmHint")}</p>
                <Input placeholder={t("webOrders.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />
                <div className="flex gap-2">
                  <Button disabled={busy} onClick={() => decide(api.confirm)}>{t("webOrders.confirm")}</Button>
                  <Button variant="outline" disabled={busy} onClick={() => decide(api.reject)}>{t("webOrders.reject")}</Button>
                </div>
              </div>
            )}
            {open.status !== "new" && (
              <div className="text-muted">
                {t("webOrders.decidedBy", { name: open.decided_by_name || "—", date: fmt(open.decided_at) })}
                {open.decision_note && <> · «{open.decision_note}»</>}
                {open.sales_order && <div className="mt-1"><Link href="/sales/?tab=quotes" className="text-accent hover:underline">{t("webOrders.openSalesOrder")}</Link></div>}
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}

export default function WebOrdersPage() {
  return <Suspense fallback={null}><WebOrders /></Suspense>;
}
