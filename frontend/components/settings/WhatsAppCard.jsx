"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageCircle, Send } from "lucide-react";

import { whatsapp as api } from "@/lib/api";
import { errorText } from "@/lib/errors";
import { useI18n } from "../../app/providers/I18nProvider";
import { Badge, Button, Field, Input } from "@/components/ui/kit";

// Meta's body parameters are positional; the backend names them in English
// ("customer name"). Show the reader their own words, keeping {{1}}…{{4}}.
const PARAM_KEY = {
  "customer name": "customerName", "invoice number": "invoiceNumber", "total": "total",
  "amount due": "amountDue", "amount paid": "amountPaid", "balance due": "balanceDue",
  "amount overdue": "amountOverdue", "oldest invoice": "oldestInvoice",
  "days overdue": "daysOverdue", "order reference": "orderReference", "branch": "branch",
};

const STATUS_TONE = { received: "accent", queued: "muted", sent: "muted", delivered: "ok", read: "ok", failed: "danger" };

/**
 * Settings → WhatsApp: connect the company's own WhatsApp Business number,
 * pick the approved Meta template for each purpose, send a test, and see
 * the last messages. The access token is write-only: entered here, never
 * shown again.
 */
export default function WhatsAppCard({ canManage, language }) {
  const { t } = useI18n();
  const [data, setData] = useState(null);
  const [account, setAccount] = useState({ phone_number_id: "", waba_id: "", display_phone: "", display_name: "", access_token: "", is_active: true });
  const [templates, setTemplates] = useState([]);
  const [test, setTest] = useState({ phone: "", text: "" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.settings().then((r) => {
      setData(r.data);
      const a = r.data.account;
      setAccount({
        phone_number_id: a?.phone_number_id || "", waba_id: a?.waba_id || "",
        display_phone: a?.display_phone || "", display_name: a?.display_name || "",
        access_token: "", is_active: a ? a.is_active !== false : true,
      });
      setTemplates(r.data.templates || []);
    }).catch(() => setData({ error: true }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const setAcc = (key) => (e) => setAccount((a) => ({ ...a, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const setTpl = (purpose, key) => (e) =>
    setTemplates((rows) => rows.map((r) => (r.purpose === purpose ? { ...r, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value } : r)));

  async function save() {
    setMsg(""); setBusy(true);
    try {
      const body = { templates: templates.map(({ purpose, template_name, language: lang, is_active }) => ({ purpose, template_name, language: lang, is_active })) };
      if (account.phone_number_id.trim()) body.account = account;
      const r = await api.saveSettings(body);
      setData(r.data);
      setAccount((a) => ({ ...a, access_token: "" }));
      setMsg(t("settings.whatsappSaved"));
    } catch (err) {
      setMsg(errorText(err, t, "settings.saveFailed"));
    } finally { setBusy(false); }
  }

  async function sendTest() {
    setMsg(""); setBusy(true);
    try {
      const r = await api.testSend(test);
      setMsg(r.data.status === "failed" ? t("settings.whatsappTestFailed", { reason: r.data.error_title || "" }) : t("settings.whatsappTestSent"));
      load();
    } catch (err) {
      setMsg(errorText(err, t, "settings.saveFailed"));
    } finally { setBusy(false); }
  }

  const fmt = (v) => new Date(v).toLocaleString(language === "ar" ? "ar" : "en", { dateStyle: "short", timeStyle: "short" });
  const connected = Boolean(data?.account?.phone_number_id);

  return (
    <>
      <h2 className="mb-1 flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wide text-muted">
        <MessageCircle size={16} /> {t("settings.whatsapp")}
        {connected && <Badge tone={data.account.has_token ? "ok" : "warn"}>{t(data.account.has_token ? "settings.whatsappConnected" : "settings.whatsappNoToken")}</Badge>}
      </h2>
      <p className="mb-4 text-sm text-muted">{t("settings.whatsappHint")}</p>
      {data?.error && <p className="text-sm text-danger">{t("common.loadError")}</p>}
      {data && !data.error && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("settings.whatsappPhoneNumberId")} hint={t("settings.whatsappPhoneNumberIdHint")}>
              <Input value={account.phone_number_id} onChange={setAcc("phone_number_id")} dir="ltr" disabled={!canManage} />
            </Field>
            <Field label={t("settings.whatsappWabaId")}>
              <Input value={account.waba_id} onChange={setAcc("waba_id")} dir="ltr" disabled={!canManage} />
            </Field>
            <Field label={t("settings.whatsappDisplayPhone")} hint={t("settings.whatsappDisplayPhoneHint")}>
              <Input value={account.display_phone} onChange={setAcc("display_phone")} dir="ltr" inputMode="tel" disabled={!canManage} />
            </Field>
            <Field label={t("settings.whatsappDisplayName")}>
              <Input value={account.display_name} onChange={setAcc("display_name")} disabled={!canManage} />
            </Field>
            <Field label={t("settings.whatsappToken")} hint={t(data.account?.has_token ? "settings.whatsappTokenKeep" : "settings.whatsappTokenHint")}>
              <Input type="password" autoComplete="off" value={account.access_token} onChange={setAcc("access_token")} dir="ltr" disabled={!canManage} />
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" checked={account.is_active} onChange={setAcc("is_active")} className="h-4 w-4 accent-accent" disabled={!canManage} />
              {t("settings.whatsappActive")}
            </label>
          </div>
          {data.account?.last_event_at && (
            <p className="text-xs text-muted">{t("settings.whatsappLastEvent", { when: fmt(data.account.last_event_at) })} · {t("settings.whatsappOptedIn", { count: data.opted_in_customers ?? 0 })}</p>
          )}

          <div>
            <h3 className="text-sm font-semibold">{t("settings.whatsappTemplates")}</h3>
            <p className="mb-2 text-xs text-muted">{t("settings.whatsappTemplatesHint")}</p>
            <div className="divide-y divide-line rounded-card border border-line">
              {templates.map((row) => (
                <div key={row.purpose} className="grid gap-2 px-3 py-2 sm:grid-cols-[1fr_1fr_5rem_auto] sm:items-center">
                  <div>
                    <div className="text-sm">{t(`settings.whatsappPurpose.${row.purpose}`)}</div>
                    <div className="text-xs text-muted">{row.params.map((p, i) => `{{${i + 1}}} ${PARAM_KEY[p] ? t(`settings.whatsappParam.${PARAM_KEY[p]}`) : p}`).join(" · ")}</div>
                  </div>
                  <Input value={row.template_name} onChange={setTpl(row.purpose, "template_name")} dir="ltr" placeholder={t("settings.whatsappTemplateName")} disabled={!canManage} />
                  <Input value={row.language} onChange={setTpl(row.purpose, "language")} dir="ltr" maxLength={8} disabled={!canManage} />
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={row.is_active} onChange={setTpl(row.purpose, "is_active")} className="h-4 w-4 accent-accent" disabled={!canManage} />
                    {t("common.active")}
                  </label>
                </div>
              ))}
            </div>
          </div>

          {canManage && (
            <div className="flex flex-wrap items-end gap-3">
              <Button onClick={save} disabled={busy}>{busy ? t("common.saving") : t("common.save")}</Button>
              <div className="ms-auto flex flex-wrap items-end gap-2">
                <Field label={t("settings.whatsappTestPhone")}>
                  <Input value={test.phone} onChange={(e) => setTest({ ...test, phone: e.target.value })} dir="ltr" inputMode="tel" className="w-40" />
                </Field>
                <Field label={t("settings.whatsappTestText")}>
                  <Input value={test.text} onChange={(e) => setTest({ ...test, text: e.target.value })} className="w-56" />
                </Field>
                <Button variant="outline" onClick={sendTest} disabled={busy || !connected || !test.phone || !test.text}>
                  <Send size={15} /> {t("settings.whatsappSendTest")}
                </Button>
              </div>
            </div>
          )}
          {msg && <p className="text-sm text-muted">{msg}</p>}

          {data.recent_messages?.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold">{t("settings.whatsappRecent")}</h3>
              <div className="divide-y divide-line text-sm">
                {data.recent_messages.map((m) => (
                  <div key={m.id} className="flex flex-wrap items-center gap-2 py-1.5">
                    <span className="text-muted">{m.direction === "in" ? "←" : "→"}</span>
                    <span dir="ltr" className="tabular">{m.phone}</span>
                    {m.contact_name && <span className="text-muted">{m.contact_name}</span>}
                    <span className="min-w-0 flex-1 truncate">{m.text || (m.purpose ? t(`settings.whatsappPurpose.${m.purpose}`) : "")}</span>
                    <Badge tone={STATUS_TONE[m.status] || "muted"}>{t(`settings.whatsappStatus.${m.status}`)}</Badge>
                    {m.error_title && <span className="text-xs text-danger">{m.error_title}</span>}
                    <span className="text-xs text-muted" dir="ltr">{fmt(m.created_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
