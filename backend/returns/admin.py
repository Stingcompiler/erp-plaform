from django.contrib import admin

from returns.models import (
    CreditNote,
    DebitNote,
    PurchaseReturn,
    SalesReturn,
    SalesReturnLine,
)


class SalesReturnLineInline(admin.TabularInline):
    model = SalesReturnLine
    extra = 0
    readonly_fields = [f.name for f in SalesReturnLine._meta.fields]
    can_delete = False


@admin.register(SalesReturn)
class SalesReturnAdmin(admin.ModelAdmin):
    list_display = ["id", "company", "invoice", "customer", "created_at"]
    list_filter = ["company"]
    inlines = [SalesReturnLineInline]

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register([PurchaseReturn, CreditNote, DebitNote])
