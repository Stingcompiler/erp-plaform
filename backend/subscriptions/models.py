import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

# What a plan may cap. The counted ones have a resolver in
# subscriptions.services.LIMIT_RESOLVERS; storage_mb is priced, not counted.
LIMIT_KEYS = ("users", "branches", "warehouses", "devices", "storage_mb")


class Plan(models.Model):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    # Marketing copy for the public pricing page. `name`/`description` are the
    # operator's working labels; these are what a visitor reads, in both
    # languages, with one feature per line so the card can render a list.
    name_ar = models.CharField(max_length=120, blank=True)
    tagline_en = models.CharField(max_length=160, blank=True)
    tagline_ar = models.CharField(max_length=160, blank=True)
    features_en = models.TextField(blank=True, help_text="One feature per line.")
    features_ar = models.TextField(blank=True, help_text="One feature per line.")
    is_highlighted = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PlanVersion(models.Model):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    BILLING_CYCLES = [(MONTHLY, "Monthly"), (YEARLY, "Yearly")]

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    currency = models.CharField(max_length=8, default="USD")
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    billing_cycle = models.CharField(
        max_length=16, choices=BILLING_CYCLES, default=MONTHLY
    )
    modules = models.JSONField(default=list, blank=True)
    limits = models.JSONField(default=dict, blank=True)
    is_legacy = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["plan__name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "version"], name="uniq_plan_version"
            )
        ]

    def __str__(self):
        return f"{self.plan.name} v{self.version}"

    def clean(self):
        allowed = {
            "*",
            "users",
            "org",
            "inventory",
            "sales",
            "purchasing",
            "sales_returns",
            "purchase_returns",
            "reports",
            "hr",
            "crm",
            "finance",
            "website",
            "settings",
        }
        modules = set(self.modules or [])
        unknown = modules - allowed
        if unknown:
            raise ValidationError(
                {"modules": f"Unknown modules: {', '.join(sorted(unknown))}"}
            )
        dependencies = {
            "sales_returns": {"sales", "inventory"},
            "purchase_returns": {"purchasing", "inventory"},
        }
        if "*" not in modules:
            for module, required in dependencies.items():
                missing = required - modules if module in modules else set()
                if missing:
                    names = ", ".join(sorted(missing))
                    raise ValidationError(
                        {"modules": f"{module} also requires {names}."}
                    )
        for name, value in (self.limits or {}).items():
            if name not in LIMIT_KEYS:
                raise ValidationError({"limits": f"Unknown limit: {name}"})
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationError(
                    {"limits": f"{name} must be a non-negative integer."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.pk:
            previous = PlanVersion.objects.filter(pk=self.pk).first()
            locked = previous and (
                previous.published_at or previous.subscriptions.exists()
            )
            fields = (
                "plan_id",
                "version",
                "currency",
                "price",
                "billing_cycle",
                "modules",
                "limits",
                "is_legacy",
            )
            if locked and any(
                getattr(previous, field) != getattr(self, field) for field in fields
            ):
                raise ValidationError(
                    "A published or used plan version is immutable; create a new version."
                )
        super().save(*args, **kwargs)


class Subscription(models.Model):
    TRIALING = "trialing"
    ACTIVE = "active"
    GRACE = "grace"
    READ_ONLY = "read_only"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    LEGACY = "legacy"
    STATES = [
        (value, value.replace("_", " ").title())
        for value in (TRIALING, ACTIVE, GRACE, READ_ONLY, SUSPENDED, CANCELLED, LEGACY)
    ]

    company = models.OneToOneField(
        "org.Company", on_delete=models.CASCADE, related_name="subscription"
    )
    plan_version = models.ForeignKey(
        PlanVersion, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(max_length=16, choices=STATES, default=TRIALING)
    starts_at = models.DateTimeField()
    period_ends_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    suspended_reason = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name"]


class SubscriptionEvent(models.Model):
    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(max_length=48)
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16, blank=True)
    reason = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class SubscriptionInvoice(models.Model):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"
    STATES = [(DRAFT, "Draft"), (ISSUED, "Issued"), (PAID, "Paid"), (VOID, "Void")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.PROTECT, related_name="subscription_invoices"
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name="invoices"
    )
    number = models.CharField(max_length=48, unique=True)
    status = models.CharField(max_length=12, choices=STATES, default=DRAFT)
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=8)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    due_at = models.DateTimeField()
    line_snapshot = models.JSONField(default=list)
    issued_at = models.DateTimeField(null=True, blank=True)
    # Marks the commercial period as granted. This is separate from `paid`: a
    # paid invoice may be historical, and replaying payment review must never
    # extend access a second time.
    entitlement_granted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0), name="subscription_invoice_amount_nonnegative"
            )
        ]


