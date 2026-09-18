"""Give existing credit sales the terms they were never given.

Until now the POS never set payment_terms_days, so every invoice was due
the day it was sold and every account sale showed as overdue from the
next morning. Recompute due_date for invoices that carry a customer and
zero terms, using the company default (30 days). Cash sales with no
customer are left alone — they are paid at the till.
"""

from datetime import timedelta

from django.db import migrations


def backfill(apps, schema_editor):
    Invoice = apps.get_model("sales", "Invoice")
    Company = apps.get_model("org", "Company")
    defaults = dict(Company.objects.values_list("pk", "default_payment_terms_days"))
    batch = []
    for inv in Invoice.objects.filter(
        customer__isnull=False, payment_terms_days=0, is_void=False
    ).only("pk", "company_id", "issued_at"):
        days = defaults.get(inv.company_id, 30)
        inv.payment_terms_days = days
        inv.due_date = inv.issued_at.date() + timedelta(days=days)
        batch.append(inv)
        if len(batch) >= 500:
            Invoice.objects.bulk_update(batch, ["payment_terms_days", "due_date"])
            batch = []
    if batch:
        Invoice.objects.bulk_update(batch, ["payment_terms_days", "due_date"])


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0014_customer_payment_terms_days"),
        ("org", "0010_company_default_payment_terms_days"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
