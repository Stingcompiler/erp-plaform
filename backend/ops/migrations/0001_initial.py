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
            name="BackupRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("manual", "Manual"), ("scheduled", "Scheduled"), ("restore", "Restore")], max_length=16)),
                ("status", models.CharField(choices=[("success", "Success"), ("failed", "Failed")], max_length=16)),
                ("record_count", models.PositiveIntegerField(default=0)),
                ("size_bytes", models.PositiveIntegerField(default=0)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="backup_records", to="org.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="backup_records", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="UserPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language", models.CharField(choices=[("en", "English"), ("ar", "Arabic")], default="en", max_length=8)),
                ("theme", models.CharField(choices=[("light", "Light"), ("dark", "Dark"), ("system", "System")], default="system", max_length=8)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="preference", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
