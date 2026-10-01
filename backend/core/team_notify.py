"""Telling the Vezano platform team about new business.

The attention badges only help someone who is already signed in. These
notices reach the team where they are: a bilingual email to every active
platform member whose role covers the event (superusers always), to the
extra inboxes in ``PLATFORM_NOTIFY_EMAILS``, and a Web Push to each browser
a member enabled.

Best effort, like every other email here: nothing in this module may fail
the request that triggered it. Delivery waits for the transaction to commit
(a rolled-back request announces nothing) and then runs off the request
thread, the same way the password-reset email does, so a slow SMTP server
never delays the visitor. Messages carry what the admin page shows at a
glance (names, references, amounts), never a visitor's phone or email.
"""

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Q

logger = logging.getLogger(__name__)


def extra_addresses():
    """``PLATFORM_NOTIFY_EMAILS`` as a clean list."""
    raw = getattr(settings, "PLATFORM_NOTIFY_EMAILS", None) or []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [address.strip() for address in raw if "@" in str(address)]


def team_members(capability):
    """Active platform members holding ``capability``, one per address."""
    from accounts.models import Role, User
    from core.platform_roles import user_has_platform_capability

    candidates = (
        User.objects.select_related("role")
        .filter(is_active=True)
        .filter(
            Q(is_superuser=True)
            | Q(company__isnull=True, role__scope_level=Role.SCOPE_PLATFORM)
        )
        .exclude(email="")
        .order_by("pk")
    )
    seen, members = set(), []
    for user in candidates:
        key = user.email.strip().lower()
        if key in seen or not user_has_platform_capability(user, capability):
            continue
        seen.add(key)
        members.append(user)
    return members


def recipients(capability):
    """(members, extra addresses): the extra list skips anyone already a member."""
    members = team_members(capability)
    seen = {user.email.strip().lower() for user in members}
    extras = []
    for address in extra_addresses():
        key = address.lower()
        if key not in seen:
            seen.add(key)
            extras.append(address)
    return members, extras


def _link(path):
    origin = (getattr(settings, "PUBLIC_APP_ORIGIN", "") or "").rstrip("/")
    return f"{origin}{path}" if origin and path else None


