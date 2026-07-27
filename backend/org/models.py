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
