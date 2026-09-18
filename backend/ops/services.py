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


def restore_master(target_company, dump, user=None):
    """
    Re-create master data into an empty company. Refuses to run if the target
    already has products (so a restore can never clobber live data).
    """
    from inventory.models import Brand, Category, Product, Unit, Warehouse
    from purchasing.models import Supplier
    from sales.models import Customer

    if Product.objects.filter(company=target_company).exists():
        raise ValidationError(
            _("Target company already has products; restore only into an empty company.")
        )

    master = dump.get("master", {})
    cat_map, brand_map, unit_map = {}, {}, {}

    for c in master.get("categories", []):
        # Parent hierarchy is not restored (parents flattened to null).
        obj = Category.objects.create(
            company=target_company, name=c["name"], is_active=c.get("is_active", True),
        )
        cat_map[c["id"]] = obj.id
    for b in master.get("brands", []):
        obj = Brand.objects.create(
            company=target_company, name=b["name"], is_active=b.get("is_active", True),
        )
        brand_map[b["id"]] = obj.id
    for u in master.get("units", []):
        obj = Unit.objects.create(
            company=target_company, name=u["name"], symbol=u.get("symbol", ""),
            is_active=u.get("is_active", True),
        )
        unit_map[u["id"]] = obj.id

    for w in master.get("warehouses", []):
        Warehouse.objects.create(
            company=target_company, name=w["name"], code=w.get("code", ""),
            is_active=w.get("is_active", True),
        )

    restored = 0
    for p in master.get("products", []):
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
        restored += 1

    for c in master.get("customers", []):
        Customer.objects.create(
            company=target_company, name=c["name"], phone=c.get("phone", ""),
            email=c.get("email", ""), address=c.get("address", ""),
            is_active=c.get("is_active", True),
        )
        restored += 1
    for s in master.get("suppliers", []):
        Supplier.objects.create(
            company=target_company, name=s["name"], phone=s.get("phone", ""),
            email=s.get("email", ""), address=s.get("address", ""),
            is_active=s.get("is_active", True),
        )
        restored += 1

    return restored
