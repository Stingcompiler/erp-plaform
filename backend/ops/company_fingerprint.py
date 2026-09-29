"""What a restored company must match: one company's data, id-free.

A restore drill takes this fingerprint of the company before the export and
of the company the archive was imported into, and the two must be equal.
Nothing in it is a database id — the import gives every row a new one — so
rows are keyed by what a person reads (SKU, warehouse name, lot number,
customer name, document number):

* ``counts`` — rows per transferable model, read through the base manager so
  a default manager that hides rows cannot hide them from the check;
* ``sums`` — the total of every decimal column of every transferable model
  (invoice totals, payments, refunds, credit notes, bills, supplier payments,
  expenses, payroll, advances, drawer movements ...);
* ``stock`` — quantity on hand per product / warehouse / lot;
* ``balances`` — every customer's receivable, supplier's payable and bank
  account's balance, as the app computes them;
* ``reports`` — the report endpoints' JSON for one period, ids removed.

``diff`` compares two fingerprints and lists every difference beyond 0.01.
"""

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import models
from django.db.models import Sum

TOLERANCE = Decimal("0.01")
_WHOLE_SECOND = re.compile(r"(?<=T\d\d:\d\d:\d\d)\.000(?=Z$|[+-]\d\d:\d\d$)")

# Report endpoints (path, extra query) run for the period. Each is what an
# owner opens on the reports page; together they read every money table.
REPORTS = [
    ("/api/reports/income-statement/", {}),
    ("/api/reports/profit-summary/", {}),
    ("/api/reports/cash-flow/", {}),
    ("/api/reports/ar-aging/", {}),
    ("/api/reports/ap-aging/", {}),
    ("/api/reports/inventory-valuation/", {}),
    ("/api/reports/inventory-valuation/", {"method": "fifo"}),
    ("/api/reports/sales-summary/", {}),
    ("/api/reports/sales-by-product/", {}),
    ("/api/reports/purchases-summary/", {}),
    ("/api/reports/sales-returns/", {}),
    ("/api/reports/purchase-returns/", {}),
    ("/api/reports/payment-reconciliation/", {}),
    ("/api/reports/receivables-due/", {}),
    ("/api/reports/payables-due/", {}),
    ("/api/reports/payroll/", {}),
    ("/api/reports/hr-summary/", {}),
    ("/api/reports/zakat/", {}),
    ("/api/reports/cfo-kpis/", {}),
    ("/api/reports/crm/", {}),
    ("/api/debts/summary/", {}),
]

# Keys whose values are database ids or the moment the report ran.
_VOLATILE_KEYS = {"id", "pk", "generated_at", "url", "href"}


# Report keys that carry a row's id when their value is a number (the name
# of the row sits beside it: "customer": 7, "name": "...").
_ID_KEYS = {
    "account", "batch", "bill", "branch", "customer", "employee", "invoice", "lead",
    "order", "payment", "product", "supplier", "user", "warehouse",
}


def _is_volatile(key, value=None):
    key = str(key)
    if key in _ID_KEYS and isinstance(value, int) and not isinstance(value, bool):
        return True
    return key in _VOLATILE_KEYS or key.endswith("_id") or key.endswith("_ids")


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError):
        return value


def normalise(value):
    """JSON with ids dropped and numbers as Decimals, lists in a stable
    order (two lists with the same rows in another order are equal)."""
    if isinstance(value, dict):
        return {
            str(key): normalise(item)
            for key, item in value.items()
            if not _is_volatile(key, item)
        }
    if isinstance(value, (list, tuple)):
        items = [normalise(item) for item in value]
        return sorted(items, key=repr)
    if isinstance(value, float):
        return _money(value)
    if isinstance(value, Decimal):
        return _money(value)
    return value


def _decimal_fields(model):
    return [
        field.name for field in model._meta.fields
        if isinstance(field, models.DecimalField)
    ]


def _rows(model, company):
    from ops.transfer import _company_filter_path

    path = _company_filter_path(model)
    if path is None:
        return model._base_manager.none()
    return model._base_manager.filter(**{path: company})


def counts_and_sums(company):
    from ops.transfer import label_for, transferable_models

    counts, sums = {}, {}
    for model in transferable_models():
        label = label_for(model)
        queryset = _rows(model, company)
        counts[label] = queryset.count()
        fields = _decimal_fields(model)
        if fields:
            totals = queryset.aggregate(**{name: Sum(name) for name in fields})
            for name in fields:
                sums[f"{label}.{name}"] = _money(totals[name])
    return counts, sums


def stock_on_hand(company):
    from inventory.models import StockMovement

    rows = (
        StockMovement.objects.filter(company=company)
        .values("product__sku", "warehouse__name", "batch__lot_number")
        .annotate(quantity=Sum("quantity"))
    )
    return {
        f"{row['product__sku']} | {row['warehouse__name']} | {row['batch__lot_number'] or '-'}":
            _money(row["quantity"])
        for row in rows
    }


def balances(company):
    from purchasing.models import Supplier
    from sales.models import CompanyBankAccount, Customer

    result = defaultdict(dict)
    for customer in Customer.objects.filter(company=company):
        key = f"{customer.name} | {customer.phone}"
        result["customers"][key] = _money(customer.ar_balance())
    for supplier in Supplier.objects.filter(company=company):
        key = f"{supplier.name} | {supplier.phone}"
        result["suppliers"][key] = _money(supplier.ap_balance())
    for account in CompanyBankAccount.objects.filter(company=company):
        key = f"{account.bank_name} | {account.account_number}"
        result["bank_accounts"][key] = _money(account.balance())
    return dict(result)


