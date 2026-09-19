"""The branch-visibility policy registry for company-owned resources.

Row-level branch scoping is opt-in: a viewset that sets ``branch_field``
narrows branch-scoped users to their own branch, and one that does not
exposes the whole company. Before this registry, leaving ``branch_field``
off was indistinguishable from deciding a resource is company-wide — the
2026-09 architecture review flagged Customer, Supplier, Bill and Expense
as exactly that ambiguity.

Every company-scoped viewset's model must now appear here with a policy:

- ``BRANCH``: rows belong to a branch (directly or through a relation) and
  branch-scoped users see only their own branch's rows.
- ``COMPANY_WIDE``: rows are deliberately shared across branches; the
  entry's reason documents why, so the decision is reviewable.

A system check (``vezano.E002``–``vezano.E005``) compares this registry
against the live viewsets on every ``manage.py check``/CI run: an
unregistered model, a policy that contradicts the viewset, or a stale
entry fails the build. Adding a resource therefore forces an explicit
branch decision instead of silently inheriting company-wide visibility.
"""

BRANCH = "branch"
COMPANY_WIDE = "company-wide"

# model label -> (policy, reason). The reason is documentation for
# COMPANY_WIDE entries: why every branch may see and use these rows.
REGISTRY = {
    # ----- shared master data: any branch serves the same parties -------
    "sales.Customer": (
        COMPANY_WIDE,
        "A customer may buy, pay and hold debt at any branch; splitting the "
        "ledger per branch would fragment their balance and credit limit.",
    ),
    "crm.CustomerGroup": (
        COMPANY_WIDE,
        "Pricing/discount groups apply to customers, who are company-wide.",
    ),
    "purchasing.Supplier": (
        COMPANY_WIDE,
        "Suppliers serve the whole company; their payable balance must stay "
        "one number regardless of which branch received the goods.",
    ),
    "inventory.Product": (
        COMPANY_WIDE,
        "One catalogue: stock per branch lives on warehouses/movements, not "
        "on the product row.",
    ),
    "inventory.Category": (COMPANY_WIDE, "Catalogue taxonomy."),
    "inventory.Brand": (COMPANY_WIDE, "Catalogue taxonomy."),
    "inventory.Unit": (COMPANY_WIDE, "Units of measure are company-wide."),
    "inventory.ProductPack": (COMPANY_WIDE, "Pack definitions follow the product."),
    "inventory.StockBatch": (
        COMPANY_WIDE,
        "Batches follow the product; their location is expressed by the "
        "branch-scoped movements that put them in a warehouse.",
    ),
    # ----- company-level finance documents ------------------------------
    "purchasing.Bill": (
        COMPANY_WIDE,
        "Payables are settled centrally; a bill may cover receipts of "
        "several branches and its due balance must be visible wherever a "
        "supplier payment is recorded.",
    ),
    "purchasing.SupplierPayment": (
        COMPANY_WIDE,
        "Follows Bill: payments against a central payable ledger.",
    ),
    "finance.Expense": (
        COMPANY_WIDE,
        "The expense book is company-level today; branch attribution is a "
        "reporting field, not a visibility wall.",
    ),
    "finance.Budget": (COMPANY_WIDE, "Budgets are set for the company."),
    "sales.CompanyBankAccount": (
        COMPANY_WIDE,
        "Bank accounts belong to the legal entity, not a branch.",
    ),
    # ----- org & HR policy objects --------------------------------------
    "org.Branch": (COMPANY_WIDE, "The branch list itself must be visible to pick from."),
    "org.Department": (COMPANY_WIDE, "Org structure is shared."),
    "org.ExchangeRate": (COMPANY_WIDE, "One rate prices the whole catalogue."),
    "hr.Position": (COMPANY_WIDE, "Job catalogue."),
    "hr.WorkPolicy": (COMPANY_WIDE, "Company-level HR policy."),
    "hr.LeaveAccrualPolicy": (COMPANY_WIDE, "Company-level HR policy."),
    "hr.PayrollRun": (
        COMPANY_WIDE,
        "Payroll is executed for the company in one run; per-branch cuts "
        "are reporting, and only payroll-capable roles reach it anyway.",
    ),
    # ----- public website content ---------------------------------------
    "website.Section": (COMPANY_WIDE, "The public site is one per company."),
    "website.FeaturedProduct": (COMPANY_WIDE, "The public site is one per company."),
    "website.WebsiteImage": (COMPANY_WIDE, "The public site is one per company."),
    # ----- branch-scoped operational records -----------------------------
    "accounts.User": (BRANCH, None),
    "crm.Lead": (BRANCH, None),
    "crm.FollowUp": (BRANCH, None),
    "crm.Note": (BRANCH, None),
    "hr.Employee": (BRANCH, None),
    "hr.Attendance": (BRANCH, None),
    "hr.Deduction": (BRANCH, None),
    "hr.EmployeeDocument": (BRANCH, None),
    "hr.LeaveAllowance": (BRANCH, None),
    "hr.LeaveRequest": (BRANCH, None),
    "hr.PerformanceRecord": (BRANCH, None),
    "hr.SalaryAdvance": (BRANCH, None),
    "inventory.Warehouse": (BRANCH, None),
    "inventory.StockMovement": (BRANCH, None),
    "inventory.StockAdjustment": (BRANCH, None),
    "inventory.StockTransfer": (BRANCH, None),
    "inventory.StockCount": (BRANCH, None),
    "purchasing.PurchaseOrder": (BRANCH, None),
    "purchasing.GoodsReceipt": (BRANCH, None),
    "returns.SalesReturn": (BRANCH, None),
    "returns.PurchaseReturn": (BRANCH, None),
    "returns.CreditNote": (BRANCH, None),
    "returns.DebitNote": (BRANCH, None),
    "sales.Invoice": (BRANCH, None),
    "sales.SalesOrder": (BRANCH, None),
    "sales.Quotation": (BRANCH, None),
    "sales.Payment": (BRANCH, None),
    "sales.Refund": (BRANCH, None),
    "sales.CashShift": (BRANCH, None),
    "sales.CashDrawerMovement": (BRANCH, None),
}


