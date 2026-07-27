from django.contrib import admin

from ops.models import BackupRecord, UserPreference


@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "status", "company", "record_count"]
    list_filter = ["kind", "status", "company"]
    readonly_fields = [f.name for f in BackupRecord._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(UserPreference)
