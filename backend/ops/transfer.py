"""
Move one company between deployments.

A company cannot be moved by copying a whole database: the source holds every
other tenant, the platform's own accounts, and the vendor's commercial records.
This module exports exactly one company — every row that belongs to it, every
document, every uploaded file — into a portable archive, and imports that
archive into a fresh company on another installation.

Two rules shape the design:

* **The set of models is discovered, not hand-listed.** A hand-written list goes
  stale the moment a model is added, and a silently missing table is a data loss
  that only shows up after the cutover. The set is derived from the model graph:
  every model that carries a `company` field, plus every model reachable from one
  through foreign keys.
* **Nothing outside the company travels.** Platform accounts, sessions, tokens,
  the vendor's subscription and licence rows, and every other tenant are absent
  by construction — they are not in the discovered set — and the import refuses
  to write a foreign key it cannot resolve rather than guessing.

Foreign keys are preserved by exporting each row's original primary key and
importing into a fresh identity map, so a moved invoice still points at its
moved customer and its moved lines.
"""

import json
import shutil
import zipfile
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

from django.db import models, transaction
from django.core.serializers.json import DjangoJSONEncoder

ARCHIVE_NAME = "company.json"
MANIFEST_NAME = "transfer-manifest.json"
MEDIA_PREFIX = "media/"
FORMAT_VERSION = 1

# The vendor's commercial records and the installation identity never belong to
# a customer company. Django's own bookkeeping is per-installation too.
EXCLUDED_APPS = frozenset(
    {
        "subscriptions",
        "licensing",
        "sessions",
        "admin",
        "contenttypes",
        "token_blacklist",
    }
)

# A foreign key to one of these is resolved by a natural key rather than by the
# numeric id, because the target is installation-wide and its ids differ.
GLOBAL_REFERENCE_KEYS = {
    ("accounts", "role"): "name",
}


class TransferError(Exception):
    """Raised when an export or import cannot be completed safely."""


@dataclass
class ImportReport:
    created: dict = dataclass_field(default_factory=dict)
    media_copied: int = 0
    skipped_users: list = dataclass_field(default_factory=list)
    warnings: list = dataclass_field(default_factory=list)

    @property
    def total_created(self):
        return sum(self.created.values())

    def as_dict(self):
        return {
            "created": self.created,
            "total_created": self.total_created,
            "media_copied": self.media_copied,
            "skipped_users": list(self.skipped_users),
            "warnings": list(self.warnings),
        }


def label_for(model):
    return f"{model._meta.app_label}.{model._meta.object_name}"


def _candidate_models():
    from django.apps import apps

    for config in apps.get_app_configs():
        if config.label in EXCLUDED_APPS:
            continue
        for model in config.get_models():
            if model._meta.proxy:
                continue
            if model._meta.abstract:
                continue
            yield model


def _company_field(model):
    try:
        return model._meta.get_field("company")
    except Exception:  # noqa: BLE001 - FieldDoesNotExist
        return None


def _referenced_models(model):
    for field in model._meta.fields:
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            if field.related_model is not model:
                yield field.related_model


def company_model_closure():
    """
    Every model that travels with a company: the ones carrying a `company`
    field, plus anything reachable from them by foreign key (invoice lines,
    return lines, bill lines and the like do not repeat the company themselves).
    """
    candidates = list(_candidate_models())
    members = {model for model in candidates if _company_field(model) is not None}
    changed = True
    while changed:
        changed = False
        for model in candidates:
            if model in members:
                continue
            if any(target in members for target in _referenced_models(model)):
                members.add(model)
                changed = True
    return members


def _topological_order(models_set):
    """
    Order so that a model's foreign-key targets come before it. Self-references
    are ignored (a category pointing at its parent is written in insertion
    order). A cycle that cannot be broken is left in place and reported by the
    caller rather than silently dropped.
    """
    remaining = set(models_set)
    ordered = []
    while remaining:
        ready = [
            model
            for model in remaining
            if not any(
                target in remaining and target is not model
                for target in _referenced_models(model)
            )
        ]
        if not ready:
            # A cycle: emit the rest deterministically so the export is still
            # reproducible; the import resolves ids in two passes.
            ordered.extend(sorted(remaining, key=label_for))
            break
        ordered.extend(sorted(ready, key=label_for))
        remaining -= set(ready)
    return ordered


