import uuid

from django.db import models


class Installation(models.Model):
    singleton_key = models.PositiveSmallIntegerField(
        default=1, unique=True, editable=False
    )
    installation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organisation_name = models.CharField(max_length=255, blank=True)
    deployment_mode = models.CharField(
        max_length=16, default="standalone", editable=False
    )
    application_version = models.CharField(max_length=40, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        installation = cls.objects.order_by("pk").first()
        return installation or cls.objects.create()


class LicenseActivation(models.Model):
    PERPETUAL = "perpetual"
    TERM = "term"
    KINDS = [(PERPETUAL, "Perpetual"), (TERM, "Fixed term")]

    installation = models.ForeignKey(
        Installation, on_delete=models.PROTECT, related_name="activations"
    )
    license_id = models.UUIDField(unique=True)
    organisation_name = models.CharField(max_length=255)
    kind = models.CharField(max_length=16, choices=KINDS)
    key_id = models.CharField(max_length=64)
    modules = models.JSONField(default=list)
    limits = models.JSONField(default=dict)
    usable_until = models.DateTimeField(null=True, blank=True)
    grace_until = models.DateTimeField(null=True, blank=True)
    maintenance_until = models.DateField(null=True, blank=True)
    max_application_version = models.CharField(max_length=40, blank=True)
    payload = models.JSONField()
    signature = models.TextField()
    activated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    activated_at = models.DateTimeField(auto_now_add=True)
    superseded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-activated_at"]
