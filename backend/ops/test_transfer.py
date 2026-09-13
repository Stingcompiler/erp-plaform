import json
import tempfile
import zipfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import Role, User
from ops.transfer import (
    ARCHIVE_NAME,
    ImportReport,
    TransferError,
    export_company,
    import_company,
    read_export,
    validate_payload,
    verify_transfer,
    write_export,
)
from org.models import Branch, Company, Department


class CompanyTransferTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.company = Company.objects.create(
            name="Transfer Source",
            slug="transfer-source",
            currency="SAR",
            legal_name="Transfer Source LLC",
            tax_number="VAT-100",
        )
        self.other = Company.objects.create(name="Do Not Export", slug="other-company")
        self.branch = Branch.objects.create(company=self.company, name="Riyadh")
        Department.objects.create(
            company=self.company, branch=self.branch, name="Sales"
        )
        User.objects.create_user(
            email="owner@transfer.test",
            password="SourcePassword!1",
            company=self.company,
            branch=self.branch,
            role=self.role,
        )
        Branch.objects.create(company=self.other, name="Secret branch")

    def test_export_is_tenant_scoped_and_preserves_company_fields(self):
        payload, _ = export_company(self.company, include_media=False)
        self.assertEqual(
            payload["source"]["fields"]["legal_name"], "Transfer Source LLC"
        )
        self.assertEqual(payload["counts"]["org.Branch"], 1)
        branch_names = {row["name"] for row in payload["objects"]["org.Branch"]}
        self.assertEqual(branch_names, {"Riyadh"})
        self.assertEqual(validate_payload(payload), [])

    def test_archive_round_trip_remaps_foreign_keys_and_disables_passwords(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "company.vezano.zip"
            write_export(self.company, archive_path, include_media=False)
            payload, archive = read_export(archive_path)
            self.company.delete()
            target = Company.objects.create(name="Imported", slug="imported")
            try:
                report = import_company(payload, target, archive=archive)
            finally:
                archive.close()

        self.assertGreater(report.total_created, 0)
        self.assertEqual(verify_transfer(payload, target), [])
        branch = Branch.objects.get(company=target)
        department = Department.objects.get(company=target)
        moved_user = User.objects.get(company=target)
        self.assertEqual(department.branch, branch)
        self.assertEqual(moved_user.branch, branch)
        self.assertEqual(moved_user.role, self.role)
        self.assertFalse(moved_user.has_usable_password())
        self.assertFalse(moved_user.is_staff)
        self.assertFalse(moved_user.is_superuser)

    def test_tampered_counts_are_rejected(self):
        payload, _ = export_company(self.company, include_media=False)
        payload["counts"]["org.Branch"] = 99
        with self.assertRaises(TransferError):
            import_company(payload, self.other, report=ImportReport())

    def test_archive_rejects_non_transferable_models(self):
        payload, _ = export_company(self.company, include_media=False)
        payload["objects"]["subscriptions.Plan"] = []
        payload["counts"]["subscriptions.Plan"] = 0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(ARCHIVE_NAME, json.dumps(payload, default=str))
            with self.assertRaises(TransferError):
                read_export(path)

    def test_import_command_refuses_an_existing_slug(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "company.zip"
            write_export(self.company, archive_path, include_media=False)
            with self.assertRaises(CommandError):
                call_command("import_company", archive=str(archive_path), no_media=True)
