from django.contrib import admin

from sync.models import SyncBatch, SyncOperation


class SyncOperationInline(admin.TabularInline):
    model = SyncOperation
    extra = 0
    readonly_fields = [f.name for f in SyncOperation._meta.fields]
    can_delete = False


@admin.register(SyncBatch)
class SyncBatchAdmin(admin.ModelAdmin):
    list_display = [
        "batch_uuid", "company", "user", "operation_count",
        "applied_count", "duplicate_count", "error_count", "received_at",
    ]
    list_filter = ["company"]
    inlines = [SyncOperationInline]
    readonly_fields = [f.name for f in SyncBatch._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
