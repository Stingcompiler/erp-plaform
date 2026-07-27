import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("org", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Brand",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="brands", to="org.company")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="categories", to="org.company")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="children", to="inventory.category")),
            ],
            options={"verbose_name_plural": "categories", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Unit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64)),
                ("symbol", models.CharField(blank=True, max_length=16)),
                ("is_active", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="units", to="org.company")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Warehouse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("code", models.CharField(blank=True, max_length=32)),
                ("is_active", models.BooleanField(default=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="warehouses", to="org.branch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouses", to="org.company")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("barcode", models.CharField(blank=True, max_length=128)),
                ("qr_code", models.CharField(blank=True, max_length=255)),
                ("cost_price", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("sale_price", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("reorder_level", models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ("track_batches", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("brand", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="inventory.brand")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="inventory.category")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="products", to="org.company")),
                ("unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="inventory.unit")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="StockBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("lot_number", models.CharField(max_length=128)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_batches", to="org.company")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="batches", to="inventory.product")),
            ],
            options={"verbose_name_plural": "stock batches", "ordering": ["expiry_date", "lot_number"]},
        ),
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("movement_type", models.CharField(choices=[("purchase_in", "Purchase In"), ("sale_out", "Sale Out"), ("adjustment", "Adjustment"), ("transfer", "Transfer"), ("sales_return_in", "Sales Return In"), ("purchase_return_out", "Purchase Return Out")], max_length=32)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("unit_cost", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("reference_type", models.CharField(blank=True, max_length=64)),
                ("reference_id", models.CharField(blank=True, max_length=64)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="inventory.stockbatch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_movements", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_movements", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="inventory.product")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="StockAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="adjustments", to="inventory.stockbatch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_adjustments", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_adjustments", to=settings.AUTH_USER_MODEL)),
                ("movement", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="adjustment", to="inventory.stockmovement")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="adjustments", to="inventory.product")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="adjustments", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="StockTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=16)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("client_uuid", models.UUIDField(blank=True, null=True, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="transfers", to="inventory.stockbatch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_transfers", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_transfers", to=settings.AUTH_USER_MODEL)),
                ("dest_movement", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="transfer_dest", to="inventory.stockmovement")),
                ("dest_warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers_in", to="inventory.warehouse")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers", to="inventory.product")),
                ("source_movement", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="transfer_source", to="inventory.stockmovement")),
                ("source_warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers_out", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="brand",
            constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_brand_name_per_company"),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_category_name_per_company"),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_unit_name_per_company"),
        ),
        migrations.AddConstraint(
            model_name="warehouse",
            constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_warehouse_name_per_company"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(fields=("company", "sku"), name="uniq_product_sku_per_company"),
        ),
        migrations.AddConstraint(
            model_name="stockbatch",
            constraint=models.UniqueConstraint(fields=("company", "product", "lot_number"), name="uniq_batch_lot_per_product"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["company", "product", "warehouse"], name="stockmove_co_prod_wh_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["movement_type"], name="stockmove_type_idx"),
        ),
    ]
