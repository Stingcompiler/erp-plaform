# Generated manually to keep the registration workflow additive.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0002_platformlead"),
        ("org", "0007_storemodeaccessexception"),
        ("subscriptions", "0002_seed_legacy_entitlements"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistrationRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_uuid", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("company_name", models.CharField(max_length=255)),
                ("contact_name", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(max_length=64)),
                ("country", models.CharField(max_length=2)),
                ("timezone_name", models.CharField(default="UTC", max_length=64)),
                ("estimated_users", models.PositiveIntegerField(blank=True, null=True)),
                ("estimated_branches", models.PositiveIntegerField(blank=True, null=True)),
                ("delivery_mode", models.CharField(choices=[("saas", "Hosted SaaS"), ("standalone", "Standalone")], default="saas", max_length=16)),
                ("message", models.TextField(blank=True)),
                ("privacy_version", models.CharField(max_length=32)),
                ("status", models.CharField(choices=[("submitted", "Submitted"), ("under_review", "Under review"), ("needs_information", "Needs information"), ("approved", "Approved"), ("provisioned", "Provisioned"), ("rejected", "Rejected"), ("withdrawn", "Withdrawn")], default="submitted", max_length=20)),
                ("internal_note", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registration_request", to="org.company")),
                ("plan_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="registration_requests", to="subscriptions.planversion")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_registration_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="OwnerInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="owner_invitations", to=settings.AUTH_USER_MODEL)),
                ("registration_request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="owner_invitations", to="website.registrationrequest")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
