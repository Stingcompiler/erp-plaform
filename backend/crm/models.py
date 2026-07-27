"""
CRM domain models (M6): CustomerGroup, Lead, FollowUp, Note.

All models are company-scoped (Rule #1) via a direct `company` FK, so the
shared CompanyScopedModelViewSet filters and forces tenancy uniformly — the
same pattern every other module uses. FollowUp and Note carry their own
`company` FK (denormalized from their parent Lead) so they scope directly
without a join, exactly as their viewsets expect.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models


class CustomerGroup(models.Model):
    """A segment/category for grouping leads and customers (e.g. 'Wholesale',
    'VIP'). Company-scoped master data referenced by leads."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="customer_groups"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # Optional UI accent (hex) so the frontend can color-code segments.
    color = models.CharField(max_length=16, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Lead(models.Model):
    """A prospective sale moving through the pipeline. `stage` is the pipeline
    position; transitions are just field updates (append-only history lives in
    the ActivityLog + the FollowUp/Note timeline)."""

    STAGE_NEW = "new"
    STAGE_CONTACTED = "contacted"
    STAGE_QUALIFIED = "qualified"
    STAGE_PROPOSAL = "proposal"
    STAGE_WON = "won"
    STAGE_LOST = "lost"
    STAGE_CHOICES = [
        (STAGE_NEW, "New"),
        (STAGE_CONTACTED, "Contacted"),
        (STAGE_QUALIFIED, "Qualified"),
        (STAGE_PROPOSAL, "Proposal sent"),
        (STAGE_WON, "Won"),
        (STAGE_LOST, "Lost"),
    ]
    # Stages that close a lead — used to keep the active pipeline uncluttered.
    CLOSED_STAGES = {STAGE_WON, STAGE_LOST}

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="leads"
    )
    # Optional branch dimension enables row-level branch visibility on the
    # viewset (branch_field="branch"), consistent with sales/inventory.
    branch = models.ForeignKey(
        "org.Branch",
        on_delete=models.SET_NULL,
        related_name="leads",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=120, blank=True)
    stage = models.CharField(
        max_length=16, choices=STAGE_CHOICES, default=STAGE_NEW
    )
    estimated_value = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0")
    )
    customer_group = models.ForeignKey(
        CustomerGroup,
        on_delete=models.SET_NULL,
        related_name="leads",
        null=True,
        blank=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_leads",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        return self.stage not in self.CLOSED_STAGES


class FollowUp(models.Model):
    """A scheduled next-action on a lead (call, meeting, email). Completing it
    is a status flip; overdue open follow-ups drive the CRM dashboard."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="crm_followups"
    )
    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="followups"
    )
    due_date = models.DateField()
    summary = models.CharField(max_length=255)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="crm_followups",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["done", "due_date"]

    def __str__(self):
        return f"{self.summary} ({self.due_date})"


class Note(models.Model):
    """A freeform, timestamped note on a lead — the activity trail."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="crm_notes"
    )
    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="notes"
    )
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="crm_notes",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note<{self.lead_id}: {self.body[:32]}>"
