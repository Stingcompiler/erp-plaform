from django.urls import include, path
from rest_framework.routers import DefaultRouter

from sales.views import (
    CashDrawerMovementViewSet,
    CashShiftViewSet,
    CompanyBankAccountViewSet,
    CustomerViewSet,
    DebtCustomerListView,
    DebtSummaryView,
    InvoiceViewSet,
    PaymentViewSet,
    POSCheckoutView,
    QuotationViewSet,
    RefundViewSet,
    SalesOrderViewSet,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("bank-accounts", CompanyBankAccountViewSet, basename="bankaccount")
router.register("quotations", QuotationViewSet, basename="quotation")
router.register("sales-orders", SalesOrderViewSet, basename="salesorder")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")
router.register("refunds", RefundViewSet, basename="refund")
router.register("cash-shifts", CashShiftViewSet, basename="cashshift")
router.register(
    "drawer-movements", CashDrawerMovementViewSet, basename="drawermovement"
)

urlpatterns = [
    path("pos/checkout/", POSCheckoutView.as_view(), name="pos-checkout"),
    path("debts/customers/", DebtCustomerListView.as_view(), name="debt-customer-list"),
    path("debts/summary/", DebtSummaryView.as_view(), name="debt-summary"),
    path("", include(router.urls)),
]
