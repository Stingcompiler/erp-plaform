"use client";

import { useI18n } from "../../app/providers/I18nProvider";
import { channelLabel } from "@/lib/bankChannels";

/**
 * A till receipt for 80 mm / 58 mm thermal rolls.
 *
 * One column, no borders, large totals: what a customer reads in the shop
 * doorway. Fed the same document payload as DocumentView so the numbers
 * cannot differ from the A4 invoice; only the layout does. Widths are
 * fixed in millimetres because a roll printer has no page to fit to.
 */

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Always digits in day/month/year order, Latin numerals: a receipt is read
// in a doorway, and bidi reordering of Arabic-locale dates inside an LTR
// span turned "19/9/2026" into "192026/9/".
function fmtDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = (n) => String(n).padStart(2, "0");
  const date = `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
  return /T\d/.test(String(value)) ? `${date} ${pad(d.getHours())}:${pad(d.getMinutes())}` : date;
}

const TITLE_KEY = {
  invoice: "doc.titleInvoice",
  credit_note: "doc.titleCreditNote",
  debit_note: "doc.titleDebitNote",
  payment_receipt: "doc.titleReceipt",
  payment_voucher: "doc.titleVoucher",
};

function Dashed() {
  return <div className="my-1.5 border-t border-dashed border-black" />;
}

function Row({ label, value, strong }) {
  return (
    <div className={`flex justify-between gap-2 ${strong ? "text-[13px] font-bold" : ""}`}>
      <span className="min-w-0 flex-1">{label}</span>
      <span className="tabular shrink-0" dir="ltr">{value}</span>
    </div>
  );
}

export default function ReceiptView({ doc, paper = "80mm" }) {
  const { t } = useI18n();
  if (!doc) return null;
  const narrow = paper === "58mm";
  const type = doc.doc_type || "invoice";
  const issuer = doc.issuer || {};
  const currency = doc.currency || "";
  const isInvoice = type === "invoice";
  const width = narrow ? "48mm" : "72mm";
  const methodLabel = (p) =>
    p.method === "cash" ? t("common.cash")
      : p.method === "credit" ? t("sales.storeCredit")
        : p.channel && p.channel !== "bank" ? channelLabel(t, p.channel) : t("common.bankTransfer");

  return (
    <div
      className={`receipt mx-auto bg-white text-black ${narrow ? "text-[10px]" : "text-[11px]"} leading-snug`}
      style={{ width, padding: "2mm 0" }}
    >
      {/* ---- header ---- */}
      <div className="text-center">
        <div className={`font-bold ${narrow ? "text-[13px]" : "text-[15px]"}`}>{issuer.name || "—"}</div>
        {issuer.address && <div className="whitespace-pre-line">{issuer.address}</div>}
        {issuer.phone && <div className="tabular" dir="ltr">{issuer.phone}</div>}
        {issuer.tax_number && <div className="tabular">{t("doc.taxNumber")}: <span dir="ltr">{issuer.tax_number}</span></div>}
      </div>
      <Dashed />
      <div className="text-center font-bold uppercase">{t(TITLE_KEY[type] || TITLE_KEY.invoice)}</div>
      <Row label={t("doc.number")} value={doc.number || doc.invoice_number} />
      <Row label={t("doc.date")} value={fmtDate(doc.date || doc.issued_at)} />
      {doc.branch?.name && <Row label={t("doc.branch")} value={doc.branch.name} />}
      {doc.party?.name && <Row label={t("doc.customer")} value={doc.party.name} />}
      {doc.issued_by && <Row label={t("doc.cashier")} value={doc.issued_by} />}
      {(doc.is_void || doc.provisional) && (
        <div className="mt-1 text-center font-bold uppercase">{t(doc.is_void ? "doc.void" : "doc.provisional")}</div>
      )}
      <Dashed />

      {/* ---- lines ---- */}
      {isInvoice && Array.isArray(doc.lines) && (
        <div className="space-y-1">
          {doc.lines.map((l, i) => (
            <div key={i}>
              <div className="break-words">{l.description}</div>
              <div className="flex justify-between gap-2 tabular" dir="ltr">
                <span>
                  {l.pack ? `${l.pack.packs_sold} × ${l.pack.name}` : `${Number(l.quantity)} × ${money(l.unit_price)}`}
                  {Number(l.discount) > 0 ? ` −${money(l.discount)}` : ""}
                </span>
                <span>{money(l.line_total)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {!isInvoice && (
        <div className="space-y-0.5">
          {(doc.against_invoice || doc.against_bill) && <Row label={t("doc.against")} value={doc.against_invoice || doc.against_bill} />}
          {doc.method && <Row label={t("doc.method")} value={doc.method} />}
          {doc.bank?.account && <Row label={t("doc.bankAccount")} value={doc.bank.account} />}
          {doc.bank?.reference_last4 && <Row label={t("doc.reference")} value={doc.bank.reference_last4} />}
          {doc.reason && <div>{t("doc.reason")}: {doc.reason}</div>}
        </div>
      )}
      <Dashed />

      {/* ---- totals ---- */}
      {isInvoice ? (
        <>
          <Row label={t("doc.subtotal")} value={money(doc.subtotal)} />
          {Number(doc.discount) > 0 && <Row label={t("doc.discount")} value={`−${money(doc.discount)}`} />}
          {Number(doc.tax) > 0 && <Row label={`${t("doc.tax")} ${doc.tax_rate ?? 0}%`} value={money(doc.tax)} />}
          <Row label={`${t("doc.total")} ${currency}`} value={money(doc.total)} strong />
          {Array.isArray(doc.payments) && doc.payments.map((p, i) => (
            <Row key={i} label={`${t("doc.paid")} · ${methodLabel(p)}${p.reference ? ` #${p.reference}` : ""}`} value={money(p.amount)} />
          ))}
          {Number(doc.amount_due) > 0 && <Row label={t("doc.balanceDue")} value={money(doc.amount_due)} strong />}
        </>
      ) : (
        <>
          <Row label={`${t("doc.amount")} ${currency}`} value={money(doc.amount)} strong />
          {doc.invoice_due != null && <Row label={t("doc.balanceDue")} value={money(doc.invoice_due)} />}
        </>
      )}
      <Dashed />

      {/* ---- footer ---- */}
      <div className="text-center">
        {issuer.receipt_footer && <div className="whitespace-pre-line">{issuer.receipt_footer}</div>}
        <div className="mt-1">{t("doc.thanks")}</div>
      </div>
    </div>
  );
}
