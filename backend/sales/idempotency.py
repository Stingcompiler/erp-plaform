"""What a checkout's idempotency key promised to record.

A till names each sale with a `client_uuid` so a retry after a lost
response returns the invoice already made instead of ringing the sale up
twice. Two till tabs restored the same autosaved draft, though, and so the
same key: the second tab's *different* sale was answered with the first
tab's invoice and never recorded.

The invoice keeps a fingerprint of the body that created it. A replay with
the same key and the same fingerprint is the retry the key exists for; the
same key with a materially different body (other lines, quantities,
prices, discounts, customer or payments) is a conflict the till must hear
about. Times (`occurred_at`, `sent_at`) and the printed reference are not
part of it: a queued sale replays with the time it was taken, and the
device corrects its clock between attempts.
"""

import hashlib
import json
from decimal import Decimal, InvalidOperation

CLIENT_UUID_CONFLICT = "client_uuid_conflict"


def _num(value):
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if not number.is_finite():
        return str(value)
    # 3, "3.0" and "3.00" are the same quantity.
    number = number.normalize()
    return format(number, "f")


def _ref(value):
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        value = value.get("id", "")
    return str(value)


def _payment(row):
    if not isinstance(row, dict):
        return None
    amount = _num(row.get("amount"))
    if amount in ("", "0"):
        return None
    return [str(row.get("method") or ""), amount, _ref(row.get("bank_account"))]


def checkout_fingerprint(data):
    """A stable hash of the parts of a POS checkout body that make it the
    sale it is. Accepts the raw request/queued payload (strings or numbers)."""
    if not isinstance(data, dict):
        return ""
    lines = []
    for line in data.get("lines") or []:
        if not isinstance(line, dict):
            continue
        lines.append([
            _ref(line.get("product")),
            _ref(line.get("pack")),
            _num(line.get("quantity")),
            _num(line.get("unit_price")),
            _num(line.get("discount_percent")),
        ])
    payments = data.get("payments")
    if not isinstance(payments, list):
        single = data.get("payment")
        payments = [single] if single else []
    paid = [p for p in (_payment(row) for row in payments) if p]
    credit = data.get("apply_credit") if isinstance(data.get("apply_credit"), dict) else {}
    body = {
        "warehouse": _ref(data.get("warehouse")),
        "customer": _ref(data.get("customer")),
        "source_order": _ref(data.get("source_order")),
        "lines": sorted(lines),
        "discount_amount": _num(data.get("discount_amount")),
        "payments": sorted(paid),
        "credit": [_ref(credit.get("credit_note")), _num(credit.get("amount"))] if credit else [],
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def conflicts(invoice, data):
    """True when `data` re-uses `invoice`'s key for a different sale.
    Invoices recorded before the fingerprint existed never conflict."""
    stored = getattr(invoice, "client_body_hash", "") or ""
    return bool(stored) and stored != checkout_fingerprint(data)
