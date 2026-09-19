"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Globe, Lock, MessageCircle, Truck, Store } from "lucide-react";

import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { useAttention } from "@/components/attention/AttentionProvider";
import { webOrders as api } from "@/lib/api";
import { whatsappUrl } from "@/lib/phone";
import { Badge, Button, Card, Input, PageHeader } from "@/components/ui/kit";
import PhoneLink from "@/components/ui/PhoneLink";
import Drawer from "@/components/ui/Drawer";
import PushPrompt from "@/components/orders/PushPrompt";

const TABS = ["new", "confirmed", "rejected", "all"];
const TONE = { new: "warn", confirmed: "ok", rejected: "danger", cancelled: "muted" };

function money(v, c) {
  return `${Number(v || 0).toLocaleString("en", { maximumFractionDigits: 2 })} ${c}`;
}

function WebOrders() {
  const { canRead, canWrite } = useAuth();
  const { t, language } = useI18n();
  const { markSeen } = useAttention();
  const params = useSearchParams();
  const [tab, setTab] = useState("new");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.list(tab === "all" ? {} : { status: tab });
      setRows(res.data.results || res.data);
    } catch (err) {
      setRows([]);
      setError(err?.response?.data?.detail || t("webOrders.loadError"));
    } finally { setLoading(false); }
  }, [tab, t]);
  useEffect(() => { if (canRead("sales")) load(); }, [canRead, load]);
  useEffect(() => { markSeen?.("web-orders"); }, [markSeen]);

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
    catch (err) { setError(err?.response?.data?.detail || t("webOrders.decideError")); }
    finally { setBusy(false); }
  };
  const customerMessage = (order, kind) => {
    const name = order.contact_name;
    const map = {
      confirmed: language === "ar" ? `مرحباً ${name}، تأكّد طلبك رقم ${order.reference} وسنجهّزه.` : `Hello ${name}, your order ${order.reference} is confirmed and being prepared.`,
      rejected: language === "ar" ? `مرحباً ${name}، نعتذر، لم نتمكن من تنفيذ طلبك رقم ${order.reference}.${order.decision_note ? ` السبب: ${order.decision_note}` : ""}` : `Hello ${name}, sorry, we could not fulfil order ${order.reference}.${order.decision_note ? ` Reason: ${order.decision_note}` : ""}`,
      new: language === "ar" ? `مرحباً ${name}، بخصوص طلبك رقم ${order.reference} من موقعنا:` : `Hello ${name}, about your order ${order.reference} from our page:`,
    };
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
            {loading && <tr><td colSpan={7} className="px-4 py-8 text-center text-muted">{t("common.loading")}</td></tr>}
            {!loading && !rows.length && <tr><td colSpan={7} className="px-4 py-10 text-center text-muted"><Globe className="mx-auto mb-2 text-muted" />{t("webOrders.empty")}</td></tr>}
            {!loading && rows.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-paper" onClick={() => setOpen(r)}>
                <td className="px-4 py-3 font-mono font-semibold">{r.reference}</td>
                <td className="px-3 py-3"><div>{r.contact_name}</div><div className="text-xs text-muted" dir="ltr">{r.phone}</div></td>
                <td className="px-3 py-3">{r.branch_name || "—"}</td>
                <td className="px-3 py-3 text-muted">{r.lines.map((l) => `${l.name} ×${Number(l.quantity)}`).join("، ")}</td>
                <td className="px-3 py-3 text-end tabular">{r.total == null ? <span className="text-muted">{t("webOrders.askPrice")}</span> : money(r.total, r.currency)}</td>
                <td className="px-3 py-3 text-muted">{fmt(r.created_at)}</td>
                <td className="px-3 py-3"><Badge tone={TONE[r.status]}>{t(`webOrders.status.${r.status}`)}</Badge> {r.delivery_mode === "delivery" ? <Truck size={14} className="inline text-muted" /> : <Store size={14} className="inline text-muted" />}</td>
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
            <a href={whatsappUrl(open.phone) + `?text=${encodeURIComponent(customerMessage(open, open.status))}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-control border border-line px-3 py-2 text-sm font-medium hover:bg-paper"><MessageCircle size={16} className="text-ok" />{t("webOrders.whatsappCustomer")}</a>
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
