"""The one way a customer payment is written.

Every path that records money against an invoice — the till, the collect
drawer, the offline replay and the public order's transfer claim — goes
through ``record_payment``. It locks the invoice, caps the amount at what
is still owed, takes the currency and rate from the invoice (never from the
caller), validates transfer references, and stamps the invoice's
``updated_at`` so other devices pull the new balance. The 2026-09-20 review
found the public-order path writing payments directly and accepting
800 + 800 on a 1,000 order; this module makes that impossible by
construction.
"""
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework import serializers

from sales.models import CompanyBankAccount, Invoice, Payment


def record_payment(invoice, *, amount, method, recorded_by=None, company_bank_account=None,
                   sender_bank_name="", reference_last4="", transfer_reference="",
                   shift=None, credit_note=None, client_uuid=None, recorded_at=None,
                   receipt_group=None, verified_by=None):
    """Create one Payment under a row lock on the invoice.

    Raises ``serializers.ValidationError`` when the amount exceeds the
    balance due or a bank transfer lacks its reference; the caller answers
    400 (or 409 for a concurrent overpay, which reads the same).
    """
    from sales.serializers import assert_store_credit, transfer_details

    if amount is None or amount <= 0:
        raise serializers.ValidationError({"amount": _("Amount must be positive.")})
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if locked.is_void:
            raise serializers.ValidationError({"invoice": _("This invoice is void.")})
        due = locked.amount_due()
        if amount > due:
            raise serializers.ValidationError({
                "amount": _("Amount exceeds the balance due (%(due)s). Record the "
                            "surplus separately instead of overpaying the invoice.")
                % {"due": due},
                "code": "overpayment",
            })
        details = {
            "reference_last4": reference_last4, "transfer_reference": transfer_reference,
            "receipt_group": receipt_group,
        }
        if method == Payment.BANK_TRANSFER:
            if company_bank_account is None or not sender_bank_name:
                raise serializers.ValidationError(
                    _("Bank transfer needs the receiving account and the sender.")
                )
            if company_bank_account.company_id != locked.company_id:
                raise serializers.ValidationError(
                    {"company_bank_account": _("Not your company's bank account.")}
                )
            # Serialise reference checks per receiving account: two tills
            # presenting the same screenshot at once both passed the
            # unlocked check before (review F13). The lock is held until
            # this transaction commits the row.
            company_bank_account = CompanyBankAccount.objects.select_for_update().get(
                pk=company_bank_account.pk
            )
            details["reference_last4"] = transfer_details(details, company_bank_account)
        elif method == Payment.CASH:
            if company_bank_account or sender_bank_name or reference_last4 or transfer_reference:
                raise serializers.ValidationError(
                    _("Cash payments must not carry bank/reference details.")
                )
        elif method == Payment.STORE_CREDIT:
            from returns.models import CreditNote

            if credit_note is None:
                raise serializers.ValidationError(
                    {"credit_note": _("A store-credit payment names the credit note it draws on.")}
                )
            credit_note = CreditNote.objects.select_for_update().get(pk=credit_note.pk)
            assert_store_credit(credit_note, locked, amount, locked.company_id)
        try:
            payment = _create(locked, method, amount, company_bank_account, sender_bank_name,
                              details, shift, credit_note, recorded_by, client_uuid,
                              recorded_at, receipt_group, verified_by)
        except IntegrityError as exc:
            if "uniq_payment_reference_per_invoice" in str(exc):
                raise serializers.ValidationError({
                    "transfer_reference": _("This transfer was already recorded on this invoice."),
                    "code": "duplicate_reference",
                })
            raise
        Invoice.objects.filter(pk=locked.pk).update(updated_at=payment.recorded_at)
    return payment


def _create(locked, method, amount, company_bank_account, sender_bank_name, details, shift,
            credit_note, recorded_by, client_uuid, recorded_at, receipt_group, verified_by):
    # A savepoint so a constraint violation does not poison the outer
    # transaction (PostgreSQL aborts it otherwise).
    with transaction.atomic():
        return Payment.objects.create(
            company_id=locked.company_id, invoice=locked, method=method,
            company_bank_account=company_bank_account if method == Payment.BANK_TRANSFER else None,
            sender_bank_name=sender_bank_name if method == Payment.BANK_TRANSFER else "",
            reference_last4=details["reference_last4"] if method == Payment.BANK_TRANSFER else "",
            transfer_reference=(
                details["transfer_reference"] if method == Payment.BANK_TRANSFER else ""
            ),
            amount=amount,
            # Snapshot from the invoice, never from the caller (review F04).
            currency=locked.currency, exchange_rate=locked.exchange_rate,
            shift=shift, credit_note=credit_note if method == Payment.STORE_CREDIT else None,
            recorded_by=recorded_by, client_uuid=client_uuid, receipt_group=receipt_group,
            **({"recorded_at": recorded_at} if recorded_at else {}),
            **({"verified_by": verified_by, "verified_at": _now()} if verified_by else {}),
        )


def _now():
    from django.utils import timezone

    return timezone.now()
