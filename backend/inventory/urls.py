from django.urls import include, path
from rest_framework.routers import DefaultRouter

from inventory.views import (
    BrandViewSet,
    CategoryViewSet,
    ProductViewSet,
    StockAdjustmentViewSet,
    StockCountViewSet,
    StockBatchViewSet,
    StockMovementViewSet,
    StockTransferViewSet,
    UnitViewSet,
    WarehouseViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("units", UnitViewSet, basename="unit")
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("products", ProductViewSet, basename="product")
router.register("stock-batches", StockBatchViewSet, basename="stockbatch")
router.register("stock-movements", StockMovementViewSet, basename="stockmovement")
router.register("stock-adjustments", StockAdjustmentViewSet, basename="stockadjustment")
router.register("stock-transfers", StockTransferViewSet, basename="stocktransfer")
router.register("stock-counts", StockCountViewSet, basename="stockcount")

urlpatterns = [
    path("", include(router.urls)),
]
