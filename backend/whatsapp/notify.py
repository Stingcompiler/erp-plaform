"""Business notifications over WhatsApp: which message, to whom, how.

Meta's rule: a business may write freely only inside the 24 hours after
the customer's last message; outside it only an approved template goes
through. So each purpose tries the company's template first, then free
text if the window is open, and otherwise records why nothing was sent.
Every entry point is best-effort and never raises into the sale or the
payment that triggered it.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from whatsapp import client
from whatsapp.models import WhatsAppAccount, WhatsAppMessage, WhatsAppTemplate, digits_only

logger = logging.getLogger(__name__)
WINDOW = timedelta(hours=24)


def money(value, currency=""):
    number = f"{Decimal(value or 0):,.2f}"
    return f"{number} {currency}".strip()


def account_for(company):
    if company is None:
        return None
    return WhatsAppAccount.objects.filter(
        company=company, is_active=True,
    ).exclude(access_token="").first()


def reachable_phone(customer):
    """The customer's number as Meta wants it, only if they opted in."""
    if customer is None or not getattr(customer, "whatsapp_opt_in", False):
        return ""
    phone = digits_only(customer.phone)
    return phone if len(phone) >= 8 else ""


def window_open(account, phone):
    since = timezone.now() - WINDOW
    return WhatsAppMessage.objects.filter(
        account=account, phone=phone, direction=WhatsAppMessage.INBOUND,
        created_at__gte=since,
    ).exists()


def template_for(company, purpose):
    return WhatsAppTemplate.objects.filter(
        company=company, purpose=purpose, is_active=True,
    ).exclude(template_name="").first()


def deliver(company, customer, purpose, *, params, text):
    """Template if configured, else free text inside the window, else skip.
    Returns (row_or_None, reason)."""
    account = account_for(company)
    if account is None:
        return None, "no_account"
    phone = reachable_phone(customer)
    if not phone:
        return None, "no_opt_in"
    template = template_for(company, purpose)
    if template is not None:
        payload = client.template_payload(phone, template.template_name, template.language, params)
        return client.send(
            account, phone, payload, purpose=purpose, customer=customer, text=text,
        ), "template"
    if window_open(account, phone):
        return client.send(
            account, phone, client.text_payload(phone, text), purpose=purpose,
            customer=customer, text=text,
        ), "text"
    return None, "outside_window"


def notify_invoice(invoice):
    """After a sale: what was bought, what was paid, what is still owed."""
    try:
        customer = invoice.customer
        if customer is None:
            return None, "no_customer"
        currency = invoice.currency or ""
        due = invoice.amount_due()
        params = [
            customer.name, invoice.number_display, money(invoice.total, currency),
            money(due, currency),
        ]
        company_name = invoice.company.name
        text = (
            f"{company_name}\n"
            f"فاتورة {invoice.number_display}\n"
            f"الإجمالي: {money(invoice.total, currency)}\n"
            + (f"المتبقي: {money(due, currency)}\n" if due > 0 else "مدفوعة بالكامل\n")
            + "شكرًا لتعاملكم معنا."
        )
        return deliver(
            invoice.company, customer, WhatsAppTemplate.INVOICE_SENT, params=params, text=text,
        )
    except Exception:  # noqa: BLE001 - never break the sale
        logger.exception("WhatsApp invoice notification failed for invoice %s", invoice.pk)
        return None, "error"


def notify_payment(payment):
    """After a customer payment is recorded: amount and remaining balance."""
    try:
        invoice = payment.invoice
        customer = invoice.customer
        if customer is None or payment.method == "credit":
            return None, "no_customer"
        currency = payment.currency or invoice.currency or ""
        due = invoice.amount_due()
        params = [
            customer.name, money(payment.amount, currency), invoice.number_display,
            money(due, currency),
        ]
        text = (
            f"{invoice.company.name}\n"
            f"استلمنا دفعة {money(payment.amount, currency)} "
            f"على الفاتورة {invoice.number_display}.\n"
            + (f"المتبقي: {money(due, currency)}" if due > 0 else "الفاتورة مسددة بالكامل.")
        )
        return deliver(
            invoice.company, customer, WhatsAppTemplate.PAYMENT_RECEIVED, params=params, text=text,
        )
    except Exception:  # noqa: BLE001 - never break the payment
        logger.exception("WhatsApp payment notification failed for payment %s", payment.pk)
        return None, "error"
