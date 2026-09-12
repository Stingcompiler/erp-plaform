from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0002_bill_due_date_bill_payment_terms_days"), ("returns", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="purchasereturnline",
            name="goods_receipt_line",
            field=models.ForeignKey(
                blank=True,
                help_text="Original received line; null is reserved for legacy records.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="return_lines",
                to="purchasing.goodsreceiptline",
            ),
        ),
        migrations.AlterField(
            model_name="creditnote",
            name="customer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="credit_notes",
                to="sales.customer",
            ),
        ),
    ]
