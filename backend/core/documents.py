"""
Shared building blocks for printable documents.

Every outgoing document (invoice, credit/debit note, payment voucher) is
returned as plain JSON and rendered by the frontend, rather than being turned
into a PDF here. That keeps one rendering path for screen and paper, needs no
PDF toolchain on the server, and lets the document print correctly in Arabic
RTL — the browser already handles bidirectional text and the print stylesheet
is the same CSS the app uses everywhere else.

Blank issuer/party fields are dropped rather than emitted empty, so a document
never prints a dangling label like "Tax No:" for a company that has not
registered one.
"""

from decimal import Decimal

TWO = Decimal("0.01")


def money(value):
    """Consistent 2-decimal string. Every amount in every document goes through
    here — mixing "0" with "0.00" across documents looks like a bug to the
    person holding the paper."""
    return str(Decimal(value or 0).quantize(TWO))


def _compact(data):
    return {k: v for k, v in data.items() if v not in (None, "")}


def issuer_block(company):
    """Who issued the document. Most jurisdictions require name, address and
    tax registration number on a tax invoice."""
    if company is None:
        return {}
    return _compact(
        {
            "name": company.name,
            "legal_name": company.legal_name,
            "address": company.address,
            "phone": company.phone,
            "email": company.email,
            "tax_number": company.tax_number,
            "registration_number": company.registration_number,
        }
    )


def party_block(party):
    """The customer or supplier the document is addressed to."""
    if party is None:
        return {}
    return _compact(
        {
            "name": party.name,
            "phone": getattr(party, "phone", ""),
            "email": getattr(party, "email", ""),
            "address": getattr(party, "address", ""),
        }
    )


def branch_block(branch):
    if branch is None:
        return {}
    return _compact(
        {
            "name": branch.name,
            "code": branch.code,
            "address": branch.address,
            "phone": branch.phone,
        }
    )


def _date(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _person(user):
    if user is None:
        return None
    return user.full_name or user.email


def credit_note_document(note):
    """
    The document a customer receives proving money was credited back to them —
    required for every return by PROJECT_RULES Rule #6.
    """
    return {
        "doc_type": "credit_note",
        "number": f"CN-{note.id:06d}",
        "date": _date(note.created_at),
        "currency": note.company.currency,
        "issuer": issuer_block(note.company),
        "party": party_block(note.customer),
        "party_role": "customer",
        "against_invoice": (
            note.invoice.number_display if note.invoice_id else None
        ),
        "against_return": note.sales_return_id,
        "amount": money(note.amount),
        "reason": note.reason,
        "is_void": note.is_void,
        "issued_by": _person(note.created_by),
    }


def debit_note_document(note):
    """The supplier-facing mirror of a credit note."""
    return {
        "doc_type": "debit_note",
        "number": f"DN-{note.id:06d}",
        "date": _date(note.created_at),
        "currency": note.company.currency,
        "issuer": issuer_block(note.company),
        "party": party_block(note.supplier),
        "party_role": "supplier",
        "against_bill": (
            note.bill.supplier_invoice_number or f"BILL-{note.bill_id}"
            if note.bill_id
            else None
        ),
        "against_return": note.purchase_return_id,
        "amount": money(note.amount),
        "reason": note.reason,
        "is_void": note.is_void,
        "issued_by": _person(note.created_by),
    }


def payment_receipt_document(payment):
    """
    Proof of money received from a customer. The invoice totals are recomputed
    here (never stored) so the receipt agrees with the invoice by construction.
    """
    invoice = payment.invoice
    return {
        "doc_type": "payment_receipt",
        "number": f"RC-{payment.id:06d}",
        "date": _date(payment.recorded_at),
        "currency": payment.company.currency,
        "issuer": issuer_block(payment.company),
        "party": party_block(invoice.customer),
        "party_role": "customer",
        "against_invoice": invoice.number_display,
        "method": payment.get_method_display(),
        "bank": _compact(
            {
                "account": (
                    str(payment.company_bank_account)
                    if payment.company_bank_account_id
                    else ""
                ),
                "sender_bank": payment.sender_bank_name,
                # Only ever the last 4 — full references are not stored.
                "reference_last4": payment.reference_last4,
            }
        ),
        "amount": money(payment.amount),
        "invoice_total": money(invoice.total),
        "invoice_paid": money(invoice.amount_paid()),
        "invoice_due": money(invoice.amount_due()),
        "received_by": _person(payment.recorded_by),
        "verified_by": _person(payment.verified_by),
        "verified_at": _date(payment.verified_at),
    }


def supplier_payment_document(payment):
    """Proof of money paid out to a supplier — the payment voucher."""
    bill = payment.bill
    return {
        "doc_type": "payment_voucher",
        "number": f"PV-{payment.id:06d}",
        "date": _date(payment.recorded_at),
        "currency": payment.company.currency,
        "issuer": issuer_block(payment.company),
        "party": party_block(payment.supplier),
        "party_role": "supplier",
        "against_bill": bill.supplier_invoice_number or f"BILL-{bill.id}",
        "method": payment.get_method_display(),
        "bank": _compact(
            {
                "account": (
                    str(payment.from_bank_account)
                    if payment.from_bank_account_id
                    else ""
                ),
                "reference_last4": payment.reference_last4,
            }
        ),
        "amount": money(payment.amount),
        "bill_total": money(bill.total),
        "paid_by": _person(payment.recorded_by),
        "verified_by": _person(payment.verified_by),
        "verified_at": _date(payment.verified_at),
    }
