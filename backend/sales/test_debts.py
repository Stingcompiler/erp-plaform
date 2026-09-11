"""Customer debt ledger: derived receivables, scoped to the active company."""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from returns.models import CreditNote
from sales.models import Customer, Invoice, Payment


class DebtLedgerTestCase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="North shop")
        self.warehouse = Warehouse.objects.create(company=self.company, name="Store")
        self.role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="sales@north.test", password="passw0rd12345", company=self.company,
            role=self.role,
        )
        self.client.force_authenticate(self.user)
        self.customer = Customer.objects.create(
            company=self.company, name="Amina", phone="0912345678"
        )

    def secure_get(self, url, data=None):
        return self.client.get(url, data, secure=True)

    def invoice(self, total, *, issued_at=None, due_date=None, number=1):
        invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.warehouse,
            number=number, subtotal=Decimal(total), total=Decimal(total),
        )
        if issued_at or due_date:
            Invoice.objects.filter(pk=invoice.pk).update(
                issued_at=issued_at or invoice.issued_at,
                due_date=due_date or invoice.due_date,
            )
            invoice.refresh_from_db()
        return invoice

    def test_list_and_summary_use_invoices_payments_and_credit_notes(self):
        invoice = self.invoice("100", due_date=timezone.localdate() - timedelta(days=1))
        Payment.objects.create(
            company=self.company, invoice=invoice, method=Payment.CASH,
            amount=Decimal("40"), recorded_by=self.user,
        )
        CreditNote.objects.create(
            company=self.company, customer=self.customer, amount=Decimal("15"),
            created_by=self.user, reason="Returned item",
        )

        listed = self.secure_get(reverse("debt-customer-list"))
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["count"], 1)
        row = listed.data["results"][0]
        self.assertEqual(row["outstanding"], "60.00")
        self.assertEqual(row["overdue"], "60.00")
        self.assertEqual(row["credit_balance"], "15.00")
        self.assertEqual(row["status"], "overdue")

        summary = self.secure_get(reverse("debt-summary"))
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data, {
            "outstanding": "60.00", "overdue": "60.00",
            "credit_balance": "15.00", "debtor_count": 1,
        })

    def test_statement_has_opening_balance_and_running_balance(self):
        now = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        invoice = self.invoice(
            "100", issued_at=now - timedelta(days=4),
            due_date=(now - timedelta(days=3)).date(), number=2,
        )
        payment = Payment.objects.create(
            company=self.company, invoice=invoice, method=Payment.CASH,
            amount=Decimal("25"), recorded_by=self.user,
        )
        credit = CreditNote.objects.create(
            company=self.company, customer=self.customer, invoice=invoice,
            amount=Decimal("10"), created_by=self.user,
        )
        Payment.objects.filter(pk=payment.pk).update(recorded_at=now - timedelta(days=2))
        CreditNote.objects.filter(pk=credit.pk).update(created_at=now - timedelta(days=1))

        response = self.secure_get(
            reverse("customer-debt-statement", args=[self.customer.id]),
            {
                "start": (now - timedelta(days=2)).date().isoformat(),
                "end": now.date().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["opening_balance"], "100.00")
        self.assertEqual(response.data["closing_balance"], "65.00")
        self.assertEqual(
            [event["type"] for event in response.data["events"]],
            ["payment", "credit_note"],
        )
        self.assertEqual(response.data["events"][-1]["balance"], "65.00")

    def test_statement_rejects_invalid_date_and_hides_other_company(self):
        response = self.secure_get(
            reverse("customer-debt-statement", args=[self.customer.id]), {"start": "not-a-date"}
        )
        self.assertEqual(response.status_code, 400)

        other_company = Company.objects.create(name="South shop")
        other_customer = Customer.objects.create(company=other_company, name="Other")
        response = self.secure_get(reverse("customer-debt-statement", args=[other_customer.id]))
        self.assertEqual(response.status_code, 404)

    def test_status_and_pagination_validation(self):
        self.invoice("20")
        response = self.secure_get(reverse("debt-customer-list"), {"status": "owing"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            self.secure_get(reverse("debt-customer-list"), {"page_size": "oops"}).status_code,
            400,
        )

    def test_branch_user_sees_only_own_branch_invoices(self):
        own_branch = Branch.objects.create(company=self.company, name="North")
        other_branch = Branch.objects.create(company=self.company, name="South")
        branch_role = Role.objects.create(
            name="Branch Manager", scope_level=Role.SCOPE_BRANCH
        )
        branch_user = User.objects.create_user(
            email="manager@north.test", password="passw0rd12345", company=self.company,
            role=branch_role, branch=own_branch,
        )
        other_customer = Customer.objects.create(company=self.company, name="Other branch")
        own_invoice = self.invoice("30", number=3)
        other_invoice = Invoice.objects.create(
            company=self.company, customer=other_customer, warehouse=self.warehouse,
            branch=other_branch, number=4, subtotal=Decimal("90"), total=Decimal("90"),
        )
        own_invoice.branch = own_branch
        own_invoice.save(update_fields=["branch"])
        self.assertIsNotNone(other_invoice.pk)

        self.client.force_authenticate(branch_user)
        response = self.secure_get(reverse("debt-customer-list"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], self.customer.name)
