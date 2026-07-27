from django.urls import include, path
from rest_framework.routers import DefaultRouter

from returns.views import (
    CreditNoteViewSet,
    DebitNoteViewSet,
    PurchaseReturnViewSet,
    SalesReturnViewSet,
)

router = DefaultRouter()
router.register("sales-returns", SalesReturnViewSet, basename="salesreturn")
router.register("purchase-returns", PurchaseReturnViewSet, basename="purchasereturn")
router.register("credit-notes", CreditNoteViewSet, basename="creditnote")
router.register("debit-notes", DebitNoteViewSet, basename="debitnote")

urlpatterns = [
    path("", include(router.urls)),
]
