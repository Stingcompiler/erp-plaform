"""WhatsApp Business (Meta Cloud API) for each company's own number.

Every company connects its own WhatsApp Business number (decision (ب),
2026-09-20): the customer sees the shop's name, and the shop pays for its
own conversations. One webhook serves the platform; Meta tags each event
with the receiving ``phone_number_id`` and that is how an event finds its
company. Vezano's own marketing number is simply an account with no
company.

Nothing here moves money (PROJECT_RULES rule 3): a WhatsApp message can
inform about an invoice or a payment, never confirm one.
"""
import re

from django.conf import settings
from django.db import models


def digits_only(value):
    """Meta gives phone numbers as bare international digits ("2499…")."""
    return re.sub(r"\D", "", str(value or ""))


class WhatsAppAccount(models.Model):
    """A WhatsApp Business phone number connected to the platform."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, null=True, blank=True,
        related_name="whatsapp_accounts",
        help_text="Empty for the platform's own number.",
    )
    # Meta identifiers. phone_number_id is what every webhook event carries.
    phone_number_id = models.CharField(max_length=32, unique=True)
    waba_id = models.CharField(max_length=32, blank=True)
    display_phone = models.CharField(max_length=32, blank=True)
    display_name = models.CharField(max_length=120, blank=True)
    # A permanent System User token from Business Manager. Sending needs it;
    # receiving does not, so a webhook-only account may leave it empty. It
    # is stored encrypted (core.secrets) — a database read or dump must not
    # hand out the ability to message customers in a merchant's name — and
    # read/written through the ``access_token`` property.
    access_token_encrypted = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_phone"]

    def __str__(self):
        return self.display_phone or self.phone_number_id

    @property
    def access_token(self):
        from core.secrets import decrypt

        return decrypt(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value):
        from core.secrets import encrypt

        self.access_token_encrypted = encrypt((value or "").strip())

    @property
    def has_token(self):
        return bool(self.access_token_encrypted)

    def save(self, *args, **kwargs):
        from core.secrets import encrypt, is_encrypted

        # A plaintext that reached the column some other way (a legacy row,
        # a raw update) is sealed on the next save.
        if self.access_token_encrypted and not is_encrypted(self.access_token_encrypted):
            self.access_token_encrypted = encrypt(self.access_token_encrypted)
        super().save(*args, **kwargs)


class WhatsAppMessage(models.Model):
    """One message, inbound or outbound, with the status Meta last reported.

    Meta redelivers events it thinks were lost, so ``wa_message_id`` is
    unique and a second delivery of the same message is ignored. Status
    events (sent → delivered → read, or failed) update the outbound row
    they refer to; a status for a message this system never sent is kept
    as a bare row so nothing is silently dropped.
    """

    INBOUND = "in"
    OUTBOUND = "out"
    DIRECTIONS = [(INBOUND, "Inbound"), (OUTBOUND, "Outbound")]

    RECEIVED = "received"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    STATUSES = [
        (RECEIVED, "Received"), (QUEUED, "Queued"), (SENT, "Sent"),
        (DELIVERED, "Delivered"), (READ, "Read"), (FAILED, "Failed"),
    ]
    # The order Meta's statuses progress in; a late "sent" after "read" must
    # not roll the row backwards.
    STATUS_RANK = {QUEUED: 0, SENT: 1, DELIVERED: 2, READ: 3, FAILED: 4}

    account = models.ForeignKey(
        WhatsAppAccount, on_delete=models.CASCADE, related_name="messages"
    )
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, null=True, blank=True,
        related_name="whatsapp_messages",
    )
    direction = models.CharField(max_length=3, choices=DIRECTIONS)
    wa_message_id = models.CharField(max_length=128, unique=True)
    # The other party, international digits without "+".
    phone = models.CharField(max_length=32, db_index=True)
    contact_name = models.CharField(max_length=120, blank=True)
    message_type = models.CharField(max_length=32, blank=True)  # text, image, button…
    text = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default=RECEIVED)
    error_code = models.CharField(max_length=32, blank=True)
    error_title = models.CharField(max_length=255, blank=True)
    # Meta's own timestamp for the message (seconds since epoch as they send it).
    wa_timestamp = models.DateTimeField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    # Filled by later phases: the customer this phone resolved to, the
    # document a notification was about.
    customer = models.ForeignKey(
        "sales.Customer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="whatsapp_messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"], name="wa_msg_co_created_idx"),
            models.Index(fields=["account", "phone"], name="wa_msg_acct_phone_idx"),
        ]

    def __str__(self):
        return f"{self.direction} {self.phone} {self.status}"


class WhatsAppWebhookEvent(models.Model):
    """Every accepted webhook body, kept briefly for debugging a bad parse.

    Pruned by the daily scans after WHATSAPP_EVENT_RETENTION_DAYS.
    """

    account = models.ForeignKey(
        WhatsAppAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="events",
    )
    payload = models.JSONField()
    messages = models.PositiveSmallIntegerField(default=0)
    statuses = models.PositiveSmallIntegerField(default=0)
    unknown_numbers = models.PositiveSmallIntegerField(default=0)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-received_at"]


class WhatsAppTemplate(models.Model):
    """Which approved Meta template a company uses for each purpose.

    Templates are created and approved in the company's own Business
    Manager; here we only record the name and language to call them by.
    Body parameters are positional and fixed per purpose (see PARAMS) so
    the owner knows what {{1}}…{{4}} must mean when writing the template.
    """

    INVOICE_SENT = "invoice_sent"
    PAYMENT_RECEIVED = "payment_received"
    DEBT_REMINDER = "debt_reminder"
    ORDER_CONFIRMED = "order_confirmed"
    PURPOSES = [
        (INVOICE_SENT, "Invoice after a sale"),
        (PAYMENT_RECEIVED, "Payment received"),
        (DEBT_REMINDER, "Debt reminder"),
        (ORDER_CONFIRMED, "Public order confirmed"),
    ]
    # Positional body parameters each purpose sends, in order.
    PARAMS = {
        INVOICE_SENT: ["customer name", "invoice number", "total", "amount due"],
        PAYMENT_RECEIVED: ["customer name", "amount paid", "invoice number", "balance due"],
        DEBT_REMINDER: ["customer name", "amount overdue", "oldest invoice", "days overdue"],
        ORDER_CONFIRMED: ["customer name", "order reference", "total", "branch"],
    }

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="whatsapp_templates"
    )
    purpose = models.CharField(max_length=32, choices=PURPOSES)
    template_name = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=8, default="ar")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "purpose"], name="uniq_wa_template_purpose")
        ]

    def __str__(self):
        return f"{self.purpose} → {self.template_name or '—'}"


def settings_ready():
    """The two secrets the webhook needs; sending needs the account token."""
    return bool(
        getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
        and getattr(settings, "WHATSAPP_APP_SECRET", "")
    )
