from decimal import Decimal

from django.test import TestCase

from accounts.models import Role, User
from core.models import DocumentSequence
from org.models import Company
from purchasing.models import Supplier
from returns.models import CreditNote, DebitNote


class NoteNumberingTests(TestCase):
    """Rule #6: credit and debit notes are formal, sequentially numbered
    documents — per company, per type, gapless, and never the database id."""

    def setUp(self):
        self.a = Company.objects.create(name="A")
        self.b = Company.objects.create(name="B")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user("a@a.test", "passw0rd123", company=self.a, role=role)

    def test_numbers_are_per_company_and_per_type(self):
        c1 = CreditNote.objects.create(company=self.a, amount=Decimal("10"))
        c2 = CreditNote.objects.create(company=self.a, amount=Decimal("20"))
        other = CreditNote.objects.create(company=self.b, amount=Decimal("5"))
        supplier = Supplier.objects.create(company=self.a, name="S")
        d1 = DebitNote.objects.create(company=self.a, supplier=supplier, amount=Decimal("7"))
        self.assertEqual((c1.number, c2.number), (1, 2))
        self.assertEqual(other.number, 1)          # B has its own run
        self.assertEqual(d1.number, 1)             # debit notes count separately
        self.assertEqual(c2.number_display, "CN-000002")
        self.assertEqual(d1.number_display, "DN-000001")

    def test_sequence_row_tracks_last_number(self):
        CreditNote.objects.create(company=self.a, amount=Decimal("1"))
        CreditNote.objects.create(company=self.a, amount=Decimal("1"))
        seq = DocumentSequence.objects.get(company=self.a, doc_type="credit_note")
        self.assertEqual(seq.last_number, 2)

    def test_rolled_back_note_does_not_burn_a_number(self):
        from django.db import transaction

        CreditNote.objects.create(company=self.a, amount=Decimal("1"))
        try:
            with transaction.atomic():
                CreditNote.objects.create(company=self.a, amount=Decimal("1"))
                raise RuntimeError("abort")
        except RuntimeError:
            pass
        note = CreditNote.objects.create(company=self.a, amount=Decimal("1"))
        self.assertEqual(note.number, 2)

    def test_document_uses_the_formal_number(self):
        from core.documents import credit_note_document

        note = CreditNote.objects.create(company=self.a, amount=Decimal("3"))
        self.assertEqual(credit_note_document(note)["number"], "CN-000001")
