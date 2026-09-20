from django.urls import path

from whatsapp.views import webhook

urlpatterns = [
    path("whatsapp/webhook/", webhook, name="whatsapp-webhook"),
]
