import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("org", "0001_initial"),
        ("inventory", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("address", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="customers", to="org.company")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="CompanyBankAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bank_name", models.CharField(max_length=255)),
                ("account_name", models.CharField(max_length=255)),
                ("account_number", models.CharField(blank=True, max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bank_accounts", to="org.company")),
            ],
            options={"ordering": ["bank_name"]},
        ),
        migrations.CreateModel(
            name="InvoiceSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_number", models.PositiveIntegerField(default=0)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="invoice_sequence", to="org.company")),
            ],
        ),
        migrations.CreateModel(
            name="Quotation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted"), ("expired", "Expired"), ("converted", "Converted")], default="draft", max_length=16)),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="quotations", to="org.branch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quotations", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="quotations", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="quotations", to="sales.customer")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="QuotationLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(blank=True, max_length=255)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=16)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="quotation_lines", to="inventory.product")),
                ("quotation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="sales.quotation")),
            ],
        ),
        migrations.CreateModel(
            name="SalesOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("draft", "Draft"), ("confirmed", "Confirmed"), ("fulfilled", "Fulfilled"), ("cancelled", "Cancelled")], default="draft", max_length=16)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_orders", to="org.branch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_orders", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_orders", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales_orders", to="sales.customer")),
                ("source_quotation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sales_orders", to="sales.quotation")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SalesOrderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(blank=True, max_length=255)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=16)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales_order_lines", to="inventory.product")),
                ("sales_order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="sales.salesorder")),
            ],
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField()),
                ("currency", models.CharField(default="SDG", max_length=8)),
                ("exchange_rate", models.DecimalField(decimal_places=6, default=1, max_digits=14)),
                ("tax_rate_snapshot", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("is_void", models.BooleanField(default=False)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoices", to="org.branch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoices", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoices", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="sales.customer")),
                ("source_order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoices", to="sales.salesorder")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="inventory.warehouse")),
            ],
            options={"ordering": ["-number"]},
        ),
        migrations.CreateModel(
            name="InvoiceLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(blank=True, max_length=255)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("tax_rate", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("line_subtotal", models.DecimalField(decimal_places=2, max_digits=16)),
                ("line_tax", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=16)),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="sales.invoice")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoice_lines", to="inventory.product")),
            ],
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("method", models.CharField(choices=[("cash", "Cash"), ("bank_transfer", "Bank Transfer")], max_length=16)),
                ("sender_bank_name", models.CharField(blank=True, max_length=255)),
                ("reference_last4", models.CharField(blank=True, max_length=4)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=16)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="org.company")),
                ("company_bank_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="sales.companybankaccount")),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="sales.invoice")),
                ("recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments_recorded", to=settings.AUTH_USER_MODEL)),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments_verified", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-recorded_at"]},
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.UniqueConstraint(fields=("company", "number"), name="uniq_invoice_number_per_company"),
        ),
    ]
