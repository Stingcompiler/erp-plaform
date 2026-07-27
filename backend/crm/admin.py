from django.contrib import admin

from crm.models import CustomerGroup, FollowUp, Lead, Note


@admin.register(CustomerGroup)
class CustomerGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_active", "created_at")
    list_filter = ("company", "is_active")
    search_fields = ("name",)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "name", "company", "stage", "estimated_value", "assigned_to", "updated_at",
    )
    list_filter = ("company", "stage", "customer_group")
    search_fields = ("name", "contact_name", "email", "phone")


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("summary", "lead", "due_date", "done", "company")
    list_filter = ("company", "done")


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("lead", "created_by", "created_at", "company")
    list_filter = ("company",)