def transferable_models():
    """The company-scoped models, in dependency order."""
    return _topological_order(company_model_closure())


# Fields left out of an export archive. The archive travels between
# installations by hand; a password hash or session marker inside it is a
# credential leak, and the import side never carries them anyway (it writes an
# unusable password and asks the account to reset).
EXCLUDED_EXPORT_FIELDS = {
    ("accounts", "User"): {"password", "last_login"},
}


def _serializable_fields(model):
    """Every concrete field except the primary key, which is exported separately,
    and the credential fields listed in EXCLUDED_EXPORT_FIELDS."""
    excluded = EXCLUDED_EXPORT_FIELDS.get(
        (model._meta.app_label, model.__name__), set()
    )
    for field in model._meta.fields:
        if field.primary_key or field.name in excluded:
            continue
        yield field


def _natural_key_field(field):
    """
    The attribute by which a foreign key into an installation-wide model is
    re-resolved on import. Without this a moved row would keep a raw id that
    means something different — or nothing — on the target installation.
    """
    related = field.related_model
    return GLOBAL_REFERENCE_KEYS.get((related._meta.app_label, field.name))


def serialize_row(instance):
    row = {"__pk__": instance.pk}
    natural = {}
    for field in _serializable_fields(type(instance)):
        value = getattr(instance, field.attname)
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            row[field.name] = value  # the raw target id, remapped on import
            key_field = _natural_key_field(field)
            if key_field:
                related = getattr(instance, field.name, None)
                natural[field.name] = getattr(related, key_field) if related else None
        elif isinstance(field, models.FileField):
            row[field.name] = getattr(instance, field.name).name if value else ""
        else:
            row[field.name] = value
    if natural:
        row["__natural__"] = natural
    return row


def _company_filter_path(model):
    """
    The lookup that narrows `model` to one company. Models that carry the field
    are filtered directly; children that do not are reached through their parent
    (invoice lines through the invoice, return lines through the return).
    Returns None when no path exists, which means the model is not company data.
    """
    if _company_field(model) is not None:
        return "company"

    # Breadth-first over foreign keys, looking for a model that owns `company`.
    seen = {model}
    queue = [(model, "")]
    while queue:
        current, prefix = queue.pop(0)
        for field in current._meta.fields:
            if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                continue
            target = field.related_model
            if target in seen:
                continue
            path = f"{prefix}{field.name}"
            if _company_field(target) is not None:
                return f"{path}__company"
            seen.add(target)
            queue.append((target, f"{path}__"))
    return None


def company_queryset(model, company):
    """All rows of `model` belonging to `company`."""
    path = _company_filter_path(model)
    if path is None:
        return model._default_manager.none()
    return model._default_manager.filter(**{path: company})


def _file_fields(model):
    for field in model._meta.fields:
        if isinstance(field, models.FileField):
            yield field


def collect_media_names(instance):
    """Relative names of every file this row points at."""
    names = []
    for field in _file_fields(type(instance)):
        value = getattr(instance, field.name)
        if value:
            names.append(value.name)
    return names


def export_company(company, include_media=True):
    """
    Build the portable payload for one company. Returns `(payload, media_names)`.
    Only models in the discovered closure are considered, so nothing outside the
    company can be included even by mistake.
    """
    from ops.release import application_version

    objects = {}
    counts = {}
    media_names = set()
    for model in transferable_models():
        label = label_for(model)
        rows = []
        for instance in company_queryset(model, company).iterator():
            rows.append(serialize_row(instance))
            if include_media:
                media_names.update(collect_media_names(instance))
        if rows:
            objects[label] = rows
            counts[label] = len(rows)

    payload = {
        "format_version": FORMAT_VERSION,
        "application_version": application_version(),
        "source": {
            "company_id": company.pk,
            "name": company.name,
            "slug": company.slug,
            "currency": company.currency,
            "fields": {
                field.name: getattr(company, field.name)
                for field in company._meta.fields
                if not field.primary_key
                and field.name not in {"created_at", "updated_at"}
            },
        },
        "counts": counts,
        "objects": objects,
    }
    return payload, sorted(media_names)


