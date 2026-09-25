"""Give every existing registration and demo request its short public
reference (R… / D…) and the folded name / phone keys, so older requests are
found on vezano.app/track/ like new ones."""

import secrets

from django.db import migrations

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # website.orders.REFERENCE_ALPHABET


def _name_key(name):
    from core.arabic import fold_arabic

    return fold_arabic(" ".join(str(name or "").split())).casefold()[:120]


def _phone_key(phone):
    arabic = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    digits = "".join(ch for ch in str(phone or "").translate(arabic) if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else ""


def _reference(model, prefix):
    for _attempt in range(50):
        ref = prefix + "".join(secrets.choice(ALPHABET) for _i in range(6))
        if not model.objects.filter(public_reference=ref).exists():
            return ref
    raise RuntimeError("could not allocate a reference")


def backfill(apps, schema_editor):
    RegistrationRequest = apps.get_model("website", "RegistrationRequest")
    PlatformLead = apps.get_model("website", "PlatformLead")
    for row in RegistrationRequest.objects.all().iterator():
        if not row.public_reference:
            row.public_reference = _reference(RegistrationRequest, "R")
        row.lookup_name = _name_key(row.contact_name)
        row.lookup_company = _name_key(row.company_name)
        row.lookup_phone = _phone_key(row.phone)
        row.save(update_fields=[
            "public_reference", "lookup_name", "lookup_company", "lookup_phone",
        ])
    for row in PlatformLead.objects.all().iterator():
        if not row.public_reference:
            row.public_reference = _reference(PlatformLead, "D")
        row.lookup_name = _name_key(row.name)
        row.lookup_phone = _phone_key(row.phone)
        row.save(update_fields=["public_reference", "lookup_name", "lookup_phone"])


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0018_platform_request_tracking"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
