from django.contrib import admin

from website.models import (
    FeaturedProduct, OwnerInvitation, PlatformLead, RegistrationRequest, Section, Website,
)


@admin.register(PlatformLead)
class PlatformLeadAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "status", "source", "created_at"]
    list_filter = ["status", "source", "created_at"]
    search_fields = ["name", "email", "message"]
    readonly_fields = ["request_uuid", "created_at", "updated_at"]


@admin.register(RegistrationRequest)
class RegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ["company_name", "email", "delivery_mode", "status", "created_at"]
    list_filter = ["delivery_mode", "status", "country", "created_at"]
    search_fields = ["company_name", "contact_name", "email"]
    readonly_fields = ["request_uuid", "reviewed_at", "created_at", "updated_at"]


@admin.register(OwnerInvitation)
class OwnerInvitationAdmin(admin.ModelAdmin):
    list_display = ["owner", "registration_request", "expires_at", "accepted_at", "revoked_at"]
    readonly_fields = ["token_hash", "accepted_at", "revoked_at", "created_at"]


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ["company", "business_name", "is_published", "updated_at"]
    list_filter = ["is_published"]
    inlines = [SectionInline]


admin.site.register([Section, FeaturedProduct])
