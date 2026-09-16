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


def site_upload_path(instance, filename):
    """MEDIA_ROOT/public/sites/<company>/<file>; the public/ prefix is what
    the anonymous media view is allowed to serve."""
    company_id = getattr(instance, "company_id", None)
    return f"public/sites/{company_id}/{filename}"


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

    # Landing-page fields. Uploaded images live under MEDIA_ROOT/public/ —
    # the only media subtree served to anonymous visitors (core.public_media).
    # `logo_url` above is kept for sites that pasted a link; an uploaded logo
    # wins when both exist.
    CATEGORY_CHOICES = [
        ("grocery", "Grocery & food"),
        ("pharmacy", "Pharmacy"),
        ("wholesale", "Wholesale & distribution"),
        ("electronics", "Electronics"),
        ("fashion", "Fashion & clothing"),
        ("cosmetics", "Cosmetics & perfume"),
        ("hardware", "Hardware & building"),
        ("restaurant", "Restaurant & café"),
        ("services", "Services"),
        ("other", "Other"),
    ]
    cover_image = models.ImageField(upload_to=site_upload_path, blank=True, null=True)
    logo_image = models.ImageField(upload_to=site_upload_path, blank=True, null=True)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, blank=True)
    city = models.CharField(max_length=120, blank=True)
    opening_hours = models.TextField(blank=True)
    map_url = models.URLField(blank=True)
    # Consent to appear in the public directory and the platform's marketing
    # sections. The page itself is public whenever the site is published.
    list_in_directory = models.BooleanField(default=True)

    def __str__(self):
        return f"Website<{self.company.slug}>"


class WebsiteImage(models.Model):
    """A gallery photo on the public site."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="website_images"
    )
    website = models.ForeignKey(
        Website, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to=site_upload_path)
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"WebsiteImage<{self.website_id}:{self.pk}>"


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


def seo_upload_path(instance, filename):
    """MEDIA_ROOT/public/seo/<file>: the default share image is meant for
    every visitor and crawler, so it lives under the anonymous prefix."""
    return f"public/seo/{filename}"


def normalize_seo_path(path):
    """The public path of a page as the team types it: leading slash, no
    trailing slash except the root, no language prefix. '/pricing/',
    'pricing' and '/pricing' all mean the same page."""
    path = (path or "").strip()
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return path


class SeoSettings(models.Model):
    """Site-wide search settings the platform team controls without a
    deploy: verification tags, the analytics id, a default share image and
    extra robots.txt lines. One row (pk=1); `load()` creates it on first use.

    Everything is optional and blank by default, so an untouched row changes
    nothing about what the export already ships."""

    google_site_verification = models.CharField(max_length=255, blank=True)
    bing_site_verification = models.CharField(max_length=255, blank=True)
    # GA4 measurement id ("G-XXXXXXXXXX"); the tag is injected when set.
    analytics_id = models.CharField(max_length=64, blank=True)
    default_og_image = models.ImageField(upload_to=seo_upload_path, blank=True, null=True)
    # Appended verbatim to the exported robots.txt.
    robots_extra = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SEO settings"
        verbose_name_plural = "SEO settings"

    SINGLETON_PK = 1

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)
        from website.seo import invalidate_seo_cache

        invalidate_seo_cache()

    def delete(self, *args, **kwargs):
        # The singleton is cleared, never removed.
        for field in ("google_site_verification", "bing_site_verification",
                      "analytics_id", "robots_extra"):
            setattr(self, field, "")
        if self.default_og_image:
            self.default_og_image.delete(save=False)
            self.default_og_image = None
        self.save()

    def __str__(self):
        return "SEO settings"


class SeoPageOverride(models.Model):
    """Per-page search metadata the team sets over what the export ships:
    title, description, a noindex switch and a canonical URL, for one public
    path in one language (or both). Applied while the page is served, so the
    change is live without a deploy. A blank field keeps the page's own
    value."""

    LANGUAGE_AR = "ar"
    LANGUAGE_EN = "en"
    LANGUAGE_BOTH = "both"
    LANGUAGE_CHOICES = [
        (LANGUAGE_AR, "Arabic"),
        (LANGUAGE_EN, "English"),
        (LANGUAGE_BOTH, "Both"),
    ]

    path = models.CharField(max_length=255)
    language = models.CharField(max_length=4, choices=LANGUAGE_CHOICES, default=LANGUAGE_BOTH)
    title = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=400, blank=True)
    noindex = models.BooleanField(default=False)
    canonical = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["path", "language"]
        constraints = [
            models.UniqueConstraint(fields=["path", "language"], name="seo_override_path_language"),
        ]

    def save(self, *args, **kwargs):
        self.path = normalize_seo_path(self.path)
        super().save(*args, **kwargs)
        from website.seo import invalidate_seo_cache

        invalidate_seo_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        from website.seo import invalidate_seo_cache

        invalidate_seo_cache()
        return result

    def __str__(self):
        return f"{self.path} [{self.language}]"
