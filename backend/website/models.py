import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PlatformLead(models.Model):
    """A prospective Vezano customer captured from the public platform site.

    This is deliberately separate from CRM leads, which belong to a tenant and
    represent that tenant's own customers.
    """

    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_QUALIFIED = "qualified"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_QUALIFIED, "Qualified"),
        (STATUS_CLOSED, "Closed"),
    ]

    request_uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(max_length=254)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_NEW)
    source = models.CharField(max_length=64, default="platform-website")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class RegistrationRequest(models.Model):
    """A prospective SaaS tenant, separate from a tenant's own CRM data."""

    SAAS = "saas"
    STANDALONE = "standalone"
    DELIVERY_CHOICES = [(SAAS, "Hosted SaaS"), (STANDALONE, "Standalone")]

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    NEEDS_INFORMATION = "needs_information"
    APPROVED = "approved"
    PROVISIONED = "provisioned"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    STATUS_CHOICES = [
        (SUBMITTED, "Submitted"),
        (UNDER_REVIEW, "Under review"),
        (NEEDS_INFORMATION, "Needs information"),
        (APPROVED, "Approved"),
        (PROVISIONED, "Provisioned"),
        (REJECTED, "Rejected"),
        (WITHDRAWN, "Withdrawn"),
    ]

    request_uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=254)
    phone = models.CharField(max_length=64)
    country = models.CharField(max_length=2)
    timezone_name = models.CharField(max_length=64, default="UTC")
    estimated_users = models.PositiveIntegerField(null=True, blank=True)
    estimated_branches = models.PositiveIntegerField(null=True, blank=True)
    delivery_mode = models.CharField(max_length=16, choices=DELIVERY_CHOICES, default=SAAS)
    plan_version = models.ForeignKey(
        "subscriptions.PlanVersion", on_delete=models.PROTECT,
        null=True, blank=True, related_name="registration_requests",
    )
    message = models.TextField(blank=True)
    privacy_version = models.CharField(max_length=32)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=SUBMITTED)
    internal_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_registration_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    company = models.OneToOneField(
        "org.Company", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="registration_request",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company_name} ({self.email})"

    def mark_reviewed(self, user):
        self.reviewed_by = user
        self.reviewed_at = timezone.now()


class OwnerInvitation(models.Model):
    """One-time invitation for the owner created during tenant provisioning."""

    token_hash = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owner_invitations"
    )
    registration_request = models.ForeignKey(
        RegistrationRequest, on_delete=models.CASCADE, related_name="owner_invitations"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_usable(self):
        return not self.accepted_at and not self.revoked_at and self.expires_at > timezone.now()


class Website(models.Model):
    """
    A company's public landing page. One per company. `is_published` gates
    whether the site is visible on the public (unauthenticated) endpoint —
    a company works on its site privately and flips it live when ready.
    """

    company = models.OneToOneField(
        "org.Company", on_delete=models.CASCADE, related_name="website"
    )
    business_name = models.CharField(max_length=255, blank=True)
    tagline = models.CharField(max_length=255, blank=True)
    about_text = models.TextField(blank=True)
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=16, default="#111827")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)
    address = models.TextField(blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Website<{self.company.slug}>"


class Section(models.Model):
    HERO = "hero"
    ABOUT = "about"
    PRODUCTS = "products"
    GALLERY = "gallery"
    CONTACT = "contact"
    CUSTOM = "custom"
    TYPE_CHOICES = [
        (HERO, "Hero"), (ABOUT, "About"), (PRODUCTS, "Products"),
        (GALLERY, "Gallery"), (CONTACT, "Contact"), (CUSTOM, "Custom"),
    ]

    # Denormalized company FK so the shared company-scoping base works directly.
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="website_sections"
    )
    website = models.ForeignKey(
        Website, on_delete=models.CASCADE, related_name="sections"
    )
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)
    content = models.JSONField(default=dict, blank=True)
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.type} section ({self.company_id})"


class FeaturedProduct(models.Model):
    """
    Explicitly curated products shown on the public site. Opt-in (not the whole
    catalog) so nothing internal leaks publicly by default.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="featured_products"
    )
    website = models.ForeignKey(
        Website, on_delete=models.CASCADE, related_name="featured_products"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.CASCADE, related_name="featured_on"
    )
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["website", "product"], name="uniq_featured_product_per_site"
            )
        ]

    def __str__(self):
        return f"Featured {self.product_id} on {self.website_id}"
