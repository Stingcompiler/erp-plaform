from django.contrib import admin

from sales.models import (
    CompanyBankAccount,
    Customer,
    Invoice,
    InvoiceLine,
    Payment,
    Quotation,
    SalesOrder,
)

admin.site.register([Customer, CompanyBankAccount, Quotation, SalesOrder])


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in InvoiceLine._meta.fields]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number_display", "company", "customer", "total", "status"]
    list_filter = ["company", "is_void"]
    inlines = [InvoiceLineInline]
    readonly_fields = [f.name for f in Invoice._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["invoice", "method", "amount", "verified_at"]
    list_filter = ["method", "company"]
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
