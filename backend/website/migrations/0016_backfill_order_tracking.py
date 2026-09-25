"""Give every existing web order a tracking token and a name key, and its
history so far (received, then the confirm/reject decision if there was one),
so old orders track like new ones."""

import secrets

from django.db import migrations


def _name_key(name):
    from core.arabic import fold_arabic

    return fold_arabic(" ".join(str(name or "").split())).casefold()[:120]


def backfill(apps, schema_editor):
    PublicOrder = apps.get_model("website", "PublicOrder")
    PublicOrderEvent = apps.get_model("website", "PublicOrderEvent")
    for order in PublicOrder.objects.all().iterator():
        fields = []
        if not order.tracking_token:
            order.tracking_token = secrets.token_urlsafe(24)
            fields.append("tracking_token")
        key = _name_key(order.contact_name)
        if order.lookup_name != key:
            order.lookup_name = key
            fields.append("lookup_name")
        if fields:
            order.save(update_fields=fields)
        if PublicOrderEvent.objects.filter(order_id=order.pk).exists():
            continue
        events = [PublicOrderEvent(
            company_id=order.company_id, order_id=order.pk, from_status="", to_status="new",
            created_at=order.created_at,
        )]
        if order.status != "new":
            events.append(PublicOrderEvent(
                company_id=order.company_id, order_id=order.pk, from_status="new",
                to_status=order.status, note=order.decision_note or "",
                actor_id=order.decided_by_id,
                created_at=max(order.decided_at or order.created_at, order.created_at),
            ))
        PublicOrderEvent.objects.bulk_create(events)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0015_order_tracking_stages"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
