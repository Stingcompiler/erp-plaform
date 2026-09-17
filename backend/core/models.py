from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """
    Single audit table for every state-changing action (PROJECT_RULES Rule #8):
    login/logout, and create/update/delete on Product, Invoice, Payment,
    Return, User, permission changes, backups, restores, landing-page edits.

    Append-only by convention (Rule #9): rows are written, never updated or
    deleted. M1 wires login/logout + the User/Company/Branch/Department CRUD
    actions; later milestones call `log_activity` from their own viewsets.
    """

    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"

    # company is nullable so platform-level events (e.g. a Super Administrator
    # acting before a company context exists) can still be recorded.
    company = models.ForeignKey(
        "org.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=64)
    # Generic target reference so any model can be logged without a FK per type.
    entity_type = models.CharField(max_length=128, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "action"], name="actlog_company_action_idx"),
            models.Index(fields=["entity_type", "entity_id"], name="actlog_entity_idx"),
            # The log page and every per-user history read newest-first
            # within a company.
            models.Index(fields=["company", "-created_at"], name="actlog_company_created_idx"),
            models.Index(fields=["user", "-created_at"], name="actlog_user_created_idx"),
        ]

    def __str__(self):
        who = self.user_id or "system"
        return f"ActivityLog<{self.action} by {who} @ {self.created_at:%Y-%m-%d %H:%M}>"


class ActivityLogArchive(models.Model):
    """Cold storage for audit rows past the retention window.

    The audit trail is append-only and never discarded (PROJECT_RULES Rule
    #9), but the hot table backs the live log page and per-user histories,
    and its indexes should not grow forever. The nightly archival task
    (core.tasks.archive_activity_logs) moves rows older than
    ACTIVITY_LOG_RETENTION_DAYS here verbatim.

    Relations are stored as raw ids on purpose: an archive must outlive the
    company or user it mentions, so nothing here cascades or blocks a
    deletion. Rows are written once and read through the Django admin.
    """

    source_id = models.BigIntegerField(unique=True)
    company_id = models.BigIntegerField(null=True, blank=True)
    user_id = models.BigIntegerField(null=True, blank=True)
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=128, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["company_id", "-created_at"],
                name="actlogarc_company_created_idx",
            ),
        ]

    def __str__(self):
        return f"ActivityLogArchive<{self.action} #{self.source_id} @ {self.created_at:%Y-%m-%d}>"


class DocumentSequence(models.Model):
    """
    Per-company, per-document-type counter for formally numbered documents
    (credit notes, debit notes, and any future numbered document). Same
    contract as sales.InvoiceSequence: allocated under a row lock inside the
    caller's transaction, so a rolled-back document never burns a number and
    numbering stays sequential and gapless per company. Invoices keep their
    dedicated sequence for backwards compatibility.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="document_sequences"
    )
    doc_type = models.CharField(max_length=32)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "doc_type"], name="uniq_document_sequence_per_type"
            )
        ]

    def __str__(self):
        return f"{self.doc_type}@{self.company_id}={self.last_number}"


class AttentionSeen(models.Model):
    """When a user last opened a part of the app (see core/attention.py).

    The attention badge for `key` counts items that appeared after `seen_at`;
    this row is the only state the badges keep, so it is per user, per key,
    and overwritten on every visit.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="attention_seen"
    )
    key = models.CharField(max_length=48)
    seen_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="attention_seen_user_key")
        ]

    def __str__(self):
        return f"{self.user_id}:{self.key}@{self.seen_at:%Y-%m-%d %H:%M}"


class ErrorEvent(models.Model):
    """One kind of unhandled server error, deduplicated by fingerprint.

    Production errors were visible only in the host's process logs; this
    table is the first-party alternative to a Sentry account, read by the
    platform console. The middleware (core.error_monitor) folds repeats of
    the same fingerprint into one row with a count, so an error storm is a
    counter, not a table flood. Raw ids instead of FKs: an error report
    must never block deleting the user or company it mentions.
    """

    fingerprint = models.CharField(max_length=32, unique=True)
    exc_type = models.CharField(max_length=200)
    message = models.CharField(max_length=500, blank=True)
    path = models.CharField(max_length=300)
    method = models.CharField(max_length=8, blank=True)
    traceback = models.TextField(blank=True)
    user_id = models.BigIntegerField(null=True, blank=True)
    company_id = models.BigIntegerField(null=True, blank=True)
    count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen"]
        indexes = [models.Index(fields=["resolved_at", "-last_seen"], name="error_open_recent_idx")]

    def __str__(self):
        return f"ErrorEvent<{self.exc_type} {self.path} x{self.count}>"