def iter_company_scoped_viewsets():
    """Yield every concrete viewset built on CompanyScopedQuerySetMixin.

    Importing the URL conf first guarantees every viewset module has been
    loaded, so ``__subclasses__`` sees them all.
    """
    import config.urls  # noqa: F401 - loads every app's views

    from core.scoping import CompanyScopedQuerySetMixin

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    for viewset in walk(CompanyScopedQuerySetMixin):
        if getattr(viewset, "queryset", None) is not None:
            yield viewset


def policy_violations():
    """Return human-readable registry violations (empty when consistent)."""
    problems = []
    exposed = {}
    for viewset in iter_company_scoped_viewsets():
        label = viewset.queryset.model._meta.label
        exposed.setdefault(label, []).append(viewset)
        entry = REGISTRY.get(label)
        if entry is None:
            problems.append(
                f"{label} ({viewset.__name__}) has no branch policy. Add it to "
                "core.branch_policy.REGISTRY as BRANCH or COMPANY_WIDE (with a reason)."
            )
            continue
        policy, _reason = entry
        branch_field = getattr(viewset, "branch_field", None)
        if policy == BRANCH and not branch_field:
            problems.append(
                f"{label} is registered BRANCH but {viewset.__name__} sets no "
                "branch_field, so branch users would see the whole company."
            )
        elif policy == COMPANY_WIDE and branch_field:
            problems.append(
                f"{label} is registered COMPANY_WIDE but {viewset.__name__} filters "
                f"by branch_field={branch_field!r}. Fix the registry or the viewset."
            )
    for label in REGISTRY:
        if label not in exposed:
            problems.append(
                f"{label} is in core.branch_policy.REGISTRY but no company-scoped "
                "viewset exposes it any more; remove the stale entry."
            )
    return problems