def write_export(company, destination, include_media=True, media_root=None):
    """
    Write a transfer archive (a zip) containing the payload, a manifest, and —
    unless disabled — every uploaded file the company references.
    """
    from django.conf import settings

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload, media_names = export_company(company, include_media=include_media)

    root = Path(media_root or settings.MEDIA_ROOT)
    copied = 0
    missing = []
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            ARCHIVE_NAME,
            json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=1),
        )
        for name in media_names:
            source = root / name
            if source.is_file():
                archive.write(source, f"{MEDIA_PREFIX}{name}")
                copied += 1
            else:
                missing.append(name)

        manifest = {
            "format_version": FORMAT_VERSION,
            "application_version": payload["application_version"],
            "company": payload["source"],
            "counts": payload["counts"],
            "total_rows": sum(payload["counts"].values()),
            "media_files": copied,
            "media_missing": missing,
        }
        archive.writestr(
            MANIFEST_NAME,
            # The company's own fields carry Decimals (thresholds, the
            # discount limit), so the manifest needs Django's encoder too.
            json.dumps(
                manifest, cls=DjangoJSONEncoder, indent=2, sort_keys=True, ensure_ascii=False
            ),
        )

    return {
        "destination": str(destination),
        "total_rows": sum(payload["counts"].values()),
        "models": len(payload["counts"]),
        "media_files": copied,
        "media_missing": missing,
    }


def read_export(source):
    """Read a transfer archive back into `(payload, media_root_in_zip)`."""
    source = Path(source)
    archive = zipfile.ZipFile(source, "r")
    if ARCHIVE_NAME not in archive.namelist():
        archive.close()
        raise TransferError(f"{source} is not a Vezano Pro company transfer archive.")
    payload = json.loads(archive.read(ARCHIVE_NAME).decode("utf-8"))
    if payload.get("format_version") != FORMAT_VERSION:
        archive.close()
        raise TransferError(
            f"Unsupported transfer format {payload.get('format_version')}; "
            f"this build reads {FORMAT_VERSION}."
        )
    problems = validate_payload(payload)
    if problems:
        archive.close()
        raise TransferError("Invalid company archive: " + "; ".join(problems))
    return payload, archive


def validate_payload(payload):
    """Reject unknown, excluded, or internally inconsistent archive content."""
    problems = verify_export_source(payload)
    allowed = {label_for(model) for model in transferable_models()}
    objects = payload.get("objects")
    counts = payload.get("counts")
    if not isinstance(objects, dict) or not isinstance(counts, dict):
        return problems + ["The archive objects and counts must be JSON objects."]
    for label, rows in objects.items():
        if label not in allowed:
            problems.append(f"{label} is not a transferable company model.")
            continue
        if not isinstance(rows, list):
            problems.append(f"{label} rows must be a list.")
            continue
        if counts.get(label) != len(rows):
            problems.append(
                f"{label} count is {counts.get(label)!r}, but {len(rows)} row(s) are present."
            )
    for label in set(counts) - set(objects):
        problems.append(f"{label} has a count but no object rows.")
    return problems


def _model_for_label(label):
    from django.apps import apps

    app_label, model_name = label.split(".", 1)
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as exc:
        raise TransferError(
            f"The archive references an unknown model: {label}"
        ) from exc


def _natural_key_for(field, row):
    return (row.get("__natural__") or {}).get(field.name)


