"""
Internal barcode generation for products that carry no manufacturer barcode.

Codes are valid **EAN-13**, so any off-the-shelf scanner and label printer reads
them. They start with prefix "2", which GS1 reserves for in-store/internal use —
that guarantees a generated code can never collide with a real manufacturer's
barcode. Layout (12 digits + check digit):

    2 | CC | SSSSSSSSS | K
    ^   ^    ^           ^-- EAN-13 check digit
    |   |    +-------------- 9-digit per-company sequence
    |   +------------------- company id (2 digits, wraps at 100)
    +----------------------- internal-use prefix
"""
from django.db import transaction

INTERNAL_PREFIX = "2"


def ean13_check_digit(twelve_digits):
    """Standard EAN-13 checksum: odd positions x1, even positions x3."""
    if len(twelve_digits) != 12 or not twelve_digits.isdigit():
        raise ValueError("EAN-13 body must be exactly 12 digits.")
    total = sum(
        int(d) * (3 if i % 2 else 1) for i, d in enumerate(twelve_digits)
    )
    return str((10 - (total % 10)) % 10)


def build_ean13(company_id, sequence):
    body = (
        INTERNAL_PREFIX
        + str(company_id % 100).zfill(2)
        + str(sequence).zfill(9)
    )
    return body + ean13_check_digit(body)


def is_valid_ean13(code):
    code = str(code or "").strip()
    if len(code) != 13 or not code.isdigit():
        return False
    return ean13_check_digit(code[:12]) == code[12]


@transaction.atomic
def next_internal_sku(company_id):
    """
    Allocate a house SKU for a product created without one.

    A shopkeeper thinks in barcodes, not stock-keeping units, and forcing them
    to invent a unique code before they can save their first product is pure
    friction. Uses the same row-locked per-company counter as the barcode
    allocator, and skips values already taken by hand-typed SKUs so the
    unique(company, sku) constraint can never be violated.
    """
    from inventory.models import BarcodeSequence, Product

    seq, _ = BarcodeSequence.objects.select_for_update().get_or_create(
        company_id=company_id
    )
    while True:
        seq.last_number += 1
        sku = f"P{seq.last_number:06d}"
        if not Product.objects.filter(company_id=company_id, sku=sku).exists():
            break
    seq.save(update_fields=["last_number"])
    return sku


@transaction.atomic
def next_internal_barcode(company_id):
    """Allocate and return the next unused internal EAN-13 for a company."""
    from inventory.models import BarcodeSequence, Product

    seq, _ = BarcodeSequence.objects.select_for_update().get_or_create(
        company_id=company_id
    )
    # Skip any value already taken (e.g. a code typed in by hand) so the
    # unique constraint can never be violated.
    while True:
        seq.last_number += 1
        code = build_ean13(company_id, seq.last_number)
        if not Product.objects.filter(company_id=company_id, barcode=code).exists():
            break
    seq.save(update_fields=["last_number"])
    return code
