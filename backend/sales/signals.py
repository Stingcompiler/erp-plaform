"""Keep an invoice's change marker honest.

An invoice's balance and status are derived from append-only rows around
it — payments, credit notes, refunds — so the invoice row itself never
changes when it is paid. The sync pull keys invoices on ``updated_at``, so
without this an invoice paid after a device last synced stayed "unpaid" in
that device's mirror for ever (review F18). Every row that moves an
invoice's balance bumps the marker of the invoice(s) it touches.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone


def touch_invoices(invoice_ids):
    """Bump ``updated_at`` on these invoices without running save hooks."""
    from sales.models import Invoice

    ids = {pk for pk in invoice_ids if pk is not None}
    if ids:
        Invoice.objects.filter(pk__in=ids).update(updated_at=timezone.now())


def _touched_by(instance):
    """The invoices whose balance this row changes."""
    from returns.models import CreditNote
    from sales.models import Payment, Refund

    if isinstance(instance, Payment):
        # Store credit spent here also leaves the invoice the credit came from.
        ids = [instance.invoice_id]
        if instance.credit_note_id:
            ids.append(
                CreditNote.objects.filter(pk=instance.credit_note_id)
                .values_list("invoice_id", flat=True).first()
            )
        return ids
    if isinstance(instance, Refund):
        return [
            CreditNote.objects.filter(pk=instance.credit_note_id)
            .values_list("invoice_id", flat=True).first()
        ]
    if isinstance(instance, CreditNote):
        return [instance.invoice_id]
    return []


@receiver(post_save, sender="sales.Payment")
@receiver(post_save, sender="sales.Refund")
@receiver(post_save, sender="returns.CreditNote")
@receiver(post_delete, sender="sales.Payment")
@receiver(post_delete, sender="sales.Refund")
@receiver(post_delete, sender="returns.CreditNote")
def _balance_row_changed(sender, instance, **kwargs):
    if getattr(instance, "_restoring", False) or kwargs.get("raw"):
        return
    touch_invoices(_touched_by(instance))
