import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from core.activity import log_activity
from org.models import Branch, Company
from subscriptions.models import Subscription, SubscriptionEvent
from website.models import OwnerInvitation, RegistrationRequest


INVITATION_TTL = timedelta(days=7)


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def plan_version_is_available(plan_version):
    """A plan the public can still sign up for: published, public and active."""
    return bool(
        plan_version is not None
        and plan_version.published_at is not None
        and plan_version.plan.is_public
        and plan_version.plan.is_active
    )


def _issue_owner_invitation(registration, owner, now):
    """Revoke any live invitation for this request and mint a fresh token.

    Only the hash is stored; the caller receives the plaintext once.
    """
    token = secrets.token_urlsafe(32)
    OwnerInvitation.objects.filter(
        registration_request=registration, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    OwnerInvitation.objects.create(
        token_hash=_token_hash(token), owner=owner, registration_request=registration,
        expires_at=now + INVITATION_TTL,
    )
    return token


@transaction.atomic
def provision_registration_request(request_id, actor, request=None):
    # ``plan_version`` and ``company`` are nullable, so the joins are OUTER
    # joins; PostgreSQL refuses FOR UPDATE on those unless the lock is limited
    # to this table. SQLite ignores FOR UPDATE entirely, which is why the test
    # suite never saw the failure.
    registration = (
        RegistrationRequest.objects.select_for_update(of=("self",))
        .select_related("plan_version__plan", "company")
        .get(pk=request_id)
    )
    if registration.status == RegistrationRequest.PROVISIONED:
        return registration, None
    if registration.status != RegistrationRequest.APPROVED:
        raise ValueError("Only approved registration requests can be provisioned.")
    if registration.delivery_mode != RegistrationRequest.SAAS:
        raise ValueError(
            "Standalone requests are prepared through the standalone delivery process."
        )
    if not registration.plan_version_id:
        raise ValueError("A SaaS registration needs a published plan.")
    if User.objects.filter(email__iexact=registration.email).exists():
        raise ValueError("The contact email already belongs to an account.")

    owner_role, _ = Role.objects.get_or_create(
        name="Business Owner", defaults={"scope_level": Role.SCOPE_BUSINESS}
    )
    if owner_role.scope_level != Role.SCOPE_BUSINESS:
        raise ValueError("The Business Owner role has an invalid scope.")

    if not plan_version_is_available(registration.plan_version):
        raise ValueError("The selected plan is no longer available for registration.")

    company = Company.objects.create(
        name=registration.company_name,
        legal_name=registration.company_name,
        email=registration.email,
        phone=registration.phone,
        currency=registration.plan_version.currency,
        business_type=Company.TYPE_ENTERPRISE,
        business_type_chosen=False,
    )
    main_branch = Branch.objects.create(
        company=company, name="Main Branch", code="MAIN"
    )
    owner = User.objects.create_user(
        email=registration.email,
        password=None,
        full_name=registration.contact_name,
        company=company,
        branch=main_branch,
        role=owner_role,
    )
    owner.set_unusable_password()
    owner.save(update_fields=["password"])

    now = timezone.now()
    trial_days = getattr(settings, "VEZANO_TRIAL_DAYS", 14)
    subscription = Subscription.objects.create(
        company=company,
        plan_version=registration.plan_version,
        status=Subscription.TRIALING,
        starts_at=now,
        trial_ends_at=now + timedelta(days=trial_days),
    )
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="trial_provisioned",
        to_status=Subscription.TRIALING,
        actor=actor,
        metadata={"registration_request_id": registration.pk},
    )
    token = _issue_owner_invitation(registration, owner, now)
    registration.company = company
    registration.status = RegistrationRequest.PROVISIONED
    registration.mark_reviewed(actor)
    registration.save(
        update_fields=["company", "status", "reviewed_by", "reviewed_at", "updated_at"]
    )
    log_activity(
        action="create", user=actor, company=company, request=request,
        entity_type="RegistrationProvision", entity_id=registration.pk,
        metadata={"subscription_id": subscription.pk, "owner_id": owner.pk},
    )
    return registration, token


@transaction.atomic
def reissue_owner_invitation(request_id, actor, request=None):
    """Mint a new activation link for an already provisioned company.

    Covers the two real-world cases: the 7-day link expired before the owner
    opened it, or it was lost. The previous link stops working immediately.
    """
    registration = (
        RegistrationRequest.objects.select_for_update(of=("self",))
        .select_related("company")
        .get(pk=request_id)
    )
    if registration.status != RegistrationRequest.PROVISIONED or not registration.company_id:
        raise ValueError("Only provisioned registration requests have an owner invitation.")
    owner = (
        registration.company.users.filter(role__name="Business Owner", is_active=True)
        .order_by("pk")
        .first()
    )
    if owner is None:
        raise ValueError("The company has no active owner to invite.")
    now = timezone.now()
    token = _issue_owner_invitation(registration, owner, now)
    log_activity(
        action="update", user=actor, company=registration.company, request=request,
        entity_type="OwnerInvitation", entity_id=registration.pk,
        metadata={"event": "reissued", "owner_id": owner.pk},
    )
    return registration, token


@transaction.atomic
def accept_owner_invitation(token, password, request=None):
    invitation = (
        OwnerInvitation.objects.select_for_update(of=("self",))
        .select_related("owner", "registration_request")
        .filter(token_hash=_token_hash(token))
        .first()
    )
    if invitation is None or not invitation.is_usable:
        raise ValueError("This invitation is invalid, expired, or already used.")
    owner = invitation.owner
    if not owner.is_active or (owner.company_id and not owner.company.is_active):
        raise ValueError("This account is no longer active. Contact the platform team.")
    invitation.owner.set_password(password)
    invitation.owner.save(update_fields=["password"])
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    log_activity(
        action="update", user=invitation.owner, company=invitation.owner.company,
        request=request,
        entity_type="OwnerInvitation", entity_id=invitation.pk,
        metadata={"event": "accepted"},
    )
    return invitation.owner
