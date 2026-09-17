from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


SAAS = "saas"
STANDALONE = "standalone"
DEPLOYMENT_MODES = {SAAS, STANDALONE}
POLICY_MODES = {"disabled", "observe", "enforce"}


@dataclass(frozen=True)
class DeploymentConfig:
    mode: str
    entitlement_policy: str

    @property
    def is_standalone(self):
        return self.mode == STANDALONE


def get_deployment_config():
    mode = settings.VEZANO_DEPLOYMENT_MODE.lower().strip()
    policy = settings.SUBSCRIPTION_POLICY.lower().strip()
    if mode not in DEPLOYMENT_MODES:
        raise ImproperlyConfigured("VEZANO_DEPLOYMENT_MODE must be saas or standalone")
    if policy not in POLICY_MODES:
        raise ImproperlyConfigured("SUBSCRIPTION_POLICY must be disabled, observe or enforce")
    # A standalone installation is governed by its licence, full stop. The
    # observe/disabled modes exist for rolling out enforcement across SaaS
    # tenants; on a customer's own server they would make the licence
    # decorative, so the setting is ignored there.
    if mode == STANDALONE:
        policy = "enforce"
    return DeploymentConfig(mode=mode, entitlement_policy=policy)


def assert_mode_matches_installation():
    """Once an Installation row exists, its recorded deployment_mode is the
    truth. Flipping VEZANO_DEPLOYMENT_MODE in the env file over a live
    database (standalone -> saas to escape the licence, or the reverse) is a
    misconfiguration and the process must not serve with it. Called from the
    preflight check and the web/worker entrypoints; returns None when the
    installation table is not there yet (first migrate)."""
    from django.db import DatabaseError

    try:
        from licensing.models import Installation

        installation = Installation.objects.order_by("pk").first()
    except (DatabaseError, RuntimeError, ImportError):
        return None
    if installation is None:
        return None
    configured = get_deployment_config().mode
    if installation.deployment_mode != configured:
        raise ImproperlyConfigured(
            f"VEZANO_DEPLOYMENT_MODE={configured} but this installation was created "
            f"as {installation.deployment_mode}. The mode is fixed for the life of "
            "the database; restore the correct value in the environment file."
        )
    return installation.deployment_mode
