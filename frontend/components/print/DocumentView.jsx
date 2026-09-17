"use client";

import { useI18n } from "../../app/providers/I18nProvider";

/**
 * Renders a document payload from the API into a printable page.
 *
 * One component serves both the on-screen preview and the paper output, so
 * what the user proofreads is exactly what prints. Styling stays deliberately
 * plain — black on white, no theme colours — because a document is read on
 * paper, and printers do not render the app's surface tokens.
 *
 * Every field is optional: a company that has not registered a tax number, a
 * walk-in sale with no customer, or a note with no reason all render without
 * leaving an empty label behind.
 */

const money = (v) =>
  Number(v ?? 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const TITLE_KEY = {
  invoice: "doc.titleInvoice",
  credit_note: "doc.titleCreditNote",
  debit_note: "doc.titleDebitNote",
  payment_receipt: "doc.titleReceipt",
  payment_voucher: "doc.titleVoucher",
};

function Line({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-black/55">{label}: </span>
      <span>{value}</span>
    </div>
  );
}

function Party({ heading, party }) {
  if (!party?.name) return null;
  return (
    <div className="avoid-break">
      <div className="mb-1 text-[11px] uppercase tracking-wide text-black/50">
        {heading}
      </div>
      <div className="font-medium">{party.name}</div>
      {party.address && <div className="text-black/70">{party.address}</div>}
      {party.phone && <div className="tabular text-black/70">{party.phone}</div>}
      {party.email && <div className="text-black/70">{party.email}</div>}
    </div>
  );
}

function TotalRow({ label, value, currency, strong, divide }) {
  return (
    <div
      className={`flex items-center justify-between gap-8 py-1 ${
        divide ? "border-t border-black/25 mt-1 pt-2" : ""
      } ${strong ? "text-base font-semibold" : ""}`}
    >
      <span className={strong ? "" : "text-black/60"}>{label}</span>
      <span className="tabular">
        {money(value)} {currency}
      </span>
    </div>
  );
}

export default function DocumentView({ doc }) {
  const { t } = useI18n();
  if (!doc) return null;

  // The Gulf VAT handler emits raw XML — a developer artefact, not something to
  // hand a customer. Show it as-is rather than pretending it is a document.
  if (doc.format === "gulf_vat") {
    return (
      <div>
        <p className="mb-2 text-sm text-black/60">{t("doc.xmlScaffold")}</p>
        <pre className="overflow-x-auto whitespace-pre-wrap break-all text-[10px]">
          {doc.xml}
        </pre>
      </div>
    );
  }

  const type = doc.doc_type || "invoice";
  const currency = doc.currency || "";
  const issuer = doc.issuer || {};
  const isInvoice = type === "invoice";
  const isPayment = type === "payment_receipt" || type === "payment_voucher";
  const partyHeading =
    doc.party_role === "supplier" ? t("doc.supplier") : t("doc.billTo");

  return (
    <div className="mx-auto max-w-3xl bg-white p-6 text-[13px] leading-relaxed text-black print:p-0">
      {/* ---- header ---- */}
      <div className="flex flex-wrap items-start justify-between gap-6 border-b-2 border-black pb-4">
        <div className="min-w-0">
          <div className="font-display text-xl font-bold">
            {issuer.name || "—"}
          </div>
          {issuer.legal_name && issuer.legal_name !== issuer.name && (
            <div className="text-black/70">{issuer.legal_name}</div>
          )}
          {issuer.address && (
            <div className="whitespace-pre-line text-black/70">{issuer.address}</div>
          )}
          <div className="tabular text-black/70">
            {[issuer.phone, issuer.email].filter(Boolean).join(" · ")}
          </div>
          <div className="mt-1 space-y-0.5 text-[12px]">
            <Line label={t("doc.taxNumber")} value={issuer.tax_number} />
            <Line
              label={t("doc.registrationNumber")}
              value={issuer.registration_number}
            />
          </div>
        </div>

        <div className="text-end">
          <div className="font-display text-lg font-bold uppercase tracking-wide">
            {t(TITLE_KEY[type] || TITLE_KEY.invoice)}
          </div>
          <div className="tabular mt-1 text-base">
            {doc.number || doc.invoice_number}
          </div>
          <div className="mt-1 space-y-0.5 text-[12px]">
            <Line label={t("doc.date")} value={doc.date || doc.issued_at} />
            <Line label={t("doc.dueDate")} value={doc.due_date} />
          </div>
          {doc.is_void && (
            <div className="mt-2 inline-block border border-black px-2 py-0.5 text-[11px] font-bold uppercase">
              {t("doc.void")}
            </div>
          )}
          {doc.provisional && (
            <div className="mt-2 inline-block border border-black px-2 py-0.5 text-[11px] font-bold uppercase">
              {t("doc.provisional")}
            </div>
          )}
        </div>
      </div>

      {/* ---- parties ---- */}
      <div className="flex flex-wrap justify-between gap-6 py-4">
        <Party heading={partyHeading} party={doc.party} />
        {doc.branch?.name && (
          <div className="avoid-break text-end">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-black/50">
              {t("doc.branch")}
            </div>
            <div>{doc.branch.name}</div>
            {doc.branch.address && (
              <div className="text-black/70">{doc.branch.address}</div>
            )}
          </div>
        )}
      </div>

      {/* ---- body ---- */}
      {isInvoice && Array.isArray(doc.lines) && (
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-y border-black/40 text-[11px] uppercase tracking-wide text-black/60">
              <th className="py-2 text-start font-medium">{t("doc.description")}</th>
              <th className="py-2 text-end font-medium">{t("doc.qty")}</th>
              <th className="py-2 text-end font-medium">{t("doc.unitPrice")}</th>
              <th className="py-2 text-end font-medium">{t("doc.lineTotal")}</th>
            </tr>
          </thead>
          <tbody>
            {doc.lines.map((l, i) => (
              <tr key={i} className="border-b border-black/15">
                <td className="py-1.5">{l.description}</td>
                <td className="tabular py-1.5 text-end">{l.quantity}</td>
                <td className="tabular py-1.5 text-end">{money(l.unit_price)}</td>
                <td className="tabular py-1.5 text-end">{money(l.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!isInvoice && (
        <div className="avoid-break space-y-1 border-y border-black/40 py-3">
          <Line
            label={t("doc.against")}
            value={doc.against_invoice || doc.against_bill}
          />
          <Line label={t("doc.method")} value={doc.method} />
          <Line label={t("doc.bankAccount")} value={doc.bank?.account} />
          <Line label={t("doc.senderBank")} value={doc.bank?.sender_bank} />
          <Line label={t("doc.reference")} value={doc.bank?.reference_last4} />
          <Line label={t("doc.reason")} value={doc.reason} />
        </div>
      )}

      {/* ---- totals ---- */}
      <div className="mt-4 flex justify-end">
        <div className="w-full max-w-xs">
          {isInvoice ? (
            <>
              <TotalRow
                label={t("doc.subtotal")}
                value={doc.subtotal}
                currency={currency}
              />
              <TotalRow
                label={`${t("doc.tax")} (${doc.tax_rate ?? 0}%)`}
                value={doc.tax}
                currency={currency}
              />
              <TotalRow
                label={t("doc.total")}
                value={doc.total}
                currency={currency}
                strong
                divide
              />
              <TotalRow
                label={t("doc.paid")}
                value={doc.amount_paid}
                currency={currency}
              />
              <TotalRow
                label={t("doc.balanceDue")}
                value={doc.amount_due}
                currency={currency}
                strong
                divide
              />
            </>
          ) : (
            <>
              <TotalRow
                label={t("doc.amount")}
                value={doc.amount}
                currency={currency}
                strong
                divide
              />
              {isPayment && doc.invoice_total != null && (
                <>
                  <TotalRow
                    label={t("doc.invoiceTotal")}
                    value={doc.invoice_total}
                    currency={currency}
                  />
                  <TotalRow
                    label={t("doc.balanceDue")}
                    value={doc.invoice_due}
                    currency={currency}
                  />
                </>
              )}
              {doc.bill_total != null && (
                <TotalRow
                  label={t("doc.billTotal")}
                  value={doc.bill_total}
                  currency={currency}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* ---- attribution ---- */}
      <div className="avoid-break mt-8 flex flex-wrap gap-8 border-t border-black/25 pt-3 text-[12px]">
        <Line
          label={
            type === "payment_receipt"
              ? t("doc.receivedBy")
              : type === "payment_voucher"
                ? t("doc.paidBy")
                : t("doc.issuedBy")
          }
          value={doc.issued_by || doc.received_by || doc.paid_by}
        />
        <Line label={t("doc.verifiedBy")} value={doc.verified_by} />
      </div>
    </div>
  );
}
