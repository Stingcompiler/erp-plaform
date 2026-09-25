"""Payment claims on public orders: what the visitor declares, what the
company decides, and what a decision does.

CONFIRMED is the only decision with consequences beyond the claim itself:
it rings the order up through the same checkout the till uses — invoice,
sale-out stock movements, a bank-transfer payment — and marks the payment
verified by the person who checked the bank. The person who confirms is
therefore the second pair of eyes the money rule asks for (the visitor is
the first); above the company's approval threshold it must be an approver.
FRAUD blocks the phone and the browser behind the claim from the page.
"""

import re
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from website.models import BlockedContact, PublicOrder, PublicOrderPayment
from website.tracking import first_name, record_stage


def public_bank_accounts(company):
    from sales.models import CompanyBankAccount

    return list(
        CompanyBankAccount.objects.filter(
            company=company, is_active=True, show_to_customers=True
        ).order_by("bank_name")
    )


def is_blocked(company, phone="", visitor_hash=""):
    qs = BlockedContact.objects.filter(company=company)
    if phone and qs.filter(phone=phone).exists():
        return True
    return bool(visitor_hash and qs.filter(visitor_hash=visitor_hash).exists())


def order_for_visitor(site, reference):
    """The public view of one order: no phone, no internal ids."""
    order = PublicOrder.objects.filter(
        website=site, reference__iexact=str(reference or "").strip()
    ).prefetch_related("lines", "payments__payment").first()
    return order


def claim_payload(claim):
    return {
        "id": claim.pk,
        "status": (
            PublicOrderPayment.REJECTED if claim.status == PublicOrderPayment.FRAUD
            else claim.status
        ),
        "sender_bank_name": claim.sender_bank_name,
        "reference_last4": claim.reference_last4,
        "amount": str(claim.amount),
        "created_at": claim.created_at,
        "decision_note": claim.decision_note if claim.status == PublicOrderPayment.REJECTED else "",
    }


def paid_so_far(order):
    """What was recorded against the order: a confirmed claim counts at the
    payment it produced (a surplus handed back is not paid)."""
    return sum(
        (
            c.payment.amount if c.payment_id else c.amount
            for c in order.payments.all() if c.status == PublicOrderPayment.CONFIRMED
        ),
        Decimal("0"),
    )


def public_order_payload(order):
    accounts = public_bank_accounts(order.company)
    return {
        "reference": order.reference,
        "status": order.status,
        "contact_name": first_name(order.contact_name),
        "currency": order.currency,
        # Tax included: what the confirmation invoices and what to transfer.
        "total": str(order.total) if order.total is not None else None,
        "tax_amount": str(order.tax_amount) if order.tax_amount is not None else None,
        "priced": order.total is not None,
        "lines": [
            {"name": line.name, "quantity": str(line.quantity),
             "unit_price": str(line.unit_price) if line.unit_price is not None else None}
            for line in order.lines.all()
        ],
        "branch": order.branch.name if order.branch else "",
        "bank_accounts": [
            {"id": a.pk, "bank_name": a.bank_name, "account_name": a.account_name,
             "account_number": a.account_number}
            for a in accounts
        ],
        "can_pay": (
            order.status in PublicOrder.PAYABLE
            and order.total is not None and bool(accounts)
            and paid_so_far(order) < order.total
        ),
        "paid": str(paid_so_far(order)),
        "payments": [claim_payload(c) for c in order.payments.all()],
    }


@transaction.atomic
def declare_payment(order, payload, files=None, request=None):
    if order.status not in PublicOrder.PAYABLE:
        raise ValidationError({"detail": _("This order is closed.")})
    if order.total is None:
        raise ValidationError({"detail": _("The shop has not confirmed the amount yet.")})
    accounts = {a.pk: a for a in public_bank_accounts(order.company)}
    try:
        account = accounts[int(payload.get("bank_account"))]
    except (TypeError, ValueError, KeyError):
        raise ValidationError({"bank_account": _("Choose the account you transferred to.")})
    sender = str(payload.get("sender_bank_name") or "").strip()[:120]
    if not sender:
        raise ValidationError({"sender_bank_name": _("Which bank did you transfer from?")})
    ref = re.sub(r"\D", "", str(payload.get("reference_last4") or ""))
    if len(ref) != 4:
        raise ValidationError({"reference_last4": _("Enter the last four digits of the transfer.")})
    try:
        amount = Decimal(str(payload.get("amount"))).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001
        raise ValidationError({"amount": _("Enter the amount you transferred.")})
    if amount <= 0:
        raise ValidationError({"amount": _("Enter the amount you transferred.")})
    if order.payments.filter(reference_last4=ref).exists():
        raise ValidationError({"reference_last4": _("This transfer was already declared.")})
    visitor = ""
    if request is not None:
        from website.analytics import _visitor_hash

        visitor = _visitor_hash(request, timezone.localdate())
    if is_blocked(order.company, order.phone, visitor):
        raise ValidationError({"detail": _("This order is closed.")})
    proof = (files or {}).get("proof")
    if proof is not None:
        from core.uploads import validate_proof

        validate_proof(proof, max_bytes=5 * 1024 * 1024)
    claim = PublicOrderPayment.objects.create(
        order=order, company=order.company, bank_account=account, sender_bank_name=sender,
        reference_last4=ref, amount=amount, proof=proof, visitor_hash=visitor,
    )
    log_activity(
        action="public_payment_declared", company=order.company,
        entity_type="PublicOrderPayment", entity_id=claim.pk,
        metadata={"reference": order.reference, "amount": str(amount), "last4": ref},
    )
    transaction.on_commit(lambda: _notify_claim(claim))
    return claim


