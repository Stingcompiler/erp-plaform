"""Remove credential material that earlier releases wrote to the audit trail.

`ActivityLoggingMixin._capture_changes` used to snapshot every field in
validated_data, so an administrator's password reset stored the plaintext
(before) and the new hash (after) under metadata.changes.password. The mixin
now excludes write-only and sensitive fields; this migration cleans what is
already stored. Rows are edited in place because the alternative — leaving
hashes readable to every audit viewer — is the greater breach of Rule #9.
"""

from django.db import migrations

SENSITIVE_SUFFIXES = ("password", "token", "secret", "signature")


def _is_sensitive(name):
    lowered = str(name).lower()
    return any(lowered.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


def scrub(apps, schema_editor):
    ActivityLog = apps.get_model("core", "ActivityLog")
    queryset = ActivityLog.objects.filter(metadata__has_key="changes").only("id", "metadata")
    for row in queryset.iterator(chunk_size=500):
        changes = row.metadata.get("changes")
        if not isinstance(changes, dict):
            continue
        removed = [key for key in changes if _is_sensitive(key)]
        if not removed:
            continue
        for key in removed:
            changes.pop(key, None)
        row.metadata["changes"] = changes
        row.metadata["redacted_fields"] = sorted(
            set(row.metadata.get("redacted_fields", [])) | set(removed)
        )
        row.save(update_fields=["metadata"])


class Migration(migrations.Migration):
    dependencies = [("core", "0004_cache_table")]

    operations = [migrations.RunPython(scrub, migrations.RunPython.noop)]
