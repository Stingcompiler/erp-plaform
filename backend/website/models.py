import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class FollowUpMixin(models.Model):
    """What the platform team needs to keep a conversation going: when they
    last reached the person and how, and when to try again. `record_contact`
    is called when a member opens the call or WhatsApp link from the console;
    `follow_up_due` is what the inbox flags."""

    last_contacted_at = models.DateTimeField(null=True, blank=True)
    last_contact_channel = models.CharField(max_length=16, blank=True)
    next_follow_up_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def record_contact(self, channel):
        self.last_contacted_at = timezone.now()
        self.last_contact_channel = channel
        self.save(update_fields=["last_contacted_at", "last_contact_channel", "updated_at"])

    @property
    def follow_up_due(self):
        return bool(self.next_follow_up_at) and self.next_follow_up_at <= timezone.now()


class PlatformLead(FollowUpMixin, models.Model):
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

    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_CALL = "call"
    CHANNEL_EMAIL = "email"
    CHANNEL_CHOICES = [
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_CALL, "Phone call"),
        (CHANNEL_EMAIL, "Email"),
    ]

    request_uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    name = models.CharField(max_length=255)
    # A prospect reaches us by phone (WhatsApp is the market's channel) or
    # by email; the public form asks for at least one.
    email = models.EmailField(max_length=254, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    preferred_channel = models.CharField(
        max_length=16, choices=CHANNEL_CHOICES, default=CHANNEL_WHATSAPP
    )
    message = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_NEW)
    # The team's own notes; never shown to the prospect.
    internal_note = models.TextField(blank=True)
    source = models.CharField(max_length=64, default="platform-website")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email or self.phone}>"


class RegistrationRequest(FollowUpMixin, models.Model):
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


MAX_SERVICES = 6


