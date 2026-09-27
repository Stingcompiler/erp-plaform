"""Suspending a company until it pays ("يدخل ويدفع فقط").

A platform decision distinct from the manual suspension an administrator
sets through the subscription console:

* while it holds, only the company's owner(s) may sign in, and the API
  answers every other call with ``suspended_unpaid`` (see
  core.company_access for what stays open: identity, sign-out, the
  subscription page and payment recording, and the offline upload of work
  captured before the suspension);
* approving a payment from the company lifts it automatically
  (``verify_and_allocate_payment`` calls ``lift_on_payment``), which a
  manual suspension never does;
* the platform can lift it by hand.

The suspension is ``status=SUSPENDED`` + ``suspension_kind=unpaid`` on the
subscription, so every existing rule about a suspended subscription (no
writes, the pre-suspension sync rule in core.entitlements.writes_allowed_at)
applies unchanged.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from subscriptions.models import Subscription, SubscriptionEvent

logger = logging.getLogger(__name__)

OWNER_ROLE = "Business Owner"


def is_company_owner(user):
    return bool(
        user is not None
        and getattr(user, "company_id", None)
        and getattr(getattr(user, "role", None), "name", None) == OWNER_ROLE
    )


def _status_after_lift(subscription, now):
    """Where an unpaid suspension returns to: active when a paid period is
    still ahead, else what the subscription was before the suspension (the
    clock rules in core.entitlements then take a lapsed one to grace or
    read-only on their own)."""
    if subscription.period_ends_at and subscription.period_ends_at > now:
        return Subscription.ACTIVE
    previous = subscription.status_before_suspension
    if previous and previous != Subscription.SUSPENDED:
        return previous
    return Subscription.READ_ONLY


# ---------------------------------------------------------------- email

def _owner_language(user):
    from ops.models import UserPreference

    language = UserPreference.objects.filter(user=user).values_list(
        "language", flat=True
    ).first()
    return "en" if language == "en" else "ar"


def _owners(company):
    from accounts.models import User

    return list(
        User.objects.filter(company=company, role__name=OWNER_ROLE, is_active=True)
        .order_by("pk")
    )


def _login_link():
    origin = (getattr(settings, "PUBLIC_APP_ORIGIN", "") or "").rstrip("/")
    return f"{origin}/login/" if origin else None


def _email_owners(company, build):
    """Send ``build(owner)`` -> (subject_ar, subject_en, ar, en) to every
    owner after the transaction commits; nothing when email is off."""
    from core import mailer

    if not mailer.email_is_enabled():
        return

    def send():
        for owner in _owners(company):
            subject_ar, subject_en, ar, en = build(owner)
            mailer.send_bilingual(
                subject_ar=subject_ar, subject_en=subject_en, ar=ar, en=en,
                recipient=owner.email, link=_login_link(),
                primary=_owner_language(owner),
            )

    transaction.on_commit(send)


def _email_suspended(company, reason):
    def build(owner):
        name = owner.full_name or owner.email
        return (
            "حساب شركتك موقوف مؤقتًا لحين السداد",
            "Your company account is suspended until payment",
            [
                f"مرحباً {name}،",
                f"أوقفت فيزانو برو حساب «{company.name}» مؤقتًا لحين سداد الاشتراك.",
                f"السبب: {reason}",
                "يستطيع مالك الشركة وحده الدخول الآن لتسجيل الدفعة (تحويل بنكي مع رقم "
                "العملية). يعود الحساب للعمل تلقائيًا فور اعتماد الدفعة.",
            ],
            [
                f"Hello {name},",
                f"Vezano Pro has suspended “{company.name}” until the subscription is paid.",
                f"Reason: {reason}",
                "Only the company owner can sign in now, to record the payment (bank "
                "transfer with its reference). The account reopens as soon as the "
                "payment is approved.",
            ],
        )

    _email_owners(company, build)


def _email_lifted(company):
    def build(owner):
        name = owner.full_name or owner.email
        return (
            "أُعيد تفعيل حساب شركتك",
            "Your company account is active again",
            [
                f"مرحباً {name}،",
                f"رُفع إيقاف حساب «{company.name}»، ويستطيع فريقك الدخول والعمل كالمعتاد.",
            ],
            [
                f"Hello {name},",
                f"The suspension of “{company.name}” is lifted; your team can sign in "
                "and work as usual.",
            ],
        )

    _email_owners(company, build)


# ---------------------------------------------------------------- actions

@transaction.atomic
def suspend_until_payment(company, actor, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": _("Give the company a reason; its owner will read it.")})
    subscription = Subscription.objects.select_for_update().filter(company=company).first()
    if subscription is None:
        raise ValidationError({"detail": _("This company has no subscription to suspend.")})
    if subscription.is_suspended_unpaid:
        raise ValidationError({"detail": _("This company is already suspended until payment.")})
    if subscription.status == Subscription.SUSPENDED:
        raise ValidationError({
            "detail": _(
                "This company is already suspended by an administrator. Lift that "
                "suspension first."
            )
        })
    if not company.is_active:
        raise ValidationError({"detail": _("This company is scheduled for deletion.")})
    now = timezone.now()
    previous = subscription.status
    subscription.status = Subscription.SUSPENDED
    subscription.suspension_kind = Subscription.SUSPENSION_UNPAID
    subscription.suspended_reason = reason[:2000]
    subscription.suspended_at = now
    subscription.status_before_suspension = previous
    subscription.revision += 1
    subscription.save(update_fields=[
        "status", "suspension_kind", "suspended_reason", "suspended_at",
        "status_before_suspension", "revision", "updated_at",
    ])
    SubscriptionEvent.objects.create(
        subscription=subscription, event_type="suspended_unpaid",
        from_status=previous, to_status=Subscription.SUSPENDED,
        reason=subscription.suspended_reason, actor=actor,
    )
    log_activity(
        action="company_suspended_unpaid", request=request, user=actor, company=company,
        entity_type="CompanyLifecycle", entity_id=company.pk,
        metadata={
            "company": company.name, "slug": company.slug, "reason": subscription.suspended_reason,
            "from_status": previous,
        },
    )
    _email_suspended(company, subscription.suspended_reason)
    return subscription


def _lift(subscription, actor, via, request=None, note=""):
    """Lift an unpaid suspension on a subscription the caller has locked."""
    now = timezone.now()
    previous = subscription.status
    target = _status_after_lift(subscription, now)
    subscription.status = target
    subscription.suspension_kind = ""
    subscription.suspended_reason = ""
    subscription.suspended_at = None
    subscription.status_before_suspension = ""
    subscription.revision += 1
    subscription.save(update_fields=[
        "status", "suspension_kind", "suspended_reason", "suspended_at",
        "status_before_suspension", "revision", "updated_at",
    ])
    SubscriptionEvent.objects.create(
        subscription=subscription, event_type="suspension_lifted",
        from_status=previous, to_status=target, reason=note, actor=actor,
        metadata={"via": via},
    )
    company = subscription.company
    log_activity(
        action="company_suspension_lifted", request=request, user=actor, company=company,
        entity_type="CompanyLifecycle", entity_id=company.pk,
        metadata={"company": company.name, "slug": company.slug, "via": via, "to_status": target},
    )
    _email_lifted(company)
    return subscription


@transaction.atomic
def lift_suspension(company, actor, request=None, note=""):
    subscription = Subscription.objects.select_for_update().filter(company=company).first()
    if subscription is None or not subscription.is_suspended_unpaid:
        raise ValidationError({"detail": _("This company is not suspended until payment.")})
    return _lift(subscription, actor, "manual", request=request, note=(note or "").strip())


def lift_on_payment(company_id, actor, payment_id):
    """Called inside the payment-approval transaction: an approved payment
    ends a suspension-until-payment. A manual suspension stays."""
    subscription = (
        Subscription.objects.select_for_update().select_related("company")
        .filter(company_id=company_id).first()
    )
    if subscription is None or not subscription.is_suspended_unpaid:
        return None
    return _lift(subscription, actor, "payment", note=f"payment #{payment_id}")


def unpaid_suspension(company):
    """The live suspension-until-payment of ``company`` as
    ``{"reason", "since"}``, or None."""
    if company is None:
        return None
    row = Subscription.objects.filter(
        company=company, status=Subscription.SUSPENDED,
        suspension_kind=Subscription.SUSPENSION_UNPAID,
    ).values("suspended_reason", "suspended_at").first()
    if row is None:
        return None
    return {"reason": row["suspended_reason"], "since": row["suspended_at"]}
