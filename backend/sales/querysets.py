from decimal import Decimal
from django.db.models import DecimalField, F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


def overdue_invoices(qs):
    """Outstanding balances without multiplying payments by credit-note joins."""
    from returns.models import CreditNote
    from sales.models import Payment
    money = DecimalField(max_digits=20, decimal_places=2)
    paid = Payment.objects.filter(invoice_id=OuterRef("pk")).order_by().values(
        "invoice_id").annotate(total=Sum("amount")).values("total")
    credited = CreditNote.objects.filter(
        invoice_id=OuterRef("pk"),
        is_void=False).order_by().values("invoice_id").annotate(
        total=Sum("amount")).values("total")
    return qs.filter(is_void=False, due_date__lt=timezone.localdate()).annotate(
        outstanding=F("total") - Coalesce(Subquery(paid), Decimal("0"), output_field=money)
        - Coalesce(Subquery(credited), Decimal("0"), output_field=money),
    ).filter(outstanding__gt=0)
