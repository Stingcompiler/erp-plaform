from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("subscriptions", "0002_seed_legacy_entitlements")]

    operations = [
        migrations.AddField(
            model_name="subscriptioninvoice",
            name="entitlement_granted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
