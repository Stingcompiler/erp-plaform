"""The branch-policy registry must match the deployed viewsets exactly.

The registry exists so that "who sees this across branches?" is answered in
one reviewed file instead of by the presence or absence of ``branch_field``.
These tests pin both directions: the live code is consistent, and each way
of drifting (unregistered model, contradicting policy, stale entry) is
caught by the system check rather than shipping silently.
"""

from unittest import mock

from django.test import SimpleTestCase

from core import branch_policy
from core.branch_policy import BRANCH, COMPANY_WIDE, REGISTRY, policy_violations


class BranchPolicyRegistryTests(SimpleTestCase):
    def test_live_registry_is_consistent(self):
        self.assertEqual(policy_violations(), [])

    def test_review_flagged_resources_have_documented_policies(self):
        # The 2026-09 review named these as ambiguous; they must stay
        # deliberate: company-wide with a written reason.
        flagged = ("sales.Customer", "purchasing.Supplier", "purchasing.Bill", "finance.Expense")
        for label in flagged:
            policy, reason = REGISTRY[label]
            self.assertEqual(policy, COMPANY_WIDE, label)
            self.assertTrue(reason, f"{label} needs a documented reason")

    def test_unregistered_model_is_reported(self):
        registry = dict(REGISTRY)
        registry.pop("sales.Customer")
        with mock.patch.object(branch_policy, "REGISTRY", registry):
            problems = policy_violations()
        self.assertTrue(any("sales.Customer" in p and "no branch policy" in p for p in problems))

    def test_policy_contradicting_the_viewset_is_reported(self):
        # Invoice's viewset filters by branch; registering it COMPANY_WIDE
        # must fail, and so must the reverse (Customer as BRANCH).
        registry = dict(REGISTRY)
        registry["sales.Invoice"] = (COMPANY_WIDE, "wrong on purpose")
        registry["sales.Customer"] = (BRANCH, None)
        with mock.patch.object(branch_policy, "REGISTRY", registry):
            problems = policy_violations()
        self.assertTrue(any("sales.Invoice" in p and "COMPANY_WIDE" in p for p in problems))
        self.assertTrue(any("sales.Customer" in p and "no branch_field" in p for p in problems))

    def test_stale_entry_is_reported(self):
        registry = dict(REGISTRY)
        registry["sales.Ghost"] = (COMPANY_WIDE, "model no longer exists")
        with mock.patch.object(branch_policy, "REGISTRY", registry):
            problems = policy_violations()
        self.assertTrue(any("sales.Ghost" in p and "stale" in p for p in problems))
