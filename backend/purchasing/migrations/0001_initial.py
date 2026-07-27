import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("org", "0001_initial"),
        ("inventory", "0001_initial"),
        ("sales", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Supplier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("address", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="suppliers", to="org.company")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="PurchaseOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("draft", "Draft"), ("sent", "Sent"), ("confirmed", "Confirmed"), ("partially_received", "Partially Received"), ("received", "Received"), ("cancelled", "Cancelled")], default="draft", max_length=20)),
                ("expected_date", models.DateField(blank=True, null=True)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_orders", to="org.branch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="purchase_orders", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_orders", to=settings.AUTH_USER_MODEL)),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_orders", to="purchasing.supplier")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PurchaseOrderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(blank=True, max_length=255)),
                ("quantity_ordered", models.DecimalField(decimal_places=3, max_digits=16)),
                ("unit_cost", models.DecimalField(decimal_places=2, max_digits=14)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=16)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="po_lines", to="inventory.product")),
                ("purchase_order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="purchasing.purchaseorder")),
            ],
        ),
        migrations.CreateModel(
            name="GoodsReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("note", models.CharField(blank=True, max_length=255)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="goods_receipts", to="org.company")),
                ("purchase_order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="goods_receipts", to="purchasing.purchaseorder")),
                ("received_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="goods_receipts", to=settings.AUTH_USER_MODEL)),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="goods_receipts", to="purchasing.supplier")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="goods_receipts", to="inventory.warehouse")),
            ],
            options={"ordering": ["-received_at"]},
        ),
        migrations.CreateModel(
            name="GoodsReceiptLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("unit_cost", models.DecimalField(decimal_places=2, max_digits=14)),
                ("batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="receipt_lines", to="inventory.stockbatch")),
                ("movement", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="receipt_line", to="inventory.stockmovement")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="receipt_lines", to="inventory.product")),
                ("receipt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="purchasing.goodsreceipt")),
            ],
        ),
        migrations.CreateModel(
            name="Bill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("supplier_invoice_number", models.CharField(blank=True, max_length=64)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("total", models.DecimalField(decimal_places=2, max_digits=16)),
                ("is_void", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bills", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bills", to=settings.AUTH_USER_MODEL)),
                ("goods_receipt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bills", to="purchasing.goodsreceipt")),
                ("purchase_order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bills", to="purchasing.purchaseorder")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bills", to="purchasing.supplier")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SupplierPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("method", models.CharField(choices=[("cash", "Cash"), ("bank_transfer", "Bank Transfer")], max_length=16)),
                ("reference_last4", models.CharField(blank=True, max_length=4)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=16)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("bill", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="purchasing.bill")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supplier_payments", to="org.company")),
                ("from_bank_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="supplier_payments", to="sales.companybankaccount")),
                ("recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supplier_payments_recorded", to=settings.AUTH_USER_MODEL)),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="purchasing.supplier")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supplier_payments_verified", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-recorded_at"]},
        ),
    ]
