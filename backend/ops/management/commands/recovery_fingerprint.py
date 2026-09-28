"""Counts and totals of the financial entities a restore must bring back.

Run before the drill against production and after it against the restored
copy; the two outputs must match line for line (``--json`` for a diff-able
form). The ten entities are the ones money or stock hangs on — a restore
that loses any of them is not a restore.
"""
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Sum


def _entities():
    from hr.models import PayrollEntry
    from inventory.models import StockMovement
    from purchasing.models import Bill, PurchaseOrder, SupplierPayment
    from returns.models import CreditNote, DebitNote
    from sales.models import Invoice, Payment, Refund

    # (label, model, field summed, company lookup) — the sum is the entity's
    # money (or stock) column.
    return [
        ("invoices", Invoice, "total", "company"),
        ("payments", Payment, "amount", "company"),
        ("refunds", Refund, "amount", "company"),
        ("credit_notes", CreditNote, "amount", "company"),
        ("debit_notes", DebitNote, "amount", "company"),
        ("purchase_orders", PurchaseOrder, "total", "company"),
        ("bills", Bill, "total", "company"),
        ("supplier_payments", SupplierPayment, "amount", "company"),
        ("stock_movements", StockMovement, "quantity", "company"),
        ("payroll_entries", PayrollEntry, "net_salary", "payroll_run__company"),
    ]


def fingerprint(company=None):
    rows = []
    for label, model, field, scope in _entities():
        qs = model.objects.all()
        if company is not None:
            qs = qs.filter(**{scope: company})
        agg = qs.aggregate(n=Count("pk"), total=Sum(field))
        # Fixed 3 dp so SQLite and Postgres print the same string.
        total = Decimal(agg["total"] or 0).quantize(Decimal("0.001"))
        rows.append({"entity": label, "count": agg["n"], "sum": str(total)})
    return rows


class Command(BaseCommand):
    help = (
        "Print counts and totals of the ten financial entities (restore drill check). "
        "With --full and --company: the whole company fingerprint (every table's rows and "
        "decimal totals, stock per lot, balances, report outputs), to --out and/or "
        "compared with a fingerprint taken before (--compare)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", help="Company id, slug or exact name; default: "
                                              "whole database.")
        parser.add_argument("--json", action="store_true", help="Machine-readable output.")
        parser.add_argument("--full", action="store_true",
                            help="The complete company fingerprint (needs --company).")
        parser.add_argument("--start", help="Report period start, YYYY-MM-DD (with --full).")
        parser.add_argument("--end", help="Report period end, YYYY-MM-DD (with --full).")
        parser.add_argument("--out", help="Write the --full fingerprint to this file.")
        parser.add_argument("--compare", help="A --full fingerprint file taken before; "
                                              "every difference is listed, exit 1 if any.")

    def handle(self, *args, **options):
        company = None
        if options["company"]:
            from org.models import Company

            ref = options["company"]
            company = (
                (Company.objects.filter(pk=ref).first() if ref.isdigit() else None)
                or Company.objects.filter(slug=ref).first()
                or Company.objects.filter(name=ref).first()
            )
            if company is None:
                raise CommandError(f"No company matches {ref!r}.")
        if options["full"]:
            return self._full(company, options)
        rows = fingerprint(company)
        if options["json"]:
            self.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        width = max(len(r["entity"]) for r in rows)
        scope = f"company {company.name} (#{company.pk})" if company else "whole database"
        self.stdout.write(f"Recovery fingerprint — {scope}")
        for r in rows:
            self.stdout.write(f"  {r['entity']:<{width}}  count={r['count']:>8}  sum={r['sum']}")

    def _full(self, company, options):
        from datetime import date

        from django.core.serializers.json import DjangoJSONEncoder
        from django.utils import timezone

        from ops import company_fingerprint

        if company is None:
            raise CommandError("--full needs --company.")
        before = None
        if options["compare"]:
            with open(options["compare"], encoding="utf-8") as handle:
                before = json.load(handle)
        # Comparing: the period the earlier fingerprint was taken for.
        period = (before or {}).get("period") or {}
        try:
            end = options["end"] or period.get("end")
            end = date.fromisoformat(end) if end else timezone.localdate()
            start = options["start"] or period.get("start")
            start = date.fromisoformat(start) if start else end.replace(month=1, day=1)
        except ValueError as exc:
            raise CommandError("Use YYYY-MM-DD for --start and --end.") from exc
        data = company_fingerprint.fingerprint(company, start, end)
        data["period"] = {"start": start.isoformat(), "end": end.isoformat()}
        # Through JSON either way, so a live fingerprint and one read back
        # from a file compare like for like.
        text = json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False, indent=1,
                          sort_keys=True)
        if options["out"]:
            with open(options["out"], "w", encoding="utf-8") as handle:
                handle.write(text)
        if before is not None:
            problems = company_fingerprint.diff(before, json.loads(text))
            if problems:
                for line in problems:
                    self.stdout.write(f"  {line}")
                raise CommandError(f"{len(problems)} difference(s) from {options['compare']}.")
            self.stdout.write(self.style.SUCCESS(
                f"Fingerprint of {company.name} (#{company.pk}) matches {options['compare']}."
            ))
        elif not options["out"]:
            self.stdout.write(text)
