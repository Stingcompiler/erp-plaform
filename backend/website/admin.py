from django.contrib import admin

from website.models import FeaturedProduct, PlatformLead, Section, Website


@admin.register(PlatformLead)
class PlatformLeadAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "status", "source", "created_at"]
    list_filter = ["status", "source", "created_at"]
    search_fields = ["name", "email", "message"]
    readonly_fields = ["request_uuid", "created_at", "updated_at"]


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ["company", "business_name", "is_published", "updated_at"]
    list_filter = ["is_published"]
    inlines = [SectionInline]


admin.site.register([Section, FeaturedProduct])
