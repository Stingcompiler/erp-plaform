from django.contrib import admin

from purchasing.models import (
    Bill,
    GoodsReceipt,
    PurchaseOrder,
    Supplier,
    SupplierPayment,
)

admin.site.register([Supplier, PurchaseOrder])


def _readonly(model):
    return [f.name for f in model._meta.fields]


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ["id", "company", "supplier", "warehouse", "received_at"]
    list_filter = ["company"]
    readonly_fields = _readonly(GoodsReceipt)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ["id", "company", "supplier", "total", "status"]
    list_filter = ["company", "is_void"]
    readonly_fields = _readonly(Bill)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "supplier", "method", "amount", "verified_at"]
    list_filter = ["method", "company"]
    readonly_fields = _readonly(SupplierPayment)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
