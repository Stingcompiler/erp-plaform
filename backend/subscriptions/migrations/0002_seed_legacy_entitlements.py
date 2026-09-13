from django.db import migrations
from django.utils import timezone


def seed_legacy(apps, schema_editor):
    Company = apps.get_model("org", "Company")
    Plan = apps.get_model("subscriptions", "Plan")
    PlanVersion = apps.get_model("subscriptions", "PlanVersion")
    Subscription = apps.get_model("subscriptions", "Subscription")
    plan, _ = Plan.objects.get_or_create(
        code="legacy",
        defaults={
            "name": "Legacy access",
            "description": "Preserves access for companies created before subscriptions.",
            "is_public": False,
            "is_active": True,
        },
    )
    version, _ = PlanVersion.objects.get_or_create(
        plan=plan,
        version=1,
        defaults={
            "currency": "USD",
            "price": 0,
            "billing_cycle": "yearly",
            "modules": ["*"],
            "limits": {},
            "is_legacy": True,
            "published_at": timezone.now(),
        },
    )
    now = timezone.now()
    for company_id in Company.objects.values_list("id", flat=True).iterator():
        Subscription.objects.get_or_create(
            company_id=company_id,
            defaults={"plan_version": version, "status": "legacy", "starts_at": now},
        )


def unseed_legacy(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    PlanVersion = apps.get_model("subscriptions", "PlanVersion")
    Subscription = apps.get_model("subscriptions", "Subscription")
    Subscription.objects.filter(
        plan_version__plan__code="legacy", status="legacy"
    ).delete()
    PlanVersion.objects.filter(plan__code="legacy").delete()
    Plan.objects.filter(code="legacy").delete()


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial")]
    operations = [migrations.RunPython(seed_legacy, unseed_legacy)]
