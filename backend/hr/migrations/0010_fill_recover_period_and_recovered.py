"""Fill the new payroll columns for rows written before them.

* PayrollEntry.advances_recovered — what the entry really took from net pay:
  min(advances_total, base - deductions), never below zero. The old
  calculation clipped net pay at zero and wrote the rest off silently; the
  remainder is now owed and recovered by the next payroll.
* SalaryAdvance.recover_period — the approval month in the company's
  calendar, moved on past any month whose payroll was already approved
  when the advance was.
"""

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import migrations
from django.utils import timezone


def _zone(company):
    try:
        return ZoneInfo(str(getattr(company, "timezone", "") or ""))
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return timezone.get_default_timezone()


def _next_month(period):
    return date(period.year + (period.month == 12), (period.month % 12) + 1, 1)


def fill(apps, schema_editor):
    PayrollEntry = apps.get_model("hr", "PayrollEntry")
    SalaryAdvance = apps.get_model("hr", "SalaryAdvance")
    PayrollRun = apps.get_model("hr", "PayrollRun")

    for entry in PayrollEntry.objects.filter(advances_recovered__isnull=True).iterator():
        room = max(Decimal("0"), entry.base_salary - entry.deductions_total)
        entry.advances_recovered = min(entry.advances_total, room)
        entry.save(update_fields=["advances_recovered"])

    advances = SalaryAdvance.objects.filter(
        status="approved", recover_period__isnull=True
    ).select_related("company")
    for advance in advances.iterator():
        moment = advance.reviewed_at or advance.created_at
        period = timezone.localtime(moment, _zone(advance.company)).date().replace(day=1)
        approved = {
            run.period: run.approved_at
            for run in PayrollRun.objects.filter(
                company_id=advance.company_id, status="approved", period__gte=period
            )
        }
        while period in approved and (approved[period] is None or approved[period] <= moment):
            period = _next_month(period)
        advance.recover_period = period
        advance.save(update_fields=["recover_period"])


class Migration(migrations.Migration):
    dependencies = [("hr", "0009_hr_review_payroll_fields")]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
