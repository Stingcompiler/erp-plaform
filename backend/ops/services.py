"""
Logical per-company backup and restore.

`dump_company` produces a JSON-serializable snapshot of a company's master and
transactional data. `restore_master` re-creates the master data into an EMPTY
target company (transactional records are captured in the dump but not replayed
— see the milestone notes). Every backup/restore writes a BackupRecord (Rule
#8), and the snapshot is derived live from the tables (nothing stored to drift).
"""

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
    """
    from inventory.models import Brand, Category, Product, Unit, Warehouse
    from purchasing.models import Supplier
    from sales.models import Customer

    if mode not in MODES:
        raise ValidationError({"mode": f"Choose one of {', '.join(MODES)}."})
    if mode == EMPTY_ONLY and Product.objects.filter(company=target_company).exists():
        raise ValidationError(
            _("Target company already has products; restore only into an empty company.")
        )

    master = dump.get("master", {})
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
        for row in master.get(table, []):
            match = known.get(_key(row.get("name")))
            if match is not None:
                mapping[row["id"]] = match
                note(table, created=False)
                continue
            if dry_run:
                note(table, created=True)
                continue
            obj = model.objects.create(
                company=target_company, name=row["name"],
                is_active=row.get("is_active", True), **extra(row),
            )
            known[_key(row["name"])] = obj.id
            mapping[row["id"]] = obj.id
            note(table, created=True)

    known_warehouses = existing_by_name(Warehouse)
    for w in master.get("warehouses", []):
        if _key(w.get("name")) in known_warehouses:
            note("warehouses", created=False)
            continue
        if not dry_run:
            obj = Warehouse.objects.create(
                company=target_company, name=w["name"], code=w.get("code", ""),
                is_active=w.get("is_active", True),
            )
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
    for p in master.get("products", []):
        sku, barcode = _key(p.get("sku")), _key(p.get("barcode"))
        if (sku and sku in existing_skus) or (barcode and barcode in existing_barcodes):
            note("products", created=False)
            continue
        if not dry_run:
            Product.objects.create(
                company=target_company, sku=p["sku"], name=p["name"],
                category_id=cat_map.get(p.get("category")),
                brand_id=brand_map.get(p.get("brand")),
                unit_id=unit_map.get(p.get("unit")),
                barcode=p.get("barcode", ""), qr_code=p.get("qr_code", ""),
                cost_price=p.get("cost_price", 0), sale_price=p.get("sale_price", 0),
                reorder_level=p.get("reorder_level", 0),
                track_batches=p.get("track_batches", False),
                is_active=p.get("is_active", True),
            )
        if sku:
            existing_skus.add(sku)
        if barcode:
            existing_barcodes.add(barcode)
        note("products", created=True)

    for table, model in (("customers", Customer), ("suppliers", Supplier)):
        known = existing_by_name(model)
        for row in master.get(table, []):
            if _key(row.get("name")) in known:
                note(table, created=False)
                continue
            if not dry_run:
                obj = model.objects.create(
                    company=target_company, name=row["name"], phone=row.get("phone", ""),
                    email=row.get("email", ""), address=row.get("address", ""),
                    is_active=row.get("is_active", True),
                )
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
