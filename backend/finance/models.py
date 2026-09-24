"""
Finance domain (HR/Finance expansion): Expense.

Company-scoped like every other module. Revenue is NOT stored here — it's
derived from sales (Invoices) so there's a single source of truth (no parallel
ledger that can drift). Expenses are the new records the Finance Department
manages; the dashboard combines derived revenue with recorded expenses to show
net funds. Payments to gateways are never involved (Rule #3).
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce


class Expense(models.Model):
    """A recorded company expense (rent, utilities, payroll, supplies, …)."""

    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    METHOD_CHOICES = [
        (CASH, "Cash"),
        (BANK_TRANSFER, "Bank transfer"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="expenses"
    )
    category = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=16, choices=METHOD_CHOICES, default=CASH)
    date = models.DateField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="recorded_expenses",
        null=True,
        blank=True,
    )
    # HR postings. A finance-approved payroll run and an approved salary
    # advance each post exactly one expense, so payroll reaches the income
    # statement and the cash-flow views like every other cost. PROTECT: the
    # HR document is the evidence behind the figure and must outlive it.
    payroll_run = models.OneToOneField(
        "hr.PayrollRun", on_delete=models.PROTECT, null=True, blank=True,
        related_name="expense",
    )
    salary_advance = models.OneToOneField(
        "hr.SalaryAdvance", on_delete=models.PROTECT, null=True, blank=True,
        related_name="expense",
    )
    # Petty cash paid out of a till (transport, tea, a small repair). The
    # drawer movement takes it out of the expected cash; this row puts it in
    # the income statement and cash flow, which only ever read expenses.
    drawer_movement = models.OneToOneField(
        "sales.CashDrawerMovement", on_delete=models.PROTECT, null=True, blank=True,
        related_name="expense",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Category labels the HR postings use; the P&L groups by category, so
    # keeping these fixed keeps payroll one line there.
    CATEGORY_PAYROLL = "Payroll"
    CATEGORY_SALARY_ADVANCE = "Salary advances"
    CATEGORY_PETTY_CASH = "Petty cash"

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.category}: {self.amount}"


class Budget(models.Model):
    """
    A spending/revenue plan for a period, at **category** level.

    Deliberately not tied to ledger accounts: the system has no general ledger
    (a post-v1 decision), and expenses are already categorised, so budgeting on
    the same categories keeps plan and actual directly comparable. If a GL is
    ever introduced, categories map onto accounts without reshaping this table.

    A budget only takes effect once approved — draft figures must never silently
    become the baseline that variance is measured against.
    """

    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (APPROVED, "Approved"),
        (ARCHIVED, "Archived"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="budgets"
    )
    name = models.CharField(max_length=255)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    note = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_budgets",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_budgets",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_start", "name"]

    def __str__(self):
        return f"{self.name} ({self.period_start}–{self.period_end})"

    @property
    def is_active(self):
        return self.status == self.APPROVED

    def planned_total(self):
        return self.lines.aggregate(
            t=Coalesce(Sum("planned_amount"), Decimal("0"))
        )["t"]


class BudgetLine(models.Model):
    """One planned amount for a category within a budget."""

    EXPENSE = "expense"
    REVENUE = "revenue"
    KIND_CHOICES = [(EXPENSE, "Expense"), (REVENUE, "Revenue")]

    budget = models.ForeignKey(
        Budget, on_delete=models.CASCADE, related_name="lines"
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=EXPENSE)
    # Matches Expense.category for expense lines; free text for revenue targets.
    category = models.CharField(max_length=120)
    planned_amount = models.DecimalField(max_digits=16, decimal_places=2)

    class Meta:
        ordering = ["kind", "category"]
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "kind", "category"],
                name="uniq_budget_line_per_category",
            )
        ]

    def __str__(self):
        return f"{self.category}: {self.planned_amount}"