def _notify_claim(claim):
    from core import push
    from website.orders import recipients

    order = claim.order
    for user in recipients(order):
        push.send_to_user(
            user,
            title=f"تحويل بانتظار التحقق {order.reference} · Transfer to verify",
            body=(
                f"{order.contact_name} · {claim.amount} {order.currency} · "
                f"****{claim.reference_last4}"
            ),
            url=f"/web-orders/?ref={order.reference}",
            tag=f"web-order-pay-{claim.pk}",
        )


def _closed(claim):
    if claim.status != PublicOrderPayment.VERIFYING:
        raise ValidationError({"detail": _("This claim was already answered.")})


def _decide(claim, actor, status, note):
    claim.status = status
    claim.decided_by = actor
    claim.decided_at = timezone.now()
    claim.decision_note = note
    claim.save()


def _check_surplus(claim, due, surplus_returned):
    """A transfer larger than what is owed is refused until the manager
    decides, instead of being silently cut to the balance.

    Keeping the surplus as store credit was considered and not done: a
    payment cannot exceed its invoice, so the extra money would appear
    nowhere in the bank account's recorded receipts while the customer held
    spendable credit for it — the books would stop reconciling with the
    bank, and a credit note outside a return is a manager's decision, not
    a side effect of a confirmation. The manager either returns the
    difference to the customer (``surplus_returned``: only the balance due
    is recorded) or rejects the claim and asks for a transfer that matches.
    Returns the amount to record."""
    if due <= 0:
        raise ValidationError({
            "code": "already_paid",
            "detail": _("This order is already paid in full. Reject this claim and return "
                        "the transfer to the customer."),
        })
    if claim.amount <= due:
        return claim.amount
    if not surplus_returned:
        raise ValidationError({
            "code": "overpayment",
            "detail": _(
                "The transfer (%(amount)s) is %(surplus)s more than the %(due)s still owed on "
                "this order. Confirm only %(due)s and return the difference to the customer, "
                "or reject the claim and ask for a transfer that matches."
            ) % {"amount": claim.amount, "surplus": claim.amount - due, "due": due},
            "amount": str(claim.amount), "due": str(due), "surplus": str(claim.amount - due),
        })
    return due


