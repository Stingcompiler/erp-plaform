"""Whether a tenant user's company lets them in at all.

Two platform decisions close a company to its people, and both are checked
on every authenticated request (accounts.authentication) and at sign-in
(accounts.views.LoginView):

* **Deleted** (``Company.is_active`` false, a deletion scheduled): nobody
  signs in, every session ends (401 ``company_inactive``).
* **Suspended until payment** (subscriptions.tenant_controls): staff cannot
  sign in; the owner can, and reaches only what paying needs. Every other
  API call answers 403 ``suspended_unpaid`` with the platform's reason.

What stays open while suspended until payment:

* for everyone already signed in: identity and sign-out (``/api/auth/``),
  the app shell's permission map and preferences, the health probe, and the
  offline upload (``/api/sync/push/``) — which accepts only work captured
  before the suspension (sync.views);
* for the owner, also the subscription area (``/api/subscription/``: status,
  invoices, the next renewal, payment recording, plan changes) and the
  deployment flag the subscription page reads.

Platform members and company-less identities are never affected. This is a
platform action, so it applies whatever SUBSCRIPTION_POLICY says; a
standalone installation has no platform and is never affected.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException, AuthenticationFailed

from config.deployment import get_deployment_config

SUSPENDED_UNPAID = "suspended_unpaid"
COMPANY_SUSPENDED = "company_suspended"
COMPANY_INACTIVE = "company_inactive"

OPEN_TO_EVERYONE = (
    "/api/auth/",
    "/api/rbac/access/",
    "/api/ops/preferences/",
    "/api/health/",
    "/api/sync/push/",
)
OPEN_TO_OWNER = OPEN_TO_EVERYONE + (
    "/api/subscription/",
    "/api/deployment/",
)


class CompanySuspendedUnpaid(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = SUSPENDED_UNPAID


def owner_message():
    return _(
        "The company account is suspended until payment. Record the payment on "
        "the subscription page; the account reopens once it is approved."
    )


def staff_message():
    return _("The company account is temporarily suspended — contact the company owner.")


def inactive_message():
    return _("This company account has been closed.")


def company_state(company_id):
    """``None`` when the company is open, else ``{"state", "reason", "since"}``
    with state ``company_inactive`` or ``suspended_unpaid``."""
    if not company_id or get_deployment_config().is_standalone:
        return None
    from org.models import Company
    from subscriptions.models import Subscription

    row = Company.objects.filter(pk=company_id).values(
        "is_active", "subscription__status", "subscription__suspension_kind",
        "subscription__suspended_reason", "subscription__suspended_at",
    ).first()
    if row is None:
        return None
    if not row["is_active"]:
        return {"state": COMPANY_INACTIVE, "reason": "", "since": None}
    if (
        row["subscription__status"] == Subscription.SUSPENDED
        and row["subscription__suspension_kind"] == Subscription.SUSPENSION_UNPAID
    ):
        return {
            "state": SUSPENDED_UNPAID,
            "reason": row["subscription__suspended_reason"] or "",
            "since": row["subscription__suspended_at"],
        }
    return None


def _is_owner(user):
    from subscriptions.tenant_controls import is_company_owner

    return is_company_owner(user)


def refusal_for_login(user):
    """The sign-in refusal for ``user`` as ``(code, detail)``, or None."""
    if getattr(user, "is_platform_admin", False):
        return None
    state = company_state(getattr(user, "company_id", None))
    if state is None:
        return None
    if state["state"] == COMPANY_INACTIVE:
        return COMPANY_INACTIVE, inactive_message()
    if _is_owner(user):
        return None
    return COMPANY_SUSPENDED, staff_message()


def check_request(user, path):
    """Raise when ``user``'s company closes ``path`` to them."""
    if getattr(user, "is_platform_admin", False):
        return
    state = company_state(getattr(user, "company_id", None))
    if state is None:
        return
    if state["state"] == COMPANY_INACTIVE:
        raise AuthenticationFailed(inactive_message(), code=COMPANY_INACTIVE)
    owner = _is_owner(user)
    if path.startswith(OPEN_TO_OWNER if owner else OPEN_TO_EVERYONE):
        return
    raise CompanySuspendedUnpaid({
        "code": SUSPENDED_UNPAID,
        "detail": owner_message() if owner else staff_message(),
        "reason": state["reason"],
    })


def state_for_me(user):
    """What the identity call tells the app shell about the company."""
    if getattr(user, "is_platform_admin", False):
        return None
    state = company_state(getattr(user, "company_id", None))
    if state is None:
        return None
    return {
        "state": state["state"],
        "reason": state["reason"],
        "since": state["since"].isoformat() if state["since"] else None,
        "is_owner": _is_owner(user),
    }
