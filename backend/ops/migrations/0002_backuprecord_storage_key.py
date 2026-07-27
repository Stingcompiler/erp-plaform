from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="backuprecord",
            name="storage_key",
            field=models.CharField(blank=True, max_length=512),
        ),
    ]
