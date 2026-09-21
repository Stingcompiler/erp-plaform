from decimal import Decimal
from io import StringIO
import json

from django.core.management import CommandError, call_command
from django.test import TestCase

from inventory.models import Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice


class RecoveryFingerprintTests(TestCase):
    def setUp(self):
        self.alpha = Company.objects.create(name="Alpha")
        self.beta = Company.objects.create(name="Beta")
        branch = Branch.objects.create(company=self.alpha, name="Main")
        wh = Warehouse.objects.create(company=self.alpha, branch=branch, name="W")
        customer = Customer.objects.create(company=self.alpha, name="C")
        for number, total in enumerate(("100.00", "250.50"), start=1):
            Invoice.objects.create(
                company=self.alpha, customer=customer, warehouse=wh, number=number,
                subtotal=Decimal(total), total=Decimal(total),
            )

    def _run(self, *args):
        out = StringIO()
        call_command("recovery_fingerprint", *args, "--json", stdout=out)
        return {r["entity"]: r for r in json.loads(out.getvalue())}

    def test_lists_all_ten_entities_with_counts_and_sums(self):
        rows = self._run()
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows["invoices"], {"entity": "invoices", "count": 2, "sum": "350.500"})
        self.assertEqual(rows["payments"]["count"], 0)
        self.assertEqual(rows["payments"]["sum"], "0.000")

    def test_company_scope_by_name_or_id_and_unknown_is_an_error(self):
        self.assertEqual(self._run("--company", "Beta")["invoices"]["count"], 0)
        self.assertEqual(self._run("--company", str(self.alpha.pk))["invoices"]["count"], 2)
        with self.assertRaises(CommandError):
            call_command("recovery_fingerprint", "--company", "Nope", stdout=StringIO())
