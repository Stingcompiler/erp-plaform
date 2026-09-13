import logging
from dataclasses import asdict, dataclass
from datetime import datetime

from django.utils import timezone

from config.deployment import get_deployment_config

logger = logging.getLogger(__name__)

ALL_MODULES = frozenset(
    {
        "users",
        "org",
        "inventory",
        "sales",
        "purchasing",
        "sales_returns",
        "purchase_returns",
        "reports",
        "hr",
        "crm",
        "finance",
        "website",
        "settings",
    }
)


@dataclass(frozen=True)
class EntitlementDecision:
    source: str
    state: str
    modules: frozenset
    limits: dict
    allow_writes: bool
    valid_until: datetime | None = None
    reason: str = ""

    def allows_module(self, module):
        return not module or "*" in self.modules or module in self.modules

    def as_dict(self):
        data = asdict(self)
        data["modules"] = sorted(self.modules)
        data["valid_until"] = self.valid_until.isoformat() if self.valid_until else None
        return data


def unrestricted(source="policy_disabled", state="active"):
    return EntitlementDecision(source, state, frozenset({"*"}), {}, True)


def _saas_decision(company, now):
    try:
        subscription = company.subscription
    except Exception:
        # Existing companies receive explicit legacy rows in the data
        # migration. A later company must be provisioned with a trial or plan.
        return EntitlementDecision(
            "saas",
            "unprovisioned",
            frozenset(),
            {},
            False,
            reason="No subscription has been provisioned.",
        )

    state = subscription.status
    if state == subscription.LEGACY:
        decision = unrestricted("saas", state)
    else:
        if (
            state == subscription.TRIALING
            and subscription.trial_ends_at
            and now > subscription.trial_ends_at
        ):
            state = (
                subscription.GRACE
                if subscription.grace_ends_at and now <= subscription.grace_ends_at
                else subscription.READ_ONLY
            )
        elif (
            state == subscription.GRACE
            and (not subscription.grace_ends_at or now >= subscription.grace_ends_at)
        ):
            state = subscription.READ_ONLY
        elif (
            state == subscription.ACTIVE
            and subscription.period_ends_at
            and now > subscription.period_ends_at
        ):
            state = (
                subscription.GRACE
                if subscription.grace_ends_at and now <= subscription.grace_ends_at
                else subscription.READ_ONLY
            )
        # An explicitly empty plan means it includes no business modules. Only
        # the legacy plan carries an explicit wildcard entitlement.
        modules = frozenset(subscription.plan_version.modules or [])
        allow_writes = state in {subscription.TRIALING, subscription.ACTIVE, subscription.GRACE}
        decision = EntitlementDecision(
            "saas",
            state,
            modules,
            dict(subscription.plan_version.limits or {}),
            allow_writes,
            # Whichever boundary applies to the current state: a trial ends at
            # trial_ends_at, a paid period at period_ends_at, and grace extends
            # either one.
            subscription.grace_ends_at
            or (
                subscription.trial_ends_at
                if subscription.status == subscription.TRIALING
                else subscription.period_ends_at
            ),
            subscription.suspended_reason,
        )

    overrides = company.entitlement_overrides.filter(starts_at__lte=now, ends_at__gt=now)
    modules, limits, allow_writes = (
        set(decision.modules),
        dict(decision.limits),
        decision.allow_writes,
    )
    valid_until = decision.valid_until
    for override in overrides:
        modules.update(override.modules or [])
        limits.update(override.limits or {})
        if override.allow_writes is not None:
            allow_writes = override.allow_writes
        valid_until = min(filter(None, [valid_until, override.ends_at]), default=None)
    return EntitlementDecision(
        decision.source,
        decision.state,
        frozenset(modules),
        limits,
        allow_writes,
        valid_until,
        decision.reason,
    )


def resolve_entitlements(company=None, now=None, *, apply_policy=True):
    config = get_deployment_config()
    if config.entitlement_policy == "disabled":
        return unrestricted()
    now = now or timezone.now()
    if config.is_standalone:
        from licensing.services import resolve_license_entitlements

        return resolve_license_entitlements(now=now)
    if company is None:
        return unrestricted("platform", "active")
    decision = _saas_decision(company, now)
    if config.entitlement_policy == "observe" and apply_policy:
        if not decision.allow_writes or "*" not in decision.modules or decision.limits:
            logger.warning(
                "subscription_observe company=%s state=%s source=%s",
                company.pk,
                decision.state,
                decision.source,
            )
        # Observation records the real state but never blocks modules, writes,
        # or quotas. Enforcement can therefore be compared safely first.
        return EntitlementDecision(
            decision.source,
            decision.state,
            frozenset({"*"}),
            {},
            True,
            decision.valid_until,
            decision.reason,
        )
    return decision
