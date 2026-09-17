from django.conf import settings
from django.db import models


class SyncBatch(models.Model):
    """
    One push from an offline client. Append-only, idempotent at batch level via
    `batch_uuid`: re-pushing the same batch returns the stored per-operation
    results instead of re-applying anything. Individual operations are ALSO
    idempotent (each op's own client_uuid), so even a partial re-push is safe.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="sync_batches"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sync_batches",
    )
    device_id = models.CharField(max_length=128, blank=True)
    batch_uuid = models.UUIDField(unique=True)
    operation_count = models.PositiveIntegerField(default=0)
    applied_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"SyncBatch<{self.batch_uuid}>"


class SyncOperation(models.Model):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    ERROR = "error"

    batch = models.ForeignKey(
        SyncBatch, on_delete=models.CASCADE, related_name="operations"
    )
    index = models.PositiveIntegerField()
    op_type = models.CharField(max_length=64)
    client_uuid = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16)
    result_model = models.CharField(max_length=64, blank=True)
    result_id = models.CharField(max_length=64, blank=True)
    error_detail = models.TextField(blank=True)

    class Meta:
        ordering = ["batch", "index"]
        constraints = [
            # Two resumes of a partial batch must not each insert a result row
            # for the same slot and inflate the counts.
            models.UniqueConstraint(fields=["batch", "index"], name="uniq_sync_op_per_slot")
        ]

    def as_result(self):
        return {
            "index": self.index,
            "op_type": self.op_type,
            "client_uuid": str(self.client_uuid) if self.client_uuid else None,
            "status": self.status,
            "id": int(self.result_id) if self.result_id.isdigit() else None,
            "error": self.error_detail or None,
        }


class DiscardedOperation(models.Model):
    """
    A queued operation the device gave up on. The sale, receipt or return it
    describes physically happened; the server rejected the replay and would
    keep rejecting it. Rather than leave a red counter on the till for ever,
    the cashier discards it WITH a reason, and this row keeps the evidence —
    the exact payload, the server's error, who dropped it and why — for a
    manager to act on (re-key it, adjust stock, refund). Append-only.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="discarded_operations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="discarded_operations",
    )
    branch = models.ForeignKey(
        "org.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="discarded_operations",
    )
    device_id = models.CharField(max_length=128, blank=True)
    client_uuid = models.UUIDField()
    op_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    # A manager marks it handled once the books reflect what happened.
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="discarded_operations_resolved",
    )
    resolution = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "client_uuid"], name="uniq_discarded_op_per_company"
            )
        ]

    def __str__(self):
        return f"Discarded {self.op_type} {self.client_uuid}"
