from django.urls import include, path
from rest_framework.routers import DefaultRouter

from purchasing.views import (
    BillViewSet,
    GoodsReceiptCreateView,
    GoodsReceiptViewSet,
    PurchaseOrderViewSet,
    SupplierPaymentViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchaseorder")
router.register("goods-receipts", GoodsReceiptViewSet, basename="goodsreceipt")
router.register("bills", BillViewSet, basename="bill")
router.register("supplier-payments", SupplierPaymentViewSet, basename="supplierpayment")

urlpatterns = [
    path("receivings/", GoodsReceiptCreateView.as_view(), name="receiving-create"),
    path("", include(router.urls)),
]
