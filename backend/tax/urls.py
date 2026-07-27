from django.urls import path

from tax.views import InvoiceDocumentView, TaxHandlersView, TaxProfileView

urlpatterns = [
    path("tax/profile/", TaxProfileView.as_view(), name="tax-profile"),
    path("tax/handlers/", TaxHandlersView.as_view(), name="tax-handlers"),
    path(
        "invoices/<int:invoice_id>/document/",
        InvoiceDocumentView.as_view(), name="invoice-document",
    ),
]
