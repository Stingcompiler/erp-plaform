from django.conf import settings
from django.db import models


class BackupRecord(models.Model):
    """
    Audit row for every backup and restore (PROJECT_RULES Rule #8 lists backups
    and restores explicitly). Append-only.
    """

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    RESTORE = "restore"
    KIND_CHOICES = [(MANUAL, "Manual"), (SCHEDULED, "Scheduled"), (RESTORE, "Restore")]

    SUCCESS = "success"
    FAILED = "failed"
    STATUS_CHOICES = [(SUCCESS, "Success"), (FAILED, "Failed")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="backup_records",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    record_count = models.PositiveIntegerField(default=0)
    size_bytes = models.PositiveIntegerField(default=0)
    # Object-storage key when the payload was pushed off-box (S3/R2); blank when
    # durable storage isn't configured and only metadata was recorded.
    storage_key = models.CharField(max_length=512, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="backup_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"BackupRecord<{self.kind}/{self.status} {self.created_at:%Y-%m-%d}>"


class UserPreference(models.Model):
    """Per-user UI preferences: language (drives RTL) and theme."""

    EN = "en"
    AR = "ar"
    LANGUAGE_CHOICES = [(EN, "English"), (AR, "Arabic")]

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"
    THEME_CHOICES = [(LIGHT, "Light"), (DARK, "Dark"), (SYSTEM, "System")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preference"
    )
    language = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default=EN)
    theme = models.CharField(max_length=8, choices=THEME_CHOICES, default=SYSTEM)

    @property
    def direction(self):
        return "rtl" if self.language == self.AR else "ltr"

    def __str__(self):
        return f"Preference<{self.user_id}: {self.language}/{self.theme}>"
