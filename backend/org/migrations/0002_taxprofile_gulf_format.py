from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("org", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="taxprofile",
            name="invoice_format",
            field=models.CharField(
                choices=[
                    ("simple", "Simple / plain invoice"),
                    ("gulf_vat", "Gulf VAT e-invoice (scaffold)"),
                ],
                default="simple",
                max_length=32,
            ),
        ),
    ]