@transaction.atomic
def confirm_payment(claim, actor, request, warehouse=None, note="", surplus_returned=False):
    """The money is in the bank: invoice the order, deduct stock, record the
    verified bank transfer. Returns the claim with ``invoice`` set.

    A transfer above what is owed is refused (code ``overpayment``) unless
    ``surplus_returned`` says the manager is handing the difference back;
    then only the balance due is recorded and the surplus is logged."""
    from core.rbac import can_approve_high_value
    from inventory.models import Warehouse
    from sales.models import Payment
    from sales.serializers import POSCheckoutSerializer
    from website.orders import confirm as confirm_order

    claim = PublicOrderPayment.objects.select_for_update().get(pk=claim.pk)
    _closed(claim)
    order = claim.order
    if order.status == PublicOrder.NEW:
        order = confirm_order(order, actor, note)
    if order.status not in PublicOrder.CONFIRMED_ONWARD or order.sales_order is None:
        raise ValidationError({"detail": _("Only a confirmed order can be paid.")})
    threshold = getattr(order.company, "payment_approval_threshold", 0) or 0
    if threshold and claim.amount >= threshold and not can_approve_high_value(actor):
        raise ValidationError({
            "code": "approval_required",
            "detail": _("Confirming a transfer of this size needs an approver (owner, GM or CFO)."),
        })
    sales_order = order.sales_order
    if warehouse is None:
        candidates = Warehouse.objects.filter(company=order.company, is_active=True)
        warehouse = (
            candidates.filter(branch_id=order.branch_id).first() if order.branch_id else None
        ) or candidates.first()
        if warehouse is None:
            raise ValidationError({"warehouse": _("Create a warehouse to sell from first.")})
    if sales_order.status == sales_order.CONFIRMED:
        # The checkout invoices the order's lines at the order's tax, so the
        # invoice total is the sales order's total.
        amount = _check_surplus(claim, sales_order.total, surplus_returned)
        serializer = POSCheckoutSerializer(
            data={
                "customer": sales_order.customer_id,
                "branch": order.branch_id,
                "warehouse": warehouse.pk,
                "source_order": sales_order.pk,
                "lines": [
                    {"product": line.product_id, "quantity": str(line.quantity),
                     "unit_price": str(line.unit_price)}
                    for line in sales_order.lines.all()
                ],
                "payment": {
                    "method": Payment.BANK_TRANSFER,
                    "company_bank_account": claim.bank_account_id,
                    "sender_bank_name": claim.sender_bank_name,
                    "reference_last4": claim.reference_last4,
                    "amount": str(amount),
                },
            },
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        payment = invoice.payments.filter(method=Payment.BANK_TRANSFER).order_by("-pk").first()
    else:
        # Already invoiced (a second transfer on the same order): record the
        # payment on that invoice.
        invoice = sales_order.invoices.order_by("-pk").first()
        if invoice is None:
            raise ValidationError({"detail": _("This order was fulfilled without an invoice.")})
        # Through the one payment service: locked, capped at the balance due
        # (review F01: 800 + 800 on a 1,000 order used to be accepted), the
        # currency taken from the invoice. The shop's confirmation stays the
        # verification, as decided.
        from sales.models import Invoice
        from sales.payments import record_payment

        locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
        amount = _check_surplus(claim, locked.amount_due(), surplus_returned)
        payment = record_payment(
            invoice, amount=amount, method=Payment.BANK_TRANSFER,
            recorded_by=actor, company_bank_account=claim.bank_account,
            sender_bank_name=claim.sender_bank_name, reference_last4=claim.reference_last4,
        )
    if payment is not None and payment.verified_at is None:
        payment.verified_at = timezone.now()
        payment.verified_by = actor
        payment.save(update_fields=["verified_at", "verified_by"])
    claim.payment = payment
    claim.invoice = invoice
    surplus = claim.amount - amount
    if surplus > 0:
        note = " · ".join(p for p in (note, _(
            "%(surplus)s above the balance is being returned to the customer."
        ) % {"surplus": surplus}) if p)
    _decide(claim, actor, PublicOrderPayment.CONFIRMED, note)
    log_activity(
        action="public_payment_confirmed", request=request, entity_type="PublicOrderPayment",
        entity_id=claim.pk,
        metadata={"reference": order.reference, "invoice": invoice.pk,
                  "recorded": str(amount), "surplus_returned": str(surplus)},
    )
    return claim


@transaction.atomic
def reject_payment(claim, actor, request, note=""):
    claim = PublicOrderPayment.objects.select_for_update().get(pk=claim.pk)
    _closed(claim)
    _decide(claim, actor, PublicOrderPayment.REJECTED, note)
    log_activity(
        action="public_payment_rejected", request=request, entity_type="PublicOrderPayment",
        entity_id=claim.pk, metadata={"reference": claim.order.reference},
    )
    return claim


@transaction.atomic
def flag_fraud(claim, actor, request, note=""):
    claim = PublicOrderPayment.objects.select_for_update().get(pk=claim.pk)
    _closed(claim)
    _decide(claim, actor, PublicOrderPayment.FRAUD, note)
    order = claim.order
    BlockedContact.objects.create(
        company=order.company, phone=order.phone,
        visitor_hash=claim.visitor_hash or order.visitor_hash,
        reason=note or f"fraudulent payment claim on {order.reference}", source=claim,
        created_by=actor,
    )
    if order.status == PublicOrder.NEW:
        order.status = PublicOrder.REJECTED
        order.decided_by = actor
        order.decided_at = timezone.now()
        order.decision_note = note or "fraud"
        order.save()
        # No email to the customer: the claim was a deliberate lie.
        record_stage(order, PublicOrder.NEW, actor, order.decision_note, notify=False)
    log_activity(
        action="public_payment_fraud", request=request, entity_type="PublicOrderPayment",
        entity_id=claim.pk, metadata={"reference": order.reference, "phone": order.phone},
    )
    return claim