def service_lines(text):
    """The merchant's services as a clean list: one per line, blank lines
    dropped, capped at MAX_SERVICES."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()][:MAX_SERVICES]


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
    # Visitors may send orders from the page. What they see on the form, in
    # the site's language: delivery areas, hours, "call before pickup".
    accept_orders = models.BooleanField(default=False)
    order_instructions = models.TextField(blank=True)
    # Who is told about a new order besides the chosen branch's managers:
    # the owners always, and any extra addresses (one per line).
    order_notify_owners = models.BooleanField(default=True)
    order_notify_emails = models.TextField(blank=True)
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
    # What the business offers, one short item per line (up to MAX_SERVICES);
    # shown on the directory card and under the hero of the public page.
    services = models.TextField(blank=True)
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
    # The owner's two public choices per product: show the price, and let a
    # visitor put it in an order. Availability is never a number — only
    # "in stock" or not, read live from the catalog.
    show_price = models.BooleanField(default=True)
    allow_order = models.BooleanField(default=True)

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
    # How a visitor of the marketing site reaches the platform itself: the
    # WhatsApp number behind the floating button, a phone to call and an
    # email. All optional; a blank one shows nothing.
    support_whatsapp = models.CharField(max_length=32, blank=True)
    support_phone = models.CharField(max_length=32, blank=True)
    support_email = models.EmailField(blank=True)
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
                      "analytics_id", "robots_extra", "support_whatsapp", "support_phone",
                      "support_email"):
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


class PageVisit(models.Model):
    """One public page view, recorded server-side (website/analytics.py).

    Hot table with a 7-day life: the nightly rollup folds finished days into
    DailyPageStat and prunes what is older. No cookies and no PII — the
    visitor hash is salted with the day and the secret key, so the same
    visitor collapses within a day and is unlinkable across days. Raw
    company id (not a FK) so a deleted tenant never cascades into history.
    """

    KIND_MARKETING = "marketing"
    KIND_PUBLIC_SITE = "public_site"
    KIND_DIRECTORY = "directory"
    KIND_CHOICES = [
        (KIND_MARKETING, "Marketing page"),
        (KIND_PUBLIC_SITE, "Company public page"),
        (KIND_DIRECTORY, "Public directory"),
    ]

    path = models.CharField(max_length=200)
    page_kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    company_id = models.BigIntegerField(null=True, blank=True)
    referrer_host = models.CharField(max_length=100, blank=True)
    device = models.CharField(max_length=8, blank=True)  # phone / desktop
    language = models.CharField(max_length=8, blank=True)
    visitor_hash = models.CharField(max_length=32)
    is_bot = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["created_at"], name="pagevisit_created_idx")]

    def __str__(self):
        return f"PageVisit<{self.path} @ {self.created_at:%Y-%m-%d %H:%M}>"


class DailyPageStat(models.Model):
    """One aggregated row per (day, path): what the analytics page reads.

    Written only by the nightly rollup; today's numbers are computed live
    from PageVisit by the API. Kept forever — a year of a busy site is
    thousands of rows, not millions.
    """

    date = models.DateField()
    path = models.CharField(max_length=200)
    page_kind = models.CharField(max_length=16, choices=PageVisit.KIND_CHOICES)
    company_id = models.BigIntegerField(null=True, blank=True)
    visits = models.PositiveIntegerField(default=0)
    visitors = models.PositiveIntegerField(default=0)
    bot_visits = models.PositiveIntegerField(default=0)
    # {"host": count} for the day; "" is a direct visit.
    referrers = models.JSONField(default=dict, blank=True)
    devices = models.JSONField(default=dict, blank=True)
    languages = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["date", "path"], name="daily_stat_date_path")
        ]
        indexes = [
            models.Index(fields=["date", "page_kind"], name="dailystat_date_kind_idx"),
        ]

    def __str__(self):
        return f"DailyPageStat<{self.path} {self.date} v={self.visits}>"


class PublicOrder(models.Model):
    """An order a visitor sent from the company's public page.

    It is a request, not a sale: nothing is reserved, no invoice exists and
    prices are what the page showed at the time. The company confirms it —
    which creates the customer (by phone) and a confirmed sales order — or
    rejects it with a reason the visitor can read. The row keeps the
    visitor's words and the branch they chose, because that branch is who
    gets told.
    """

    NEW = "new"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STATES = [
        (NEW, "New"), (CONFIRMED, "Confirmed"), (REJECTED, "Rejected"),
        (CANCELLED, "Cancelled"),
    ]
    PICKUP = "pickup"
    DELIVERY = "delivery"
    DELIVERY_CHOICES = [(PICKUP, "Pickup"), (DELIVERY, "Delivery")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="public_orders"
    )
    website = models.ForeignKey(
        Website, on_delete=models.CASCADE, related_name="public_orders"
    )
    branch = models.ForeignKey(
        "org.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="public_orders",
    )
    reference = models.CharField(max_length=16, unique=True)
    status = models.CharField(max_length=12, choices=STATES, default=NEW)
    contact_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32)
    # Optional: where the order summary, bank details and payment link go.
    email = models.EmailField(blank=True)
    delivery_mode = models.CharField(max_length=12, choices=DELIVERY_CHOICES, default=PICKUP)
    address = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    language = models.CharField(max_length=8, blank=True)
    currency = models.CharField(max_length=8)
    # Sum of the lines whose price was shown; None when any line hides it.
    total = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    customer = models.ForeignKey(
        "sales.Customer", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="public_orders",
    )
    sales_order = models.OneToOneField(
        "sales.SalesOrder", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="public_order",
    )
    decided_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    visitor_hash = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status", "created_at"])]

    def __str__(self):
        return self.reference


class PublicOrderLine(models.Model):
    order = models.ForeignKey(PublicOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        "inventory.Product", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    # The price the visitor saw; None when the owner chose not to show it.
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)


class PushSubscription(models.Model):
    """A browser that agreed to receive push notifications for a user.

    One row per endpoint; the same person on two phones has two rows. The
    payload is sent with the company's VAPID identity; a 404/410 from the
    push service means the browser forgot us and the row is deleted.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    company = models.ForeignKey(
        "org.Company", null=True, blank=True, on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"push:{self.user_id}:{self.endpoint[-24:]}"


class PublicOrderPayment(models.Model):
    """A visitor saying "I transferred": which of the company's accounts,
    from which bank, the transfer's last four digits, the amount, maybe a
    receipt photo.

    It is a claim until a person at the company checks the bank and says
    CONFIRMED — which invoices the order, deducts stock and records the
    verified bank-transfer payment, because at that point the sale is done.
    REJECTED keeps the order open (money never arrived, details wrong);
    FRAUD is a deliberate false claim: it blocks the phone and the visitor
    from ordering again through the page.
    """

    VERIFYING = "verifying"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FRAUD = "fraud"
    STATES = [
        (VERIFYING, "Verifying"), (CONFIRMED, "Confirmed"),
        (REJECTED, "Rejected"), (FRAUD, "Fraud"),
    ]

    order = models.ForeignKey(PublicOrder, on_delete=models.CASCADE, related_name="payments")
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="public_order_payments"
    )
    bank_account = models.ForeignKey(
        "sales.CompanyBankAccount", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    sender_bank_name = models.CharField(max_length=120)
    reference_last4 = models.CharField(max_length=4)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    proof = models.ImageField(upload_to="order-proofs/%Y/%m/", blank=True)
    status = models.CharField(max_length=12, choices=STATES, default=VERIFYING)
    decided_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    payment = models.OneToOneField(
        "sales.Payment", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="public_claim",
    )
    invoice = models.ForeignKey(
        "sales.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    visitor_hash = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "reference_last4"], name="one_claim_per_order_reference"
            )
        ]

    def __str__(self):
        return f"{self.order.reference} · {self.reference_last4}"


class BlockedContact(models.Model):
    """Who may no longer order through a company's page: a phone and the
    browser fingerprint behind a fraudulent payment claim."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="blocked_contacts"
    )
    phone = models.CharField(max_length=32, blank=True)
    visitor_hash = models.CharField(max_length=32, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    source = models.ForeignKey(
        PublicOrderPayment, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "phone"]),
            models.Index(fields=["company", "visitor_hash"]),
        ]
