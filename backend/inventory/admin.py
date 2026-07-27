from django.contrib import admin

from inventory.models import (
    Brand,
    Category,
    Product,
    StockAdjustment,
    StockBatch,
    StockMovement,
    StockTransfer,
    Unit,
    Warehouse,
)

admin.site.register([Category, Brand, Unit, Warehouse, StockBatch])


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["sku", "name", "company", "reorder_level", "is_active"]
    list_filter = ["company", "is_active", "track_batches"]
    search_fields = ["sku", "name", "barcode"]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        "created_at", "movement_type", "product", "warehouse", "quantity",
    ]
    list_filter = ["movement_type", "company"]
    search_fields = ["product__sku", "reference_type", "reference_id"]
    # Append-only (Rule #9): the ledger is immutable through the admin.
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register([StockAdjustment, StockTransfer])
