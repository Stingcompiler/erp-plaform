from django.db import models
from django.utils.text import slugify


class Company(models.Model):
    """
    A tenant business inside the single central deployment. Everything else
    in the system is isolated by `company_id` (PROJECT_RULES Rule #1).
    """

    # How much of the system this tenant needs on screen. A PRESENTATION preset
    # only — it collapses navigation, hides the warehouse picker and shortens
    # the role list, and changes no permission, no scoping rule and no
    # invariant. The RBAC matrix is untouched, so a shop that grows into a
    # multi-branch business becomes one by flipping this field rather than
    # migrating to a different product.
    TYPE_SHOP = "shop"
    TYPE_ENTERPRISE = "enterprise"
    BUSINESS_TYPE_CHOICES = [
        (TYPE_SHOP, "Single shop"),
        (TYPE_ENTERPRISE, "Multi-branch business"),
    ]

    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    # Used later by M8's auto-generated public site; unique per deployment.
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    currency = models.CharField(max_length=8, default="SDG")
    # Where the business day starts and ends. Every "today" the system
    # computes — the dashboard's sales, overdue invoices, expiring batches,
    # the day a sale falls on in a report — is taken in this zone (activated
    # per request by core.timezone once the user is known). The server clock
    # stays UTC; this is display and day-boundary only.
    timezone = models.CharField(max_length=64, default="Africa/Khartoum")
    # Defaults to enterprise so no existing tenant silently loses screens on
    # upgrade; a new shop opts in.
    business_type = models.CharField(
        max_length=16, choices=BUSINESS_TYPE_CHOICES, default=TYPE_ENTERPRISE
    )
    # Whether anyone has actually *made* that choice, as opposed to inheriting
    # the default. Without this the two states are indistinguishable, and a
    # corner shop lands in the full enterprise layout with nothing ever asking
    # — which is how a feature built for them stayed invisible to them.
    # Backfilled True for companies that already existed: they have been using
    # the system, so their layout is a decision, not an unanswered question.
    business_type_chosen = models.BooleanField(default=False)

    # Issuer identity printed on every outgoing document. Most jurisdictions
    # require the seller's name, address and tax registration number to appear
    # on a tax invoice, so without these the system can only produce receipts,
    # not invoices. All optional at the model level — a company can trade
    # before it has registered — and every document renderer degrades to
    # omitting whatever is blank rather than printing an empty label.
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    tax_number = models.CharField(max_length=64, blank=True)
    registration_number = models.CharField(max_length=64, blank=True)
    # Payments at or above this amount require sign-off from an approver role
    # (CFO / owner / GM) rather than any second user. 0 disables the extra tier,
    # leaving the standard segregation-of-duties check in force.
    payment_approval_threshold = models.DecimalField(
        max_digits=16, decimal_places=2, default=0
    )
    # A stock adjustment whose value (quantity × cost) reaches this amount
    # needs an approver role, the same segregation the stock count enforces
    # with its counter/approver pair. 0 disables the tier.
    stock_adjustment_approval_threshold = models.DecimalField(
        max_digits=16, decimal_places=2, default=0
    )
    # Days a credit sale has before it is overdue, unless the customer
    # carries their own terms. Zero meant "due the day it was sold", which
    # turned every account sale overdue the next morning.
    default_payment_terms_days = models.PositiveIntegerField(default=30)
    # Inflation pricing: catalogue prices may be kept in a stable reference
    # currency (USD for Sudan) and re-derived in the company currency from
    # the day's rate. The rate is denormalised here for cheap reads; every
    # change is also a row in ExchangeRate so a reprice can be audited.
    reference_currency = models.CharField(max_length=8, default="USD")
    # Receipt printing. Sudanese shops print on 80 mm (sometimes 58 mm)
    # thermal rolls; A4 is for offices, A5 for a shop's invoice book. The
    # footer is the line under the totals: return policy, thanks, a phone
    # number.
    PAPER_A4 = "a4"
    PAPER_A5 = "a5"
    PAPER_80 = "80mm"
    PAPER_58 = "58mm"
    PAPER_CHOICES = [
        (PAPER_A4, "A4"), (PAPER_A5, "A5"), (PAPER_80, "80 mm roll"), (PAPER_58, "58 mm roll"),
    ]
    receipt_paper = models.CharField(max_length=8, choices=PAPER_CHOICES, default=PAPER_A4)
    receipt_footer = models.CharField(max_length=240, blank=True)
    exchange_rate = models.DecimalField(
        max_digits=16, decimal_places=4, null=True, blank=True
    )
    exchange_rate_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "company"
            slug = base
            i = 1
            # Ensure uniqueness without assuming DB collation behavior.
            while Company.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)
        # Rule #7: every company has a TaxProfile from M1 onward, even though
        # only the flat-rate "simple" profile is implemented today. Auto-create
        # a default so no company can exist without one.
        TaxProfile.objects.get_or_create(company=self)