def deliver(event, *, subject_ar, subject_en, ar, en, link_path, capability,
            push_title="", push_body="", tag=""):
    """Send now. Returns {"emails": n, "pushes": n}; never raises."""
    from core import mailer, push

    sent = {"emails": 0, "pushes": 0}
    try:
        members, extras = recipients(capability)
    except Exception:  # noqa: BLE001 - a notice must never break its caller
        logger.exception("team notice %s: could not resolve recipients", event)
        return sent
    link = _link(link_path)
    for address in [user.email for user in members] + extras:
        try:
            if mailer.send_bilingual(
                subject_ar=subject_ar, subject_en=subject_en, ar=ar, en=en,
                recipient=address, link=link, primary="ar",
            ):
                sent["emails"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("team notice %s: email to %s failed", event, address)
    for user in members:
        try:
            sent["pushes"] += push.send_to_user(
                user, title=push_title or subject_ar, body=push_body,
                url=link_path, tag=tag or f"team-{event}",
            )
        except Exception:  # noqa: BLE001
            logger.exception("team notice %s: push to user %s failed", event, user.pk)
    return sent


def _in_background(work, name):
    if not getattr(settings, "TEAM_NOTIFY_BACKGROUND", True):
        work()
        return

    def run():
        try:
            work()
        except Exception:  # noqa: BLE001 - logged, never raised
            logger.exception("%s failed", name)
        finally:
            close_old_connections()

    threading.Thread(target=run, name=name, daemon=True).start()


def notify_platform_team(event, *, subject_ar, subject_en, ar, en, link_path, capability,
                         push_title="", push_body="", tag="", background=None):
    """Queue a notice for after the current transaction commits.

    ``background=False`` sends on this thread (a cron command that exits
    right after must not leave a daemon thread mid-send); the default follows
    ``TEAM_NOTIFY_BACKGROUND``.
    """
    kwargs = dict(
        subject_ar=subject_ar, subject_en=subject_en, ar=list(ar), en=list(en),
        link_path=link_path, capability=capability,
        push_title=push_title, push_body=push_body, tag=tag,
    )

    def work():
        deliver(event, **kwargs)

    def after_commit():
        try:
            if background is False:
                work()
            else:
                _in_background(work, f"team-notice-{event}")
        except Exception:  # noqa: BLE001
            logger.exception("team notice %s could not be sent", event)

    try:
        transaction.on_commit(after_commit)
    except Exception:  # noqa: BLE001
        logger.exception("team notice %s could not be queued", event)


# --- The events -----------------------------------------------------------

def registration_submitted(registration):
    from core import platform_roles

    plan = ""
    try:
        if registration.plan_version_id:
            plan = registration.plan_version.plan.name
    except Exception:  # noqa: BLE001
        plan = ""
    ref = registration.public_reference or ""
    notify_platform_team(
        "registration",
        subject_ar=f"طلب تسجيل جديد: {registration.company_name}",
        subject_en=f"New registration request: {registration.company_name}",
        ar=[
            f"وصل طلب تسجيل جديد من «{registration.company_name}» "
            f"(المسؤول: {registration.contact_name}).",
            *([f"الباقة: {plan}"] if plan else []),
            f"رقم الطلب: {ref}",
            "راجعه من صفحة «طلبات التسجيل».",
        ],
        en=[
            f"A new registration request arrived from “{registration.company_name}” "
            f"(contact: {registration.contact_name}).",
            *([f"Plan: {plan}"] if plan else []),
            f"Reference: {ref}",
            "Review it on the registrations page.",
        ],
        link_path="/platform-registrations/",
        capability=platform_roles.REGISTRATIONS_REVIEW,
        push_title=f"طلب تسجيل جديد · New registration {ref}".strip(),
        push_body=registration.company_name[:180],
        tag=f"team-registration-{registration.pk}",
    )


CHANNELS = {
    "whatsapp": ("واتساب", "WhatsApp"),
    "call": ("مكالمة هاتفية", "Phone call"),
    "email": ("البريد الإلكتروني", "Email"),
}


def lead_submitted(lead):
    from core import platform_roles

    ref = lead.public_reference or ""
    channel_ar, channel_en = CHANNELS.get(lead.preferred_channel, ("", ""))
    notify_platform_team(
        "lead",
        subject_ar=f"طلب عرض توضيحي جديد: {lead.name}",
        subject_en=f"New demo request: {lead.name}",
        ar=[
            f"طلب {lead.name} عرضًا توضيحيًا لفيزانو برو.",
            *([f"وسيلة التواصل المفضلة: {channel_ar}"] if channel_ar else []),
            f"رقم الطلب: {ref}",
            "تواصل معه من صفحة «طلبات العرض».",
        ],
        en=[
            f"{lead.name} asked for a Vezano Pro walkthrough.",
            *([f"Preferred channel: {channel_en}"] if channel_en else []),
            f"Reference: {ref}",
            "Follow up from the demo requests page.",
        ],
        link_path="/platform-leads/",
        capability=platform_roles.LEADS_MANAGE,
        push_title=f"طلب عرض جديد · New demo request {ref}".strip(),
        push_body=lead.name[:180],
        tag=f"team-lead-{lead.pk}",
    )


def payment_submitted(payment):
    from core import platform_roles

    company = payment.company.name
    amount = f"{payment.amount} {payment.currency}"
    notify_platform_team(
        "subscription-payment",
        subject_ar=f"دفعة اشتراك بانتظار المراجعة: {company}",
        subject_en=f"Subscription payment to verify: {company}",
        ar=[
            f"سجّلت «{company}» دفعة اشتراك بمبلغ {amount}.",
            "تحقق منها واعتمدها أو ارفضها من صفحة «الاشتراكات».",
        ],
        en=[
            f"“{company}” recorded a subscription payment of {amount}.",
            "Verify or reject it on the subscriptions page.",
        ],
        link_path="/platform-subscriptions/",
        capability=platform_roles.BILLING_REVIEW,
        push_title="دفعة اشتراك جديدة · New subscription payment",
        push_body=f"{company} · {amount}"[:180],
        tag=f"team-payment-{payment.pk}",
    )


def plan_change_requested(change):
    from core import platform_roles

    company = change.company.name
    if change.extra_delta:
        what_ar = f"إضافة سعة ({change.extra_delta})"
        what_en = f"add-on capacity ({change.extra_delta})"
    else:
        plan = change.to_version.plan.name
        what_ar = f"الانتقال إلى باقة {plan}"
        what_en = f"a move to the {plan} plan"
    notify_platform_team(
        "plan-change",
        subject_ar=f"طلب تغيير باقة: {company}",
        subject_en=f"Plan change request: {company}",
        ar=[
            f"طلبت «{company}» {what_ar}.",
            "اعتمده أو ارفضه من صفحة «الاشتراكات».",
        ],
        en=[
            f"“{company}” asked for {what_en}.",
            "Approve or reject it on the subscriptions page.",
        ],
        link_path="/platform-subscriptions/",
        capability=platform_roles.SUBSCRIPTIONS_MANAGE,
        push_title="طلب تغيير باقة · Plan change request",
        push_body=company[:180],
        tag=f"team-plan-change-{change.pk}",
    )


TRIAL_NOTICE_ACTION = "team_notified"
TRIAL_NOTICE_ENTITY = "TrialEnding"
TRIAL_NOTICE_DAYS = 3


def notify_trials_ending(now=None):
    """Once per company per trial end date: trials ending within 3 days.

    The marker is a platform-level ActivityLog row keyed by the
    subscription and its trial end, so reruns of the daily scan (or a second
    cron on the same day) stay silent, and an extended trial is announced
    again for its new date. Returns how many notices were queued.
    """
    from datetime import timedelta

    from django.utils import timezone

    from core import platform_roles
    from core.activity import log_activity
    from core.models import ActivityLog
    from subscriptions.models import Subscription

    now = now or timezone.now()
    due = Subscription.objects.select_related("company").filter(
        status=Subscription.TRIALING,
        trial_ends_at__gt=now,
        trial_ends_at__lte=now + timedelta(days=TRIAL_NOTICE_DAYS),
    )
    queued = 0
    for subscription in due:
        ends = subscription.trial_ends_at
        marker = f"{subscription.pk}:{ends.isoformat()}"
        if ActivityLog.objects.filter(
            action=TRIAL_NOTICE_ACTION, entity_type=TRIAL_NOTICE_ENTITY,
            entity_id=str(subscription.pk), metadata__marker=marker,
        ).exists():
            continue
        log_activity(
            action=TRIAL_NOTICE_ACTION, entity_type=TRIAL_NOTICE_ENTITY,
            entity_id=subscription.pk,
            metadata={"marker": marker, "company_id": subscription.company_id},
        )
        company = subscription.company.name
        day = timezone.localtime(ends).date().isoformat()
        notify_platform_team(
            "trial-ending",
            subject_ar=f"تجربة تنتهي قريبًا: {company}",
            subject_en=f"Trial ending soon: {company}",
            ar=[
                f"تنتهي الفترة التجريبية لـ«{company}» في {day}.",
                "تواصل مع الشركة لتحويلها إلى اشتراك مدفوع من صفحة «الاشتراكات».",
            ],
            en=[
                f"The trial for “{company}” ends on {day}.",
                "Reach out to convert it to a paid subscription from the subscriptions page.",
            ],
            link_path="/platform-subscriptions/",
            capability=platform_roles.SUBSCRIPTIONS_MANAGE,
            push_title="تجربة تنتهي قريبًا · Trial ending soon",
            push_body=f"{company} · {day}"[:180],
            tag=f"team-trial-{subscription.pk}",
            background=False,
        )
        queued += 1
    return queued
