from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0002_bill_due_date_bill_payment_terms_days")]
    operations = [
        migrations.AddField(
            model_name="supplier", name="updated_at", field=models.DateTimeField(auto_now=True)
        ),
    ]
