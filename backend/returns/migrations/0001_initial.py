import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("org", "0001_initial"),
        ("inventory", "0001_initial"),
        ("sales", "0001_initial"),
        ("purchasing", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesReturn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_returns", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_returns", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sales_returns", to="sales.customer")),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales_returns", to="sales.invoice")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SalesReturnLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("disposition", models.CharField(choices=[("quarantine", "Quarantine (pending)"), ("restocked", "Restocked to sellable"), ("scrapped", "Scrapped / written off")], default="quarantine", max_length=16)),
                ("invoice_line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="return_lines", to="sales.invoiceline")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="return_lines", to="inventory.product")),
                ("restock_movement", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sales_return_line", to="inventory.stockmovement")),
                ("restock_warehouse", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="restocked_return_lines", to="inventory.warehouse")),
                ("sales_return", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="returns.salesreturn")),
            ],
        ),
        migrations.CreateModel(
            name="PurchaseReturn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="purchase_returns", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_returns", to=settings.AUTH_USER_MODEL)),
                ("goods_receipt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_returns", to="purchasing.goodsreceipt")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_returns", to="purchasing.supplier")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_returns", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PurchaseReturnLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_return_lines", to="inventory.stockbatch")),
                ("movement", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_return_line", to="inventory.stockmovement")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_return_lines", to="inventory.product")),
                ("purchase_return", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="returns.purchasereturn")),
            ],
        ),
        migrations.CreateModel(
            name="CreditNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=16)),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("is_void", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="credit_notes", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="credit_notes", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="credit_notes", to="sales.customer")),
                ("invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="credit_notes", to="sales.invoice")),
                ("sales_return", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="credit_notes", to="returns.salesreturn")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DebitNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=16)),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("is_void", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("bill", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="debit_notes", to="purchasing.bill")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="debit_notes", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="debit_notes", to=settings.AUTH_USER_MODEL)),
                ("purchase_return", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="debit_notes", to="returns.purchasereturn")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="debit_notes", to="purchasing.supplier")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
