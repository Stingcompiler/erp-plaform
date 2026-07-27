from django.contrib import admin

from core.models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "action", "user", "company", "entity_type", "entity_id"]
    list_filter = ["action", "company"]
    search_fields = ["entity_type", "entity_id"]
    # Append-only (PROJECT_RULES Rule #9): the audit trail is never edited or
    # deleted through the admin.
    readonly_fields = [f.name for f in ActivityLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
