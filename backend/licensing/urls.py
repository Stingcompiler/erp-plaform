from django.urls import path

from licensing.views import LicenseView

urlpatterns = [path("license/", LicenseView.as_view(), name="license")]
