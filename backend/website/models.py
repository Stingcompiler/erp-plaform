import uuid

from django.db import models


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
