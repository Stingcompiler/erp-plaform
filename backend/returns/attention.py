"""Attention source for returns: quarantined lines waiting for a decision."""

from core.attention import TONE_INFO, register, scope_branch


@register("returns", "sales_returns", TONE_INFO)
def returns_awaiting_disposition(user, since):
    from returns.models import SalesReturnLine

    qs = SalesReturnLine.objects.filter(
        sales_return__company_id=user.company_id,
        disposition=SalesReturnLine.QUARANTINE,
        sales_return__created_at__gt=since,
    )
    return scope_branch(qs, user, field="sales_return__invoice__branch").count()
