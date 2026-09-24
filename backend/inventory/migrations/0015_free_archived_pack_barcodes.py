"""Archived packs give their barcode back.

From now on archiving a pack clears its barcode (ProductPackSerializer), so a
new pack or product can take the code. Packs archived before that still hold
theirs and would block it; free them the same way. Data only, no schema.
"""
from django.db import migrations


def free_barcodes(apps, schema_editor):
    ProductPack = apps.get_model("inventory", "ProductPack")
    ProductPack.objects.filter(is_active=False).exclude(barcode="").update(barcode="")


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0014_stockcount_counted_at"),
    ]

    operations = [
        migrations.RunPython(free_barcodes, migrations.RunPython.noop),
    ]
