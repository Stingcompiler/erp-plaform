from django.core.management.base import BaseCommand

from accounts.models import Role

# The fixed role set from erp_ai_agent_build_plan.md M1, grouped by scope.
ROLE_DEFINITIONS = [
    ("Super Administrator", Role.SCOPE_PLATFORM, "Platform owner; not company-scoped."),
    ("Business Owner", Role.SCOPE_BUSINESS, "Owns a tenant company."),
    ("General Manager", Role.SCOPE_BUSINESS, "Company-wide management."),
    ("Branch Manager", Role.SCOPE_BRANCH, "Manages a single branch."),
    ("Inventory Officer", Role.SCOPE_BRANCH, "Manages stock at branch level."),
    ("Sales Officer", Role.SCOPE_BRANCH, "Handles sales/POS at branch level."),
    ("Purchasing Officer", Role.SCOPE_BRANCH, "Handles purchasing at branch level."),
    ("HR Officer", Role.SCOPE_BRANCH, "Manages HR records."),
    ("CRM Officer", Role.SCOPE_BRANCH, "Manages CRM records."),
    ("Finance Department", Role.SCOPE_BUSINESS, "Manages expenses and company funds."),
    (
        "Chief Financial Officer",
        Role.SCOPE_BUSINESS,
        "Approves high-value payments and owns financial reporting.",
    ),
    ("Landing Page Manager", Role.SCOPE_BRANCH, "Edits the public website."),
    ("Viewer", Role.SCOPE_BRANCH, "Read-only access."),
]


class Command(BaseCommand):
    help = "Seed the fixed platform role set (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for name, scope, description in ROLE_DEFINITIONS:
            _, was_created = Role.objects.get_or_create(
                name=name,
                defaults={"scope_level": scope, "description": description},
            )
            created += int(was_created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Roles ensured: {len(ROLE_DEFINITIONS)} total, {created} newly created."
            )
        )
