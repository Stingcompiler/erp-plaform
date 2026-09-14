"""Create the customer's company and its first Business Owner on a standalone server.

On the hosted platform a company is born from an approved registration
request and the owner activates through an invitation link. Neither exists on
a customer's own server — the registration routes answer 404 there — so this
is the only supported way to get the first person in. It creates the company
(named after the installation's organisation unless told otherwise), a MAIN
branch, the fixed role set, and one active owner with a password that has
passed the project's validators.
"""

import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role, User
from config.deployment import get_deployment_config
from licensing.models import Installation
from org.models import Branch, Company

PASSWORD_ENV = "VEZANO_OWNER_PASSWORD"


class Command(BaseCommand):
    help = "Create the company and first Business Owner of a standalone installation."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--full-name", default="")
        parser.add_argument(
            "--company-name",
            default="",
            help="Defaults to the organisation recorded by bootstrap_standalone.",
        )
        parser.add_argument(
            "--currency", default="", help="ISO code; defaults to the company default."
        )
        parser.add_argument(
            "--shop",
            action="store_true",
            help="Single-shop layout instead of the multi-branch layout.",
        )
        parser.add_argument(
            "--password-env",
            action="store_true",
            help=f"Read the password from {PASSWORD_ENV} instead of prompting "
            "(for scripted acceptance runs only).",
        )

    def handle(self, *args, **options):
        if not get_deployment_config().is_standalone:
            raise CommandError(
                "create_owner is for standalone installations; hosted companies are "
                "provisioned from a registration request."
            )
        email = User.objects.normalize_email(options["email"].strip())
        if not email:
            raise CommandError("--email is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"{email} already belongs to an account.")

        installation = Installation.current()
        company_name = options["company_name"].strip() or installation.organisation_name
        if not company_name:
            raise CommandError(
                "No company name: pass --company-name or run bootstrap_standalone "
                "--organisation first."
            )

        password = self._read_password(options["password_env"], email, options["full_name"])

        with transaction.atomic():
            call_command("seed_roles", verbosity=0)
            owner_role = Role.objects.get(name="Business Owner")
            company = Company.objects.filter(is_active=True).order_by("pk").first()
            created_company = company is None
            if created_company:
                fields = {
                    "name": company_name,
                    "legal_name": company_name,
                    "email": email,
                    "business_type": Company.TYPE_SHOP
                    if options["shop"]
                    else Company.TYPE_ENTERPRISE,
                    "business_type_chosen": True,
                }
                if options["currency"]:
                    fields["currency"] = options["currency"].strip().upper()
                company = Company.objects.create(**fields)
            branch = (
                Branch.objects.filter(company=company, is_active=True)
                .order_by("pk")
                .first()
            )
            if branch is None:
                branch = Branch.objects.create(company=company, name="Main Branch", code="MAIN")
            owner = User.objects.create_user(
                email=email,
                password=password,
                full_name=options["full_name"].strip(),
                company=company,
                branch=branch,
                role=owner_role,
            )

        verb = "Created" if created_company else "Joined existing"
        self.stdout.write(self.style.SUCCESS(f"{verb} company: {company.name} (id {company.pk})"))
        self.stdout.write(self.style.SUCCESS(f"Business Owner: {owner.email} (id {owner.pk})"))

    def _read_password(self, from_env, email, full_name):
        if from_env:
            password = os.environ.get(PASSWORD_ENV, "")
            if not password:
                raise CommandError(f"--password-env given but {PASSWORD_ENV} is empty.")
        else:
            if not self.stdin_is_tty():
                raise CommandError(
                    "No terminal to prompt on; run interactively or use --password-env."
                )
            password = getpass.getpass("Owner password: ")
            if password != getpass.getpass("Owner password (again): "):
                raise CommandError("The passwords did not match.")
        probe = User(email=email, full_name=full_name)
        try:
            validate_password(password, user=probe)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))
        return password

    @staticmethod
    def stdin_is_tty():
        import sys

        return sys.stdin is not None and sys.stdin.isatty()
