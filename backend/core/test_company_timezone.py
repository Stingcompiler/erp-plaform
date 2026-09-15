"""The business day is the company's day, not UTC's.

A sale at 23:30 Khartoum time (21:30 UTC) belongs to "today" for a Khartoum
shop. Before the company zone existed every "today" was UTC's, so that sale
showed up in tomorrow's dashboard and the shift close counted it wrong.
"""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from accounts.models import Role, User
from core.timezone import activate_for_user, is_valid_timezone
from inventory.models import Warehouse
from org.models import Branch, Company
from sales.models import Invoice


def login_client(user, password):
    client = APIClient()
    response = client.post(reverse("auth-login"), {"email": user.email, "password": password}, format="json")
    assert response.status_code == 200, response.data
    return client


class CompanyTimezoneTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Khartoum Shop", timezone="Africa/Khartoum")
        self.branch = Branch.objects.create(company=self.company, name="Main", code="MAIN")
        self.warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        role, _ = Role.objects.get_or_create(name="Business Owner", defaults={"scope_level": Role.SCOPE_BUSINESS})
        self.owner = User.objects.create_user(
            email="owner@khartoum.test", password="passw0rd123", company=self.company, branch=self.branch, role=role,
        )

    def test_default_zone_is_khartoum_and_validated(self):
        self.assertEqual(Company.objects.create(name="Other").timezone, "Africa/Khartoum")
        self.assertTrue(is_valid_timezone("Asia/Riyadh"))
        self.assertFalse(is_valid_timezone("Mars/Olympus"))

    def test_owner_can_change_zone_but_not_to_nonsense(self):
        client = login_client(self.owner, "passw0rd123")
        url = reverse("company-profile")
        bad = client.patch(url, {"timezone": "Mars/Olympus"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("timezone", bad.data)
        good = client.patch(url, {"timezone": "Asia/Riyadh"}, format="json")
        self.assertEqual(good.status_code, 200, good.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.timezone, "Asia/Riyadh")

    def test_late_evening_sale_is_todays_sale_for_the_company(self):
        # 23:30 today in Khartoum (UTC+2) is 21:30 UTC today — same UTC date,
        # so pin the case where the two calendars disagree: 01:00 Khartoum
        # = 23:00 UTC the previous day.
        khartoum = ZoneInfo("Africa/Khartoum")
        today_local = timezone.now().astimezone(khartoum).date()
        sold_at = timezone.datetime(today_local.year, today_local.month, today_local.day, 1, 0, tzinfo=khartoum)
        if sold_at > timezone.now():
            sold_at -= timedelta(days=1)
            today_local -= timedelta(days=1)
        Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=self.warehouse, number=1,
            total=Decimal("40"), subtotal=Decimal("40"), issued_at=sold_at,
        )
        client = login_client(self.owner, "passw0rd123")
        response = client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200, response.data)
        # Only meaningful when the UTC date differs; assert on the company calendar.
        self.assertEqual(sold_at.astimezone(khartoum).date(), today_local)
        if sold_at.astimezone(ZoneInfo("UTC")).date() != today_local:
            self.assertEqual(Decimal(response.data["sections"]["sales"]["today_total"]), Decimal("40"))

    def test_zone_does_not_leak_between_requests(self):
        activate_for_user(self.owner)
        self.assertEqual(str(timezone.get_current_timezone()), "Africa/Khartoum")
        # An anonymous request on the same thread must not inherit it.
        APIClient().get(reverse("health-check"))
        self.assertEqual(str(timezone.get_current_timezone()), "UTC")
