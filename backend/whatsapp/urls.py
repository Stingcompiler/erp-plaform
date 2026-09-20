from django.urls import path

from whatsapp.views import WhatsAppSettingsView, WhatsAppTestSendView, webhook

urlpatterns = [
    path("whatsapp/webhook/", webhook, name="whatsapp-webhook"),
    path("whatsapp/settings/", WhatsAppSettingsView.as_view(), name="whatsapp-settings"),
    path("whatsapp/test-send/", WhatsAppTestSendView.as_view(), name="whatsapp-test-send"),
]
