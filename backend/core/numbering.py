from django.db import transaction

from core.models import DocumentSequence


def allocate_document_number(company_id, doc_type):
    """Next gapless number for (company, doc_type). Row-locked; safe to call
    with or without an enclosing transaction — a nested atomic() joins the
    outer one so the number commits or rolls back with the document."""
    with transaction.atomic():
        seq, _ = DocumentSequence.objects.select_for_update().get_or_create(
            company_id=company_id, doc_type=doc_type
        )
        seq.last_number += 1
        seq.save(update_fields=["last_number"])
        return seq.last_number