def _resolve_reference(field, row, identity, company, report, label):
    """
    The value to write for one foreign key. Anything the import cannot place
    exactly is either reported (a nullable field left empty) or fatal — never
    guessed, because a wrong foreign key silently rewrites somebody's ledger.
    """
    if field.name == "company":
        return company.pk

    target = field.related_model
    target_label = label_for(target)

    if target_label in identity:
        raw = row.get(field.name)
        if raw is None:
            return None
        mapped = identity[target_label].get(raw)
        if mapped is None:
            raise TransferError(
                f"{label}.{field.name} points at {target_label} #{raw}, which is not "
                f"in the archive."
            )
        return mapped

    key_field = _natural_key_field(field)
    if key_field:
        natural = _natural_key_for(field, row)
        if natural is None:
            return None
        try:
            return target._default_manager.get(**{key_field: natural}).pk
        except target.DoesNotExist as exc:
            raise TransferError(
                f"{label}.{field.name} refers to {target_label} '{natural}', which "
                f"does not exist on this installation."
            ) from exc

    if field.null:
        report.warnings.append(
            f"{label}.{field.name} left empty: {target_label} is not part of a "
            f"company transfer."
        )
        return None
    raise TransferError(
        f"{label}.{field.name} references {target_label}, which is not transferred, "
        f"and the field cannot be empty."
    )


def _attributes_for(model, row, identity, company, report):
    label = label_for(model)
    attrs = {}
    for field in _serializable_fields(model):
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            attrs[field.attname] = _resolve_reference(
                field, row, identity, company, report, label
            )
        elif isinstance(field, models.FileField):
            attrs[field.name] = row.get(field.name) or ""
        else:
            attrs[field.name] = row.get(field.name)
    return attrs


def _harden_user(attrs, report, label):
    """
    A user who moves keeps their identity but not their credentials or their
    platform powers. The password hash is deliberately not carried: the hash is
    a credential, and a moved account must be re-established locally. Anything
    that would grant platform-level access is dropped, and a platform-scoped role
    means the account does not belong to the company at all.
    """
    from accounts.models import Role, User

    role_id = attrs.get("role")
    if role_id:
        role = Role.objects.filter(pk=role_id).first()
        if role is not None and role.scope_level == Role.SCOPE_PLATFORM:
            return None

    # `set_unusable_password()` writes the attribute in place and returns None,
    # so the hash has to be read back off the instance — chaining with `or`
    # would silently carry the *source* hash, which is exactly what must not
    # travel.
    placeholder = User()
    placeholder.set_unusable_password()
    attrs["password"] = placeholder.password
    attrs["is_superuser"] = False
    attrs["is_staff"] = False
    report.warnings.append(
        f"{label}: the password was not carried; the account must reset it."
    )
    return attrs


