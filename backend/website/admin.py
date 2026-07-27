from django.contrib import admin

from website.models import FeaturedProduct, Section, Website


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ["company", "business_name", "is_published", "updated_at"]
    list_filter = ["is_published"]
    inlines = [SectionInline]


admin.site.register([Section, FeaturedProduct])
