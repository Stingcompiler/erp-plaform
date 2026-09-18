"""Spreadsheet import of customers and suppliers: preview, upsert, balances."""

import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from purchasing.models import Supplier
from sales.models import Customer


def xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("parties.xlsx", buf.getvalue())


class PartyImportTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=self.company, name="Main")
        Warehouse.objects.create(company=self.company, branch=branch, name="W")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company, role=owner,
            branch=branch,
        )
        Customer.objects.create(company=self.company, name="Old Name", phone="0911111111")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _post(self, upload, dry_run):
        return self.client.post(
            "/api/customers/import/", {"file": upload, "dry_run": "1" if dry_run else "0"},
            format="multipart",
        )

    def test_dry_run_previews_without_writing(self):
        upload = xlsx([
            ["الاسم", "الهاتف", "الرصيد الافتتاحي", "مهلة السداد"],
            ["New Buyer", "0922222222", "1500", "30"],
            ["Renamed", "0911111111", "", ""],
            ["", "0933333333", "", ""],
            ["New Buyer", "0922222222", "", ""],
        ])
        response = self._post(upload, dry_run=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["dry_run"])
        statuses = [r["status"] for r in response.data["rows"]]
        self.assertEqual(statuses, ["created", "updated", "error", "skipped"])
        self.assertEqual(response.data["summary"]["balances"], 1)
        # Nothing persisted.
        self.assertEqual(Customer.objects.filter(company=self.company).count(), 1)
        self.assertEqual(Customer.objects.get(phone="0911111111").name, "Old Name")

    def test_real_run_upserts_and_records_balances(self):
        upload = xlsx([
            ["name", "phone", "opening balance", "payment terms"],
            ["New Buyer", "0922222222", "1,500", "30"],
            ["Renamed", "0911111111", "", ""],
        ])
        response = self._post(upload, dry_run=False)
        self.assertEqual(response.status_code, 200, response.data)
        buyer = Customer.objects.get(company=self.company, phone="0922222222")
        self.assertEqual(buyer.payment_terms_days, 30)
        self.assertEqual(buyer.ar_balance(), Decimal("1500.00"))
        self.assertEqual(Customer.objects.get(phone="0911111111").name, "Renamed")
        # Importing the same sheet again neither duplicates nor doubles the balance.
        again = self._post(xlsx([
            ["name", "phone", "opening balance"],
            ["New Buyer", "0922222222", "1500"],
        ]), dry_run=False)
        self.assertEqual(again.data["rows"][0]["status"], "updated")
        self.assertTrue(again.data["rows"][0]["message"])  # "kept: already has one"
        self.assertNotIn("balance", again.data["rows"][0])
        self.assertEqual(Customer.objects.filter(company=self.company).count(), 2)
        self.assertEqual(buyer.ar_balance(), Decimal("1500.00"))

    def test_csv_suppliers_and_missing_name_column(self):
        csv_upload = SimpleUploadedFile(
            "s.csv", "المورد;الهاتف;الرصيد\nAcme;0100;250\n".encode("utf-8"),
        )
        response = self.client.post(
            "/api/suppliers/import/", {"file": csv_upload, "dry_run": "0"}, format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        acme = Supplier.objects.get(company=self.company, name="Acme")
        self.assertEqual(acme.ap_balance(), Decimal("250.00"))
        bad = self.client.post(
            "/api/suppliers/import/",
            {"file": SimpleUploadedFile("s.csv", b"phone\n0100\n"), "dry_run": "1"},
            format="multipart",
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("file", bad.data)