class SubscriptionPayment(models.Model):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    STATES = [(PENDING, "Pending"), (VERIFIED, "Verified"), (REJECTED, "Rejected")]
    METHODS = [("cash", "Cash"), ("bank_transfer", "Bank transfer")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.PROTECT, related_name="subscription_payments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8)
    method = models.CharField(max_length=20, choices=METHODS)
    sender_bank_name = models.CharField(max_length=120, blank=True)
    reference_last4 = models.CharField(max_length=4, blank=True)
    proof = models.FileField(upload_to="subscription-proofs/%Y/%m/", blank=True)
    status = models.CharField(max_length=12, choices=STATES, default=PENDING)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_subscription_payments",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="verified_subscription_payments",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="subscription_payment_amount_positive"
            )
        ]

    def clean(self):
        if self.method == "bank_transfer" and len(self.reference_last4) != 4:
            raise ValidationError(
                {"reference_last4": "Enter the last four reference characters."}
            )


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        SubscriptionPayment, on_delete=models.PROTECT, related_name="allocations"
    )
    invoice = models.ForeignKey(
        SubscriptionInvoice, on_delete=models.PROTECT, related_name="allocations"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "invoice"], name="uniq_subscription_payment_invoice"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="subscription_allocation_positive"
            ),
        ]

    def clean(self):
        if (
            self.payment_id
            and self.invoice_id
            and self.payment.company_id != self.invoice.company_id
        ):
            raise ValidationError(
                "Payment and invoice must belong to the same company."
            )


class EntitlementOverride(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="entitlement_overrides"
    )
    modules = models.JSONField(default=list, blank=True)
    limits = models.JSONField(default=dict, blank=True)
    allow_writes = models.BooleanField(null=True, blank=True)
    reason = models.TextField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="override_end_after_start",
            )
        ]


class PlanChangeRequest(models.Model):
    """An owner asking to move to another plan.

    The commercial rules live in subscriptions.plan_changes: an upgrade is
    invoiced for the rest of the current period and switches when that
    invoice is paid; a downgrade waits for the period to end and is refused
    while the company uses more than the target plan allows. The row keeps
    who asked, who decided and what came of it.
    """

    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    KINDS = [(UPGRADE, "Upgrade"), (DOWNGRADE, "Downgrade")]

    PENDING = "pending"
    APPROVED = "approved"   # waiting: for payment (upgrade) or period end (downgrade)
    APPLIED = "applied"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STATES = [
        (PENDING, "Pending"), (APPROVED, "Approved"), (APPLIED, "Applied"),
        (REJECTED, "Rejected"), (CANCELLED, "Cancelled"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="plan_change_requests"
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="change_requests"
    )
    from_version = models.ForeignKey(
        PlanVersion, on_delete=models.PROTECT, related_name="+"
    )
    to_version = models.ForeignKey(
        PlanVersion, on_delete=models.PROTECT, related_name="+"
    )
    kind = models.CharField(max_length=12, choices=KINDS)
    status = models.CharField(max_length=12, choices=STATES, default=PENDING)
    note = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    # Upgrade: the prorated difference to pay before the switch.
    invoice = models.OneToOneField(
        SubscriptionInvoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="plan_change",
    )
    # Downgrade: when the switch is due (the current period's end).
    apply_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # One open request per company: the answer to "what did they ask
            # for" must never be two rows.
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(status__in=["pending", "approved"]),
                name="one_open_plan_change_per_company",
            )
        ]
