from django.db import migrations, models
from django.db.models import Q


def keep_one_highlight(apps, schema_editor):
    """Several plans may carry the "most popular" badge today. Keep the one
    the pricing page lists first — public and active before hidden ones,
    then the lowest sort_order — and clear the rest. Nothing else changes."""
    Plan = apps.get_model("subscriptions", "Plan")
    highlighted = sorted(
        Plan.objects.filter(is_highlighted=True),
        key=lambda plan: (
            not (plan.is_public and plan.is_active), plan.sort_order, plan.name, plan.pk,
        ),
    )
    extra = [plan.pk for plan in highlighted[1:]]
    if extra:
        Plan.objects.filter(pk__in=extra).update(is_highlighted=False)


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0009_owner_tenant_controls"),
    ]

    operations = [
        migrations.RunPython(keep_one_highlight, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="plan",
            constraint=models.UniqueConstraint(
                condition=Q(is_highlighted=True),
                fields=("is_highlighted",),
                name="uniq_highlighted_plan",
            ),
        ),
    ]
