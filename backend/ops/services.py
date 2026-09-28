"""
Logical per-company backup and restore.

`dump_company` produces a JSON-serializable snapshot of a company's master and
transactional data. `restore_master` re-creates the master data into an EMPTY
target company (transactional records are captured in the dump but not replayed
— see the milestone notes). Every backup/restore writes a BackupRecord (Rule
#8), and the snapshot is derived live from the tables (nothing stored to drift).
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, transaction
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

BACKUP_VERSION = 1


def dump_company(company):
    from inventory.models import (
        Brand, Category, Product, StockMovement, Unit, Warehouse,
    )
    from purchasing.models import Bill, Supplier
    from sales.models import Customer, Invoice, InvoiceLine, Payment

    def rows(qs, fields):
        return list(qs.filter(company=company).values(*fields))

    data = {
        "version": BACKUP_VERSION,
        "company": {
            "id": company.id, "name": company.name,
            "slug": company.slug, "currency": company.currency,
        },
        "master": {
            "categories": rows(Category.objects, ["id", "name", "parent", "is_active"]),
            "brands": rows(Brand.objects, ["id", "name", "is_active"]),
            "units": rows(Unit.objects, ["id", "name", "symbol", "is_active"]),
            "warehouses": rows(Warehouse.objects, ["id", "name", "code", "is_active"]),
            "products": rows(Product.objects, [
                "id", "sku", "name", "category", "brand", "unit", "barcode",
                "qr_code", "cost_price", "sale_price", "reorder_level",
                "track_batches", "is_active",
            ]),
            "customers": rows(Customer.objects, [
                "id", "name", "phone", "email", "address", "is_active",
            ]),
            "suppliers": rows(Supplier.objects, [
                "id", "name", "phone", "email", "address", "is_active",
            ]),
        },
        "transactional": {
            "invoices": rows(Invoice.objects, [
                "id", "number", "customer", "warehouse", "subtotal",
                "tax_amount", "total", "issued_at",
            ]),
            "invoice_lines": list(
                InvoiceLine.objects.filter(invoice__company=company).values(
                    "id", "invoice", "product", "quantity", "unit_price",
                    "line_subtotal", "line_tax", "line_total",
                )
            ),
            "payments": rows(Payment.objects, [
                "id", "invoice", "method", "amount", "recorded_at",
            ]),
            "stock_movements": rows(StockMovement.objects, [
                "id", "product", "warehouse", "movement_type", "quantity",
                "created_at",
            ]),
            "bills": rows(Bill.objects, [
                "id", "supplier", "total", "is_void", "created_at",
            ]),
        },
    }
    return data


def count_records(dump):
    total = 0
    for section in ("master", "transactional"):
        for rows in dump.get(section, {}).values():
            total += len(rows)
    return total


# How a restore treats the company it lands in.
EMPTY_ONLY = "empty"      # the original: refuse unless the company is empty
MISSING_ONLY = "missing"  # add only what is not there; never touch a live row
MODES = (EMPTY_ONLY, MISSING_ONLY)


def _key(value):
    """Match the way a person would: trimmed, case- and spacing-insensitive."""
    return " ".join(str(value or "").split()).casefold()


# What a restorable dump must carry per master section: the fields every row
# needs, and the fields that identify a row within the file (a second row
# with the same product SKU is a corrupted file, not a product to drop).
MASTER_SECTIONS = {
    "categories": {"required": ("name",), "keys": ()},
    "brands": {"required": ("name",), "keys": ()},
    "units": {"required": ("name",), "keys": ()},
    "warehouses": {"required": ("name",), "keys": ()},
    "products": {"required": ("sku", "name"), "keys": ("sku", "barcode")},
    "customers": {"required": ("name",), "keys": ()},
    "suppliers": {"required": ("name",), "keys": ()},
}
PRODUCT_NUMBERS = ("cost_price", "sale_price", "reorder_level")


class InvalidBackup(Exception):
    """The file cannot be restored. ``detail`` is the 400 body: the message
    plus the place in the file — ``section``, ``row`` (1-based) and
    ``field`` when one is to blame — so the owner can fix the file rather
    than guess. (A plain exception, not DRF's: DRF would turn the row
    number into a string.)"""

    def __init__(self, message, section, row=None, field=None):
        super().__init__(message)
        self.detail = {"code": "invalid_backup", "detail": message, "section": section}
        if row is not None:
            self.detail["row"] = row
        if field:
            self.detail["field"] = field


def validate_dump(dump):
    """Check the dump's shape before a single row is written (review F19):
    every section a list of records, every record with the fields the
    restore reads, numbers that are numbers, and no product listed twice.
    Returns the master section."""
    master = dump.get("master")
    if not isinstance(master, dict):
        raise InvalidBackup(_("The backup file has no master data section."), "master")
    for section, spec in MASTER_SECTIONS.items():
        rows = master.get(section) or []
        if not isinstance(rows, list):
            raise InvalidBackup(
                _("Section %(section)s must be a list of rows.") % {"section": section}, section,
            )
        seen = {key: {} for key in spec["keys"]}
        for row_no, row in enumerate(rows, start=1):
            where = {"section": section, "row": row_no}
            if not isinstance(row, dict):
                raise InvalidBackup(
                    _("Row %(row)s of %(section)s is not a record.") % where, section, row_no,
                )
            for field in spec["required"]:
                value = row.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise InvalidBackup(
                        _("Row %(row)s of %(section)s is missing %(field)s.")
                        % {**where, "field": field},
                        section, row_no, field,
                    )
            if section == "products":
                for field in PRODUCT_NUMBERS:
                    value = row.get(field)
                    if value is None or isinstance(value, bool):
                        continue
                    try:
                        Decimal(str(value))
                    except (InvalidOperation, ValueError):
                        raise InvalidBackup(
                            _("Row %(row)s of %(section)s: %(field)s is not a number.")
                            % {**where, "field": field},
                            section, row_no, field,
                        )
            for field in spec["keys"]:
                key = _key(row.get(field))
                if not key:
                    continue
                if key in seen[field]:
                    raise InvalidBackup(
                        _("Row %(row)s of %(section)s repeats the %(field)s of row %(other)s.")
                        % {**where, "field": field, "other": seen[field][key]},
                        section, row_no, field,
                    )
                seen[field][key] = row_no
    return master


def _write(section, row_no, create):
    """Run one row's insert; a database refusal names the row instead of
    surfacing as a server fault, and the surrounding transaction undoes
    everything before it."""
    try:
        return create()
    except (DatabaseError, DjangoValidationError, ValueError, TypeError,
            InvalidOperation) as exc:
        raise InvalidBackup(
            _("Row %(row)s of %(section)s could not be saved: %(error)s")
            % {"section": section, "row": row_no, "error": exc},
            section, row_no,
        )


def restore_master(target_company, dump, user=None, mode=EMPTY_ONLY, dry_run=False):
    """Re-create master data (categories, brands, units, warehouses, products,
    customers, suppliers) from a dump.

    ``mode=empty`` is the disaster case: the company must be empty, and the
    dump is replayed as it stands.

    ``mode=missing`` is the everyday one — someone deleted a product, or a
    price list was lost — and it is deliberately additive: a row whose natural
    key already exists (SKU or barcode for a product, name for everything
    else) is left exactly as it is, including its price. Nothing is ever
    overwritten or deleted, so running it twice changes nothing the second
    time, and ``dry_run`` answers "what would this do?" without writing.

    Returns ``{"added": {...}, "skipped": {...}, "restored": n, "mode": ...}``.

    The dump is validated before anything is written, and the write is one
    transaction: a row the database refuses midway undoes every row before
    it, so the company is as empty afterwards as it was and the corrected
    file can simply be sent again (review F19).
    """
    if mode not in MODES:
        raise ValidationError({"mode": _("Choose one of %(options)s.") % {
            "options": ", ".join(MODES),
        }})
    master = validate_dump(dump)
    with transaction.atomic():
        return _restore_master(target_company, master, mode, dry_run)


def _restore_master(target_company, master, mode, dry_run):
    from inventory.models import Brand, Category, Product, Unit, Warehouse
    from purchasing.models import Supplier
    from sales.models import Customer

    if mode == EMPTY_ONLY and Product.objects.filter(company=target_company).exists():
        raise ValidationError(
            _("Target company already has products; restore only into an empty company.")
        )

    added = {}
    skipped = {}

    def note(table, created):
        added[table] = added.get(table, 0) + (1 if created else 0)
        skipped[table] = skipped.get(table, 0) + (0 if created else 1)

    def existing_by_name(model):
        return {
            _key(name): pk
            for pk, name in model.objects.filter(
                company=target_company
            ).values_list("id", "name")
        }

    # id in the dump -> id in this company, whether the row was just created
    # or was already there under the same name.
    cat_map, brand_map, unit_map = {}, {}, {}
    for table, model, mapping, extra in (
        ("categories", Category, cat_map, lambda row: {}),
        ("brands", Brand, brand_map, lambda row: {}),
        ("units", Unit, unit_map, lambda row: {"symbol": row.get("symbol", "")}),
    ):
        known = existing_by_name(model)
        for row_no, row in enumerate(master.get(table) or [], start=1):
            match = known.get(_key(row.get("name")))
            if match is not None:
                if row.get("id") is not None:
                    mapping[row["id"]] = match
                note(table, created=False)
                continue
            if dry_run:
                note(table, created=True)
                continue
            obj = _write(table, row_no, lambda: model.objects.create(
                company=target_company, name=row["name"],
                is_active=row.get("is_active", True), **extra(row),
            ))
            known[_key(row["name"])] = obj.id
            if row.get("id") is not None:
                mapping[row["id"]] = obj.id
            note(table, created=True)

    known_warehouses = existing_by_name(Warehouse)
    for row_no, w in enumerate(master.get("warehouses") or [], start=1):
        if _key(w.get("name")) in known_warehouses:
            note("warehouses", created=False)
            continue
        if not dry_run:
            obj = _write("warehouses", row_no, lambda: Warehouse.objects.create(
                company=target_company, name=w["name"], code=w.get("code") or "",
                is_active=w.get("is_active", True),
            ))
            known_warehouses[_key(w["name"])] = obj.id
        note("warehouses", created=True)

    # A product is the same product when its SKU matches, or its barcode does
    # (a barcode is unique per company, and a scan must keep resolving to the
    # item already on the shelf).
    existing_skus = {
        _key(sku)
        for sku in Product.objects.filter(company=target_company).values_list("sku", flat=True)
    }
    existing_barcodes = {
        _key(code)
        for code in Product.objects.filter(company=target_company)
        .exclude(barcode="").values_list("barcode", flat=True)
    }
    for row_no, p in enumerate(master.get("products") or [], start=1):
        sku, barcode = _key(p.get("sku")), _key(p.get("barcode"))
        if (sku and sku in existing_skus) or (barcode and barcode in existing_barcodes):
            note("products", created=False)
            continue
        if not dry_run:
            _write("products", row_no, lambda: Product.objects.create(
                company=target_company, sku=p["sku"], name=p["name"],
                category_id=cat_map.get(p.get("category")),
                brand_id=brand_map.get(p.get("brand")),
                unit_id=unit_map.get(p.get("unit")),
                barcode=p.get("barcode") or "", qr_code=p.get("qr_code") or "",
                cost_price=p.get("cost_price") or 0, sale_price=p.get("sale_price") or 0,
                reorder_level=p.get("reorder_level") or 0,
                track_batches=bool(p.get("track_batches", False)),
                is_active=p.get("is_active", True),
            ))
        if sku:
            existing_skus.add(sku)
        if barcode:
            existing_barcodes.add(barcode)
        note("products", created=True)

    for table, model in (("customers", Customer), ("suppliers", Supplier)):
        known = existing_by_name(model)
        for row_no, row in enumerate(master.get(table) or [], start=1):
            if _key(row.get("name")) in known:
                note(table, created=False)
                continue
            if not dry_run:
                obj = _write(table, row_no, lambda: model.objects.create(
                    company=target_company, name=row["name"], phone=row.get("phone") or "",
                    email=row.get("email") or "", address=row.get("address") or "",
                    is_active=row.get("is_active", True),
                ))
                known[_key(row["name"])] = obj.id
            note(table, created=True)

    # `restored` counts what the old signature counted: the rows written.
    restored = sum(added.get(t, 0) for t in ("products", "customers", "suppliers"))
    return {
        "mode": mode,
        "dry_run": dry_run,
        "added": {t: n for t, n in added.items() if n},
        "skipped": {t: n for t, n in skipped.items() if n},
        "restored": restored,
    }
