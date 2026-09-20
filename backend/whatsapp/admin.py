from django.contrib import admin

from whatsapp.models import WhatsAppAccount, WhatsAppMessage, WhatsAppWebhookEvent


@admin.register(WhatsAppAccount)
class WhatsAppAccountAdmin(admin.ModelAdmin):
    list_display = ("display_phone", "phone_number_id", "company", "is_active", "last_event_at")
    search_fields = ("display_phone", "phone_number_id", "company__name")
    # The token is a credential: editable, never listed.
    exclude = ()


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "direction", "phone", "message_type", "status", "company")
    list_filter = ("direction", "status", "message_type")
    search_fields = ("phone", "wa_message_id", "text")
    readonly_fields = ("raw",)


@admin.register(WhatsAppWebhookEvent)
class WhatsAppWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("received_at", "account", "messages", "statuses", "unknown_numbers")
    readonly_fields = ("payload",)
