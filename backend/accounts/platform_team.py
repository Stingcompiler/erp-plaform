"""Managing the Vezano platform team from inside the product.

Platform members are company-less users holding a platform-scoped role
(see ``User.is_platform_admin``). Until now the only way to add one was the
Django admin; these services give the platform page a first-class,
audited path with the same one-time activation link owners receive.
"""

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import PlatformInvitation, Role, User
from core.activity import log_activity

PLATFORM_ROLE = "Super Administrator"
INVITATION_TTL = timedelta(days=7)


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def platform_members():
    """Everyone who counts as a platform admin: superusers or platform-role users."""
    return User.objects.select_related("role").filter(
        Q(is_superuser=True) | Q(company__isnull=True, role__scope_level=Role.SCOPE_PLATFORM)
    ).order_by("-is_active", "email")


def platform_role():
    role, _ = Role.objects.get_or_create(
        name=PLATFORM_ROLE, defaults={"scope_level": Role.SCOPE_PLATFORM}
    )
    if role.scope_level != Role.SCOPE_PLATFORM:
        raise ValidationError("The platform role is misconfigured; contact support.")
    return role


def _issue_invitation(user, actor, now):
    token = secrets.token_urlsafe(32)
    PlatformInvitation.objects.filter(
        user=user, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)
    PlatformInvitation.objects.create(
        token_hash=_token_hash(token), user=user, invited_by=actor,
        expires_at=now + INVITATION_TTL,
    )
    return token


@transaction.atomic
def invite_platform_member(email, full_name, actor, request=None):
    email = User.objects.normalize_email(email).strip()
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError({"email": "This email already belongs to an account."})
    user = User.objects.create_user(
        email=email, password=None, full_name=full_name.strip(),
        company=None, branch=None, role=platform_role(),
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    token = _issue_invitation(user, actor, timezone.now())
    log_activity(
        action="create", user=actor, request=request,
        entity_type="PlatformMember", entity_id=user.pk,
        metadata={"email": user.email, "invited_by": actor.pk},
    )
    return user, token


@transaction.atomic
def reissue_platform_invitation(user_id, actor, request=None):
    user = platform_members().select_for_update(of=("self",)).get(pk=user_id)
    if not user.is_active:
        raise ValidationError("Reactivate the member before sending a new link.")
    token = _issue_invitation(user, actor, timezone.now())
    log_activity(
        action="update", user=actor, request=request,
        entity_type="PlatformInvitation", entity_id=user.pk,
        metadata={"event": "reissued", "member_id": user.pk},
    )
    return user, token


@transaction.atomic
def set_platform_member_active(user_id, is_active, actor, request=None):
    """Enable/disable a member. The platform can never lose its last active admin,
    and nobody can lock themselves out."""
    user = platform_members().select_for_update(of=("self",)).get(pk=user_id)
    if user.pk == actor.pk and not is_active:
        raise ValidationError("You cannot deactivate your own account.")
    if not is_active and user.is_active:
        others = platform_members().filter(is_active=True).exclude(pk=user.pk).count()
        if others == 0:
            raise ValidationError("The platform must keep at least one active administrator.")
    if user.is_active != is_active:
        user.is_active = is_active
        user.save(update_fields=["is_active"])
        if not is_active:
            PlatformInvitation.objects.filter(
                user=user, accepted_at__isnull=True, revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
        log_activity(
            action="update", user=actor, request=request,
            entity_type="PlatformMember", entity_id=user.pk,
            metadata={"is_active": is_active},
        )
    return user


@transaction.atomic
def accept_platform_invitation(token, password, request=None):
    invitation = (
        PlatformInvitation.objects.select_for_update(of=("self",))
        .select_related("user")
        .filter(token_hash=_token_hash(token))
        .first()
    )
    if invitation is None or not invitation.is_usable:
        raise ValueError("This invitation is invalid, expired, or already used.")
    user = invitation.user
    if not user.is_active:
        raise ValueError("This account is no longer active. Contact the platform team.")
    user.set_password(password)
    user.save(update_fields=["password"])
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    log_activity(
        action="update", user=user, request=request,
        entity_type="PlatformInvitation", entity_id=invitation.pk,
        metadata={"event": "accepted"},
    )
    return user
