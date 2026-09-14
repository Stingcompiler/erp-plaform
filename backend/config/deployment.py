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
