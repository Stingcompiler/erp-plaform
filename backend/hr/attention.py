"""Attention sources for HR and finance approvals."""

from core.attention import TONE_INFO, TONE_WARN, register, scope_branch


@register("hr", "hr", TONE_INFO)
def pending_leave_requests(user, since):
    from hr.models import LeaveRequest

    qs = LeaveRequest.objects.filter(
        company_id=user.company_id, status=LeaveRequest.PENDING, created_at__gt=since
    )
    return scope_branch(qs, user, field="employee__branch").count()


@register("finance", "finance", TONE_WARN)
def pending_salary_advances(user, since):
    from hr.models import SalaryAdvance

    qs = SalaryAdvance.objects.filter(
        company_id=user.company_id, status=SalaryAdvance.PENDING, created_at__gt=since
    )
    return scope_branch(qs, user, field="employee__branch").count()