def _owner(company):
    from accounts.models import User

    return (
        User.objects.filter(company=company, role__name="Business Owner")
        .order_by("pk").first()
    )


def report_outputs(company, start, end):
    """Each report as the owner sees it, for [start, end]."""
    import json

    from django.urls import resolve
    from rest_framework.test import APIRequestFactory, force_authenticate

    owner = _owner(company)
    if owner is None:
        return {"_error": "the company has no Business Owner"}
    factory = APIRequestFactory()
    outputs = {}
    for path, extra in REPORTS:
        query = {"start": start.isoformat(), "end": end.isoformat(), **extra}
        request = factory.get(path, query)
        force_authenticate(request, user=owner)
        match = resolve(path)
        response = match.func(request, *match.args, **match.kwargs)
        key = path + ("?" + "&".join(f"{k}={v}" for k, v in extra.items()) if extra else "")
        if response.status_code != 200:
            outputs[key] = {"_status": response.status_code}
            continue
        response.render()
        outputs[key] = normalise(json.loads(response.content))
    return outputs


def fingerprint(company, start, end, reports=True):
    counts, sums = counts_and_sums(company)
    data = {
        "counts": counts,
        "sums": sums,
        "stock": stock_on_hand(company),
        "balances": balances(company),
    }
    if reports:
        data["reports"] = report_outputs(company, start, end)
    return data


def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (Decimal, int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _close(left, right):
    if left == right:
        return True
    a, b = _as_number(left), _as_number(right)
    if a is not None and b is not None and a.is_finite() and b.is_finite():
        return abs(a - b) <= TOLERANCE
    return False


def diff(left, right, path="", ignore=()):
    """Every difference between two fingerprints (or parts of them)."""
    if any(path == item or path.startswith(item + ".") for item in ignore):
        return []
    if isinstance(left, dict) and isinstance(right, dict):
        problems = []
        for key in sorted(set(left) | set(right), key=str):
            sub = f"{path}.{key}" if path else str(key)
            if key not in left:
                problems.append(f"{sub}: missing before, {right[key]!r} after")
            elif key not in right:
                problems.append(f"{sub}: {left[key]!r} before, missing after")
            else:
                problems.extend(diff(left[key], right[key], sub, ignore))
        return problems
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [f"{path}: {len(left)} item(s) before, {len(right)} after"]
        problems = []
        for index, (a, b) in enumerate(zip(left, right)):
            problems.extend(diff(a, b, f"{path}[{index}]", ignore))
        return problems
    return [] if _close(left, right) else [f"{path}: {left!r} before, {right!r} after"]


# ---------------------------------------------------------------- row level

def _position_maps(payload):
    """Archive id → position within its model's rows, per model."""
    return {
        label: {row["__pk__"]: index for index, row in enumerate(rows)}
        for label, rows in (payload.get("objects") or {}).items()
    }


def comparable_rows(payload):
    """The archive's rows with every id replaced by the row's position, so
    two archives of the same company from different installations compare
    field by field."""
    from ops.transfer import (
        SOFT_REFERENCES,
        _model_for_label,
        _soft_reference_targets,
        label_for,
    )

    positions = _position_maps(payload)
    by_class = _soft_reference_targets(positions.keys())
    source_company = str((payload.get("source") or {}).get("company_id"))

    def soft(label, row):
        """The text id of a SOFT_REFERENCES column, as a position too."""
        type_field, id_field, targets = SOFT_REFERENCES[label]
        kind, raw = row.get(type_field) or "", row.get(id_field) or ""
        if label == "core.ActivityLog" and kind == "Company":
            return "Company#self" if raw == source_company else raw
        target = (targets or by_class).get(kind)
        try:
            position = positions.get(target, {}).get(int(raw))
        except (TypeError, ValueError):
            position = None
        return raw if position is None else f"{target}#{position}"

    result = {}
    for label, rows in (payload.get("objects") or {}).items():
        model = _model_for_label(label)
        fks = {
            field.name: label_for(field.related_model)
            for field in model._meta.fields
            if isinstance(field, (models.ForeignKey, models.OneToOneField))
        }
        converted = []
        for row in rows:
            item = {}
            for key, value in row.items():
                if key == "__pk__" or key == "company":
                    continue
                target = fks.get(key)
                if target is not None and value is not None:
                    position = positions.get(target, {}).get(value)
                    # A link to a row outside the company (the platform
                    # operator behind an audit entry, the vendor's plan)
                    # cannot travel; the import leaves it empty by design.
                    value = None if position is None else f"{target}#{position}"
                elif isinstance(value, datetime):
                    # The archive keeps milliseconds (Django's JSON encoder).
                    value = value.replace(microsecond=value.microsecond // 1000 * 1000)
                elif isinstance(value, str):
                    # ...and a moment with none prints without them.
                    value = _WHOLE_SECOND.sub("", value)
                item[key] = value
            if label in SOFT_REFERENCES:
                item[SOFT_REFERENCES[label][1]] = soft(label, row)
            converted.append(item)
        result[label] = converted
    return result
