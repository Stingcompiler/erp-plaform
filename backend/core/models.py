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
        ]

    def __str__(self):
        who = self.user_id or "system"
        return f"ActivityLog<{self.action} by {who} @ {self.created_at:%Y-%m-%d %H:%M}>"


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
