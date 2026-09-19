"""
Pluggable per-jurisdiction tax + invoice rendering (PROJECT_RULES Rule #7).

A `TaxHandler` knows how to (a) compute tax and (b) render an invoice into a
jurisdiction-appropriate representation. Handlers are selected purely by the
company's `TaxProfile.invoice_format`, so adding a jurisdiction or switching a
company between formats needs NO change to the Invoice model or its data — the
Invoice already snapshots its rate at issue time (M3). Today: a flat-rate
"simple" handler (default) and a "gulf_vat" e-invoice scaffold.
"""

from decimal import Decimal
from xml.sax.saxutils import escape

TWO = Decimal("0.01")


class TaxHandler:
    code = None
    label = None

    def __init__(self, profile):
        self.profile = profile

    def rate(self, product=None):
        """Rate applied to a line. Jurisdiction handlers override this to
        return a per-category or zero rate; the simple handler applies the
        company's flat rate to everything."""
        return self.profile.flat_tax_rate if self.profile else Decimal("0")

    def compute_tax(self, base, product=None):
        """Tax on a net line amount. THE place tax is computed: POS,
        quotations and sales orders all call this, so switching a company's
        invoice_format changes the arithmetic, not only the printout."""
        base = Decimal(base)
        return (base * self.rate(product) / Decimal("100")).quantize(TWO)

    def validate_rate(self, rate):
        """Bounds for a rate stored on the profile."""
        return Decimal("0") <= Decimal(rate) <= Decimal("100")

    def render(self, invoice):
        raise NotImplementedError


class SimpleTaxHandler(TaxHandler):
    code = "simple"
    label = "Simple / plain invoice"

    def render(self, invoice):
        from core.documents import branch_block, issuer_block, money, party_block

        paid = invoice.amount_paid()
        due = invoice.amount_due()
        return {
            "format": self.code,
            "content_type": "application/json",
            "doc_type": "invoice",
            "invoice_number": invoice.number_display,
            "currency": invoice.currency,
            # Who issued it — required on a tax invoice in most jurisdictions.
            "issuer": issuer_block(invoice.company),
            "branch": branch_block(invoice.branch),
            # `customer` stays a plain name for backwards compatibility with
            # the existing document consumers; `party` carries the full block.
            "customer": invoice.customer.name if invoice.customer else None,
            "party": party_block(invoice.customer),
            "issued_at": invoice.issued_at.date().isoformat() if invoice.issued_at else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "payment_terms_days": invoice.payment_terms_days,
            "tax_rate": str(invoice.tax_rate_snapshot),
            "subtotal": money(invoice.subtotal),
            "discount": money(invoice.discount_total),
            "tax": money(invoice.tax_amount),
            "total": money(invoice.total),
            # Settlement is derived from the payment ledger, never stored, so
            # the printed invoice can never disagree with the account.
            "amount_paid": money(paid),
            "amount_due": money(due),
            "status": invoice.status,
            "is_void": invoice.is_void,
            "issued_by": (
                invoice.created_by.full_name or invoice.created_by.email
                if invoice.created_by_id
                else None
            ),
            # How it was paid, for the receipt: "cash 30,000 · Bankak 5,700".
            "payments": [
                {
                    "method": payment.method,
                    "amount": money(payment.amount),
                    "channel": (
                        payment.company_bank_account.channel
                        if payment.company_bank_account_id else ""
                    ),
                    "reference": payment.transfer_reference or payment.reference_last4,
                }
                for payment in invoice.payments.select_related("company_bank_account")
                .order_by("recorded_at", "pk")
            ],
            "lines": [
                {
                    "description": line.description or line.product.name,
                    "quantity": str(line.quantity),
                    "unit_price": money(line.unit_price),
                    # When sold by the pack, the receipt shows what the
                    # customer bought ("2 × Carton (12)"), not 24 pieces.
                    "pack": (
                        {
                            "name": line.pack_name,
                            "contains": str(line.pack_quantity),
                            "packs_sold": str(line.packs_sold),
                        }
                        if line.pack_name else None
                    ),
                    "discount": money(line.discount_amount),
                    "line_total": money(line.line_total),
                }
                for line in invoice.lines.all()
            ],
        }


class GulfVATHandler(TaxHandler):
    """
    Scaffold for Gulf-region VAT e-invoicing. Produces a UBL-like XML document.
    This is intentionally a STUB: the structure and the e-invoicing
    UUID/hash placeholders demonstrate pluggability; real ZATCA/UBL compliance
    (signing, QR, exact schema) is out of scope for the scaffold.
    """

    code = "gulf_vat"
    label = "Gulf VAT e-invoice (scaffold)"

    def render(self, invoice):
        lines_xml = "".join(
            f"<InvoiceLine><ID>{i + 1}</ID>"
            f"<Item>{escape(line.description or line.product.name)}</Item>"
            f"<Quantity>{line.quantity}</Quantity>"
            f"<LineExtensionAmount currencyID=\"{escape(invoice.currency)}\">"
            f"{line.line_subtotal}</LineExtensionAmount></InvoiceLine>"
            for i, line in enumerate(invoice.lines.all())
        )
        einv = ""
        if self.profile and self.profile.e_invoicing_enabled:
            # Placeholders — a real integration fills UUID + cryptographic hash.
            einv = (
                "<UUID>PLACEHOLDER-UUID</UUID>"
                "<Hash>PLACEHOLDER-HASH</Hash>"
            )
        xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<Invoice format=\"gulf-vat-scaffold\">"
            f"<ID>{escape(invoice.number_display)}</ID>"
            f"<DocumentCurrencyCode>{escape(invoice.currency)}</DocumentCurrencyCode>"
            f"{einv}"
            "<TaxTotal>"
            f"<TaxAmount>{invoice.tax_amount}</TaxAmount>"
            f"<Percent>{invoice.tax_rate_snapshot}</Percent>"
            "</TaxTotal>"
            "<LegalMonetaryTotal>"
            f"<TaxExclusiveAmount>{invoice.subtotal}</TaxExclusiveAmount>"
            f"<TaxInclusiveAmount>{invoice.total}</TaxInclusiveAmount>"
            "</LegalMonetaryTotal>"
            f"{lines_xml}"
            "</Invoice>"
        )
        return {
            "format": self.code,
            "content_type": "application/xml",
            "e_invoicing_enabled": bool(
                self.profile and self.profile.e_invoicing_enabled
            ),
            "xml": xml,
            "note": "Scaffold only — not a compliant/signed e-invoice.",
        }


REGISTRY = {
    SimpleTaxHandler.code: SimpleTaxHandler,
    GulfVATHandler.code: GulfVATHandler,
}


def get_handler(profile):
    """Return the handler for a TaxProfile, defaulting to the simple handler."""
    fmt = getattr(profile, "invoice_format", None)
    return REGISTRY.get(fmt, SimpleTaxHandler)(profile)


def available_handlers():
    return [{"code": cls.code, "label": cls.label} for cls in REGISTRY.values()]