class StoreModeAccessException(models.Model):
    """A user or role the owner additionally permits in shop mode.

    This is configuration, not a mutation of a user account.  A rule matters
    only while the company is in shop mode and leaves all previous roles and
    permissions intact when company mode is restored.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="store_mode_exceptions"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, null=True, blank=True,
        related_name="store_mode_exceptions",
    )
    role = models.ForeignKey(
        "accounts.Role", on_delete=models.CASCADE, null=True, blank=True,
        related_name="store_mode_exceptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, role__isnull=True)
                    | models.Q(user__isnull=True, role__isnull=False)
                ),
                name="store_mode_exception_exactly_one_subject",
            ),
            models.UniqueConstraint(
                fields=["company", "user"],
                condition=models.Q(user__isnull=False),
                name="uniq_store_mode_exception_user",
            ),
            models.UniqueConstraint(
                fields=["company", "role"],
                condition=models.Q(role__isnull=False),
                name="uniq_store_mode_exception_role",
            ),
        ]


class TaxProfile(models.Model):
    """
    Jurisdiction-pluggable tax/invoice config (PROJECT_RULES Rule #7).

    M1 ships only the model + a flat-rate "simple/plain" default so nothing
    downstream hardcodes country assumptions into the Invoice model. The
    pluggable invoice-rendering *behavior* (and the Gulf e-invoicing stub)
    lands in M11 — this model is deliberately shaped so that arrives without
    a schema rewrite.
    """

    INVOICE_FORMAT_SIMPLE = "simple"
    INVOICE_FORMAT_GULF_VAT = "gulf_vat"
    INVOICE_FORMAT_CHOICES = [
        (INVOICE_FORMAT_SIMPLE, "Simple / plain invoice"),
        (INVOICE_FORMAT_GULF_VAT, "Gulf VAT e-invoice (scaffold)"),
    ]

    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="tax_profile"
    )
    country = models.CharField(max_length=2, default="SD")  # ISO-3166-1 alpha-2
    invoice_format = models.CharField(
        max_length=32,
        choices=INVOICE_FORMAT_CHOICES,
        default=INVOICE_FORMAT_SIMPLE,
    )
    flat_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )  # percent, e.g. 15.00
    e_invoicing_enabled = models.BooleanField(default=False)
    # Reserved for M11 Gulf scaffold; unused today, present to avoid a rewrite.
    invoice_xml_format = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return f"TaxProfile<{self.company.name}: {self.invoice_format}>"


class Branch(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_branch_name_per_company"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class Department(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="departments"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_department_name_per_company"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class Device(models.Model):
    """One browser profile that has signed in to a company.

    The client mints ``device_id`` once per browser profile (the same id it
    stamps on offline receipts) and sends it with every sign-in. A plan that
    sets a ``devices`` limit is therefore a limit on tills and desks, not on
    people: the third phone at a two-device shop is refused at sign-in until
    the owner revokes one here. Revoking keeps the row — the company's
    history of where it was used — and ends the sessions that device holds.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=64)
    label = models.CharField(max_length=80, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name="devices"
    )
    last_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="devices_last_used",
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="devices_revoked",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "device_id"], name="device_unique_per_company"
            )
        ]
        ordering = ["-last_seen_at"]

    def __str__(self):
        return self.label or self.device_id


class ExchangeRate(models.Model):
    """One recorded rate: how many units of the company currency one unit of
    the reference currency buys. Append-only; the latest row is mirrored to
    Company.exchange_rate."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="exchange_rates"
    )
    currency = models.CharField(max_length=8)
    rate = models.DecimalField(max_digits=16, decimal_places=4)
    note = models.CharField(max_length=120, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [models.Index(fields=["company", "-recorded_at"])]

    def __str__(self):
        return f"{self.currency} {self.rate} @ {self.recorded_at:%Y-%m-%d}"
