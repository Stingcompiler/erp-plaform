from django.contrib import admin

from org.models import Branch, Company, Department, TaxProfile


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    # business_type is on the list because it decides how much of the app a
    # tenant sees; without it here, whoever provisions companies cannot tell a
    # shop from an enterprise, or spot the ones that never answered the setup
    # question, without opening every record.
    list_display = [
        "name", "slug", "currency", "business_type",
        "business_type_chosen", "is_active",
    ]
    list_filter = ["business_type", "business_type_chosen", "is_active"]
    search_fields = ["name", "slug"]


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "company", "is_active"]
    list_filter = ["company", "is_active"]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "company", "branch"]
    list_filter = ["company"]


@admin.register(TaxProfile)
class TaxProfileAdmin(admin.ModelAdmin):
    list_display = ["company", "country", "invoice_format", "flat_tax_rate"]