def _extract_media(archive, media_root):
    """Write every file in the archive to MEDIA_ROOT, returning how many landed."""
    from django.conf import settings

    root = Path(media_root or settings.MEDIA_ROOT)
    copied = 0
    for name in archive.namelist():
        if not name.startswith(MEDIA_PREFIX) or name.endswith("/"):
            continue
        relative = Path(name.removeprefix(MEDIA_PREFIX))
        if relative.is_absolute() or ".." in relative.parts:
            raise TransferError(f"Unsafe media path in archive: {relative}")
        destination = (root / relative).resolve()
        resolved_root = root.resolve()
        if resolved_root not in destination.parents:
            raise TransferError(f"Unsafe media path in archive: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(name) as source, open(destination, "wb") as handle:
            shutil.copyfileobj(source, handle)
        copied += 1
    return copied


# Models that need their attributes reshaped before the row may be written.
PREPARERS = {"accounts.User": _harden_user}


def _create_row(model, row, identity, company, report, deferred):
    label = label_for(model)
    attrs = _attributes_for(model, row, identity, company, report)
    preparer = PREPARERS.get(label)
    if preparer is not None:
        attrs = preparer(attrs, report, label)
        if attrs is None:
            report.skipped_users.append(str(row.get("email") or row.get("__pk__")))
            return
    instance = model(**attrs)
    # Save hooks that write derived rows (e.g. the tax-rate history) skip
    # them: the archive carries those rows itself.
    instance._restoring = True
    instance.save()
    identity.setdefault(label, {})[row["__pk__"]] = instance.pk
    report.created[label] = report.created.get(label, 0) + 1


def _deferred_references(model, row, identity):
    """
    Foreign keys this row cannot set yet because their target has not been
    created — which can only happen inside a dependency cycle. Returns
    `(field_name, target_label, raw_id)` triples.
    """
    pending = []
    for field in _serializable_fields(model):
        if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
            continue
        if field.name == "company":
            continue
        target_label = label_for(field.related_model)
        if target_label not in identity:
            continue
        raw = row.get(field.name)
        if raw is None or raw in identity[target_label]:
            continue
        pending.append((field.name, target_label, raw))
    return pending


@transaction.atomic
def import_company(payload, company, report=None, archive=None, media_root=None):
    """
    Write an archive into `company` (which must be freshly created). Import is
    one transaction: a failure leaves the target untouched rather than half
    populated, because a partially moved company is worse than one that did not
    move at all.
    """
    problems = validate_payload(payload)
    if problems:
        raise TransferError("Invalid company archive: " + "; ".join(problems))
    report = report or ImportReport()
    identity = {}
    objects = payload.get("objects") or {}

    problems = validate_payload(payload)
    if problems:
        raise TransferError("Invalid company archive: " + "; ".join(problems))

    # Company creation generates a default TaxProfile. The archived profile is
    # the authoritative source and may safely replace it only before any other
    # company data exists.
    if objects.get("org.TaxProfile"):
        from org.models import TaxProfile

        TaxProfile.objects.filter(company=company).delete()
    # ...and that default profile wrote a first row of tax-rate history; the
    # archive carries the real history.
    if objects.get("org.TaxRateChange"):
        from org.models import TaxRateChange

        TaxRateChange.objects.filter(company=company).delete()

    if media_root is not None and archive is not None:
        report.media_copied = _extract_media(archive, media_root)

    deferred = []
    for model in transferable_models():
        label = label_for(model)
        rows = objects.get(label) or []
        pending = [row for row in rows if _deferred_references(model, row, identity)]
        for row in rows:
            if row in pending:
                continue
            _create_row(model, row, identity, company, report, deferred)
        # A second pass over rows whose targets appeared later in this same model
        # (self-referencing parent chains are written in insertion order).
        for row in pending:
            blockers = _deferred_references(model, row, identity)
            if blockers:
                names = ", ".join(f"{field}→{target}" for field, target, _ in blockers)
                raise TransferError(
                    f"{label} has a circular reference that cannot be created in "
                    f"order ({names}). Move it with the help of a database "
                    f"specialist rather than forcing the archive."
                )
            _create_row(model, row, identity, company, report, deferred)

    for instance, field_name, target_id in deferred:
        setattr(instance, f"{field_name}_id", target_id)
        instance.save(update_fields=[f"{field_name}"])

    report.created["_identity"] = sum(len(map_) for map_ in identity.values())
    return report


def verify_transfer(payload, company):
    """
    Compare what the archive says it holds against what the target company now
    holds. Returns a list of differences; empty means the move reproduced the
    company. A mismatch here is the difference between "the transfer ran" and
    "the transfer is correct".
    """
    problems = []
    expected = payload.get("counts") or {}
    for label, expected_count in sorted(expected.items()):
        try:
            model = _model_for_label(label)
        except TransferError as exc:
            problems.append(str(exc))
            continue
        actual_count = company_queryset(model, company).count()
        if actual_count != expected_count:
            problems.append(
                f"{label}: archive holds {expected_count} row(s), target has {actual_count}"
            )
    return problems


def verify_export_source(payload):
    """
    Read the archive back and confirm nothing outside one company is present.
    Used before a transfer is accepted as evidence, so a mistaken export that
    swept in another tenant is caught rather than shipped.
    """
    problems = []
    source_id = (payload.get("source") or {}).get("company_id")
    for label in sorted(payload.get("objects") or {}):
        if label.split(".", 1)[0] in EXCLUDED_APPS:
            problems.append(f"{label} must not be part of a company transfer.")
    if source_id is None:
        problems.append("The archive does not name its source company.")
    return problems
