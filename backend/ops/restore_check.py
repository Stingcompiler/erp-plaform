"""
Data fingerprints for backup and restore verification.

A backup is only worth what a restore can prove. These helpers take a compact
fingerprint of the installation — how many rows each table holds and what the
media directory contains — so an operator can capture it at backup time and
compare it against the restored database afterwards.

Counts are read live from the tables (nothing is stored that could drift), and
only concrete, business-relevant models are counted: Django's own session and
token tables are excluded because they legitimately change between a backup and
a restore.
"""

from pathlib import Path

from django.conf import settings

# Session and token tables change on their own between backup and restore;
# counting them would produce false mismatches.
VOLATILE_APPS = frozenset({"sessions", "token_blacklist", "admin", "contenttypes"})


def counted_apps(excluded_apps=VOLATILE_APPS):
    """Labels of the apps whose rows a fingerprint should include."""
    from django.apps import apps

    return sorted(
        config.label
        for config in apps.get_app_configs()
        if config.label not in excluded_apps
    )


def _concrete_models(app_labels):
    from django.apps import apps

    for label in app_labels:
        for model in apps.get_app_config(label).get_models():
            if not model._meta.proxy:
                yield model


def model_counts(company_id=None, app_labels=None):
    """
    Row count per concrete model, keyed as `app_label.ModelName`. With a
    `company_id`, a model is counted only when it carries a `company` field;
    installation-wide models are skipped rather than silently mis-counted.
    """
    labels = app_labels or counted_apps()
    counts = {}
    for model in _concrete_models(labels):
        if company_id is not None and not has_company_field(model):
            continue
        key = f"{model._meta.app_label}.{model._meta.object_name}"
        rows = model._default_manager.all()
        if company_id is not None:
            rows = rows.filter(company_id=company_id)
        counts[key] = rows.count()
    return counts


def has_company_field(model):
    try:
        model._meta.get_field("company")
    except Exception:  # noqa: BLE001 - FieldDoesNotExist and friends
        return False
    return True


def media_inventory(root=None, with_hash=True):
    """File count, total bytes, and (optionally) a hash of the media tree."""
    from ops.release import sha256_tree

    root = Path(root or settings.MEDIA_ROOT)
    if not root.is_dir():
        return {"present": False, "files": 0, "bytes": 0, "sha256": ""}
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "present": True,
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "sha256": sha256_tree(root) if with_hash else "",
    }


def data_fingerprint(company_id=None, include_media=True, with_media_hash=False):
    """The comparable description of a database (and optionally its media)."""
    from ops.release import application_version

    fingerprint = {
        "application_version": application_version(),
        "company_id": company_id,
        "counts": model_counts(company_id=company_id),
    }
    if include_media:
        fingerprint["media"] = media_inventory(with_hash=with_media_hash)
    return fingerprint


def compare_fingerprints(expected, actual):
    """
    Human-readable differences between two fingerprints. An empty list means the
    restore reproduced every counted table and the media totals match.
    """
    problems = []
    expected_counts = expected.get("counts") or {}
    actual_counts = actual.get("counts") or {}

    for key in sorted(set(expected_counts) - set(actual_counts)):
        problems.append(f"Table missing after restore: {key} ({expected_counts[key]} rows)")
    for key in sorted(set(actual_counts) - set(expected_counts)):
        problems.append(f"Unexpected table after restore: {key} ({actual_counts[key]} rows)")
    for key in sorted(set(expected_counts) & set(actual_counts)):
        if expected_counts[key] != actual_counts[key]:
            problems.append(
                f"Row count differs for {key}: expected {expected_counts[key]}, "
                f"restored {actual_counts[key]}"
            )

    expected_media = expected.get("media")
    actual_media = actual.get("media")
    if expected_media and actual_media:
        for field in ("files", "bytes"):
            if expected_media.get(field) != actual_media.get(field):
                problems.append(
                    f"Media {field} differs: expected {expected_media.get(field)}, "
                    f"restored {actual_media.get(field)}"
                )
        if expected_media.get("sha256") and actual_media.get("sha256"):
            if expected_media["sha256"] != actual_media["sha256"]:
                problems.append("The media tree hash does not match the backup.")
    return problems
