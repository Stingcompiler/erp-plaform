"""Seed the smallest company the browser end-to-end suite needs.

One company, one branch, one warehouse, the role set, a Business Owner and
a single stock-tracked product with 3 units on hand — few enough that a
two-line offline sale of 2 + 2 drives it negative, which is the case the
suite must prove reaches the attention badge. Idempotent: re-running
returns the same rows. Never meant for a real database; the email makes
that obvious.
"""
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company

EMAIL = "e2e-owner@vezano.test"
PASSWORD = "E2e-owner-passw0rd!"
SKU = "E2E-1"


class Command(BaseCommand):
    help = "Create the fixture company used by the Playwright offline suite."

    def handle(self, *args, **options):
        with transaction.atomic():
            call_command("seed_roles", verbosity=0)
            company, _ = Company.objects.get_or_create(
                name="E2E Shop",
                defaults={
                    "legal_name": "E2E Shop",
                    "email": EMAIL,
                    "business_type": Company.TYPE_SHOP,
                    "business_type_chosen": True,
                },
            )
            branch, _ = Branch.objects.get_or_create(
                company=company, code="MAIN", defaults={"name": "Main Branch"}
            )
            warehouse, _ = Warehouse.objects.get_or_create(
                company=company, name="Main Warehouse", defaults={"branch": branch}
            )
            owner = User.objects.filter(email=EMAIL).first()
            if owner is None:
                owner = User.objects.create_user(
                    email=EMAIL, password=PASSWORD, full_name="E2E Owner",
                    company=company, branch=branch,
                    role=Role.objects.get(name="Business Owner"),
                )
            product, created = Product.objects.get_or_create(
                company=company, sku=SKU,
                defaults={
                    "name": "E2E Gadget", "barcode": "6001234567890",
                    "sale_price": Decimal("25.00"), "cost_price": Decimal("10.00"),
                },
            )
            if created:
                StockMovement.objects.create(
                    company=company, product=product, warehouse=warehouse,
                    movement_type=StockMovement.ADJUSTMENT, quantity=Decimal("3"),
                    unit_cost=product.cost_price, reference_type="seed_e2e",
                )
        self.stdout.write(self.style.SUCCESS(
            f"E2E fixture ready: company {company.pk}, owner {owner.email}, "
            f"product {product.sku} (3 on hand)"
        ))
