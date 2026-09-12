from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sales", "0004_cashshift_cashdrawermovement_payment_shift_and_more")]
    operations = [
        migrations.AddField(
            model_name="customer", name="updated_at", field=models.DateTimeField(auto_now=True)
        ),
        migrations.AddField(
            model_name="invoice", name="updated_at", field=models.DateTimeField(auto_now=True)
        ),
    ]
