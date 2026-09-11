import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("website", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="PlatformLead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_uuid", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254)),
                ("message", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("new", "New"), ("contacted", "Contacted"), ("qualified", "Qualified"), ("closed", "Closed")], default="new", max_length=16)),
                ("source", models.CharField(default="platform-website", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
