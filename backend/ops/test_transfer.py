import io
import json
import tempfile
import zipfile
from pathlib import Path

from django.core.management import call_command
from django.core.serializers.json import DjangoJSONEncoder
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

    def test_import_command_puts_the_archive_media_back(self):
        from django.core.files.base import ContentFile
        from django.test import override_settings

        from inventory.models import Product

        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            product = Product.objects.create(company=self.company, sku="P1", name="Tea")
            product.image.save("tea.png", ContentFile(b"png-bytes"), save=True)
            name = product.image.name
            archive_path = Path(media) / "company.zip"
            write_export(self.company, archive_path, include_media=True)
            Product.objects.filter(pk=product.pk).delete()
            self.company.delete()
            (Path(media) / name).unlink()

            call_command("import_company", archive=str(archive_path), stdout=io.StringIO())

            self.assertEqual((Path(media) / name).read_bytes(), b"png-bytes")
            self.assertEqual(
                Product.objects.get(company__slug="transfer-source").image.name, name
            )

    def test_the_owner_download_is_an_import_source(self):
        payload, _ = export_company(self.company, include_media=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vezano-company.json"
            path.write_text(json.dumps(payload, cls=DjangoJSONEncoder), encoding="utf-8")
            read, archive = read_export(path)
            self.assertIsNone(archive)
            self.assertEqual(read["counts"], json.loads(json.dumps(payload["counts"])))
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(TransferError):
                read_export(path)

    def test_import_keeps_server_timestamps_and_drops_outside_links(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.models import ActivityLog

        platform = Role.objects.create(name="Platform staff", scope_level=Role.SCOPE_PLATFORM)
        staff = User.objects.create_user(email="staff@vezano.test", role=platform)
        ActivityLog.objects.create(company=self.company, user=staff, action="update",
                                   entity_type="Company", entity_id=str(self.company.pk))
        long_ago = timezone.now() - timedelta(days=400)
        Branch.objects.filter(company=self.company).update(created_at=long_ago)
        payload, _ = export_company(self.company, include_media=False)
        payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
        self.company.delete()
        target = Company.objects.create(name="Imported", slug="imported")

        report = import_company(payload, target)

        branch = Branch.objects.get(company=target)
        self.assertLess(abs((branch.created_at - long_ago).total_seconds()), 0.01)
        log = ActivityLog.objects.get(company=target)
        self.assertIsNone(log.user)
        self.assertEqual(log.entity_id, str(target.pk))
        self.assertTrue(any("outside the company" in w for w in report.warnings))

    def test_import_refuses_a_company_that_is_already_here(self):
        payload, _ = export_company(self.company, include_media=False)
        target = Company.objects.create(name="Copy", slug="copy")
        with self.assertRaisesMessage(TransferError, "already on this installation"):
            import_company(payload, target)

    def test_import_command_can_start_a_trial_on_the_hosted_platform(self):
        from django.utils import timezone

        from subscriptions.models import Plan, PlanVersion, Subscription

        version = PlanVersion.objects.create(
            plan=Plan.objects.create(code="restore", name="Restore"), version=1,
            published_at=timezone.now(),
        )
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "company.zip"
            write_export(self.company, archive_path, include_media=False)
            self.company.delete()
            call_command(
                "import_company", archive=str(archive_path), no_media=True,
                trial_plan_version=version.pk, stdout=io.StringIO(),
            )
        subscription = Subscription.objects.get(company__slug="transfer-source")
        self.assertEqual(subscription.status, Subscription.TRIALING)
        self.assertEqual(subscription.plan_version, version)

    def test_import_command_refuses_an_existing_slug(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "company.zip"
            write_export(self.company, archive_path, include_media=False)
            with self.assertRaises(CommandError):
                call_command("import_company", archive=str(archive_path), no_media=True)
