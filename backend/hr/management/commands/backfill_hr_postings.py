"""Post the expenses for HR documents approved before postings existed.

Payroll runs and salary advances approved before hr.postings shipped have
no Expense behind them, so the income statement understates costs for
those months. This command posts them once, through the same functions
approval now uses, and is safe to re-run: documents that already carry an
expense are skipped by the OneToOne link.

Dry by default — prints what would be posted; `--yes` writes.
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Post expenses for payroll runs and salary advances approved before postings existed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true", help="Write the expenses (default: dry run)."
        )
        parser.add_argument(
            "--company", type=int, default=None, help="Limit to one company id."
        )

    def handle(self, *args, **options):
        from hr.models import PayrollRun, SalaryAdvance
        from hr.postings import (
            payroll_expense_amount, post_payroll_expense, post_salary_advance_expense,
        )

        scope = {"company_id": options["company"]} if options["company"] else {}
        runs = (
            PayrollRun.objects.filter(status=PayrollRun.APPROVED, expense__isnull=True, **scope)
            .order_by("company_id", "period")
        )
        advances = (
            SalaryAdvance.objects.filter(
                status=SalaryAdvance.APPROVED, expense__isnull=True, **scope
            )
            .select_related("employee")
            .order_by("company_id", "reviewed_at")
        )

        write = options["yes"]
        posted_runs = posted_advances = 0
        with transaction.atomic():
            # Advances first: a payroll month's amount subtracts advances
            # expensed in that month, so their rows must exist before the
            # run is priced.
            for advance in advances:
                self.stdout.write(
                    f"advance #{advance.pk} company={advance.company_id} "
                    f"{advance.employee.full_name} {advance.amount} "
                    f"({(advance.reviewed_at or advance.created_at):%Y-%m-%d})"
                )
                if write:
                    post_salary_advance_expense(advance, advance.reviewed_by)
                    posted_advances += 1
            for run in runs:
                amount = payroll_expense_amount(run)
                self.stdout.write(
                    f"payroll #{run.pk} company={run.company_id} {run.period:%Y-%m} "
                    f"{run.entries.count()} employees -> {amount}"
                )
                if write and amount > 0:
                    post_payroll_expense(run, run.approved_by)
                    posted_runs += 1
            if not write:
                transaction.set_rollback(True)

        if write:
            self.stdout.write(self.style.SUCCESS(
                f"Posted {posted_runs} payroll run(s) and {posted_advances} advance(s)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Dry run: {runs.count()} payroll run(s) and {advances.count()} advance(s) "
                "would be posted. Re-run with --yes to write."
            ))
