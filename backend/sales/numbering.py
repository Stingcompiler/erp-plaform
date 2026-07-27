from sales.models import InvoiceSequence


def allocate_invoice_number(company_id):
    """
    Return the next sequential invoice number for a company, gaplessly.

    MUST be called inside a transaction (the caller's `@transaction.atomic`).
    The sequence row is locked with select_for_update so concurrent checkouts
    serialize on it, and because the increment commits/rolls back together with
    the invoice insert, a failed sale never burns a number — no gaps.

    On PostgreSQL (prod) this takes a real row lock; on SQLite (dev/tests)
    select_for_update is a no-op but writes are already serialized, so the
    behavior is equivalent there.
    """
    seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(
        company_id=company_id
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return seq.last_number
