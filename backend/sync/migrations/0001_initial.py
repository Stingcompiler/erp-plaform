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
            name="SyncBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(blank=True, max_length=128)),
                ("batch_uuid", models.UUIDField(unique=True)),
                ("operation_count", models.PositiveIntegerField(default=0)),
                ("applied_count", models.PositiveIntegerField(default=0)),
                ("duplicate_count", models.PositiveIntegerField(default=0)),
                ("error_count", models.PositiveIntegerField(default=0)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sync_batches", to="org.company")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sync_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-received_at"]},
        ),
        migrations.CreateModel(
            name="SyncOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("index", models.PositiveIntegerField()),
                ("op_type", models.CharField(max_length=64)),
                ("client_uuid", models.UUIDField(blank=True, null=True)),
                ("status", models.CharField(max_length=16)),
                ("result_model", models.CharField(blank=True, max_length=64)),
                ("result_id", models.CharField(blank=True, max_length=64)),
                ("error_detail", models.TextField(blank=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operations", to="sync.syncbatch")),
            ],
            options={"ordering": ["batch", "index"]},
        ),
    ]
