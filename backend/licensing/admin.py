from django.contrib import admin

from licensing.models import Installation, LicenseActivation


@admin.register(Installation)
class InstallationAdmin(admin.ModelAdmin):
    list_display = (
        "installation_id",
        "organisation_name",
        "deployment_mode",
        "installed_at",
    )
    readonly_fields = (
        "singleton_key",
        "installation_id",
        "deployment_mode",
        "installed_at",
    )

    def has_add_permission(self, request):
        return not Installation.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LicenseActivation)
class LicenseActivationAdmin(admin.ModelAdmin):
    list_display = (
        "license_id",
        "organisation_name",
        "kind",
        "activated_at",
        "superseded_at",
    )
    list_filter = ("kind",)
    search_fields = ("license_id", "organisation_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
