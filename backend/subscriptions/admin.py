from django.contrib import admin

from subscriptions.models import (
    EntitlementOverride,
    PaymentAllocation,
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)


class AppendOnlyAdmin(admin.ModelAdmin):
    """Expose commercial evidence for support without allowing history rewrites."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_public", "is_active")
    search_fields = ("code", "name")


@admin.register(PlanVersion)
class PlanVersionAdmin(admin.ModelAdmin):
    list_display = (
        "plan",
        "version",
        "price",
        "currency",
        "billing_cycle",
        "published_at",
    )
    list_filter = ("billing_cycle", "currency", "is_legacy")

    def has_delete_permission(self, request, obj=None):
        return bool(obj is None or not (obj.published_at or obj.subscriptions.exists()))


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("company", "status", "plan_version", "starts_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("company__name",)


@admin.register(EntitlementOverride)
class EntitlementOverrideAdmin(admin.ModelAdmin):
    list_display = ("company", "allow_writes", "starts_at", "ends_at", "created_at")
    search_fields = ("company__name", "reason")


@admin.register(SubscriptionEvent)
class SubscriptionEventAdmin(AppendOnlyAdmin):
    list_display = (
        "subscription",
        "event_type",
        "from_status",
        "to_status",
        "created_at",
    )
    list_filter = ("event_type", "to_status")


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(AppendOnlyAdmin):
    list_display = ("number", "company", "status", "amount", "currency", "due_at")
    list_filter = ("status", "currency")
    search_fields = ("number", "company__name")


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(AppendOnlyAdmin):
    list_display = ("company", "amount", "currency", "method", "status", "created_at")
    list_filter = ("status", "method", "currency")
    search_fields = ("company__name", "reference_last4")


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(AppendOnlyAdmin):
    list_display = ("payment", "invoice", "amount", "created_at")
