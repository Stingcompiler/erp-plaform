from django.urls import path

from reports.operational import (
    CrmReport, PaymentReconciliationReport, PurchaseReturnsReport, SalesReturnsReport,
)

from reports.views import (
    APAgingReport,
    ARAgingReport,
    CashFlowReport,
    CashFlowForecastReport,
    CfoKpiReport,
    PayablesDueReport,
    IncomeStatementReport,
    HrSummaryReport,
    PayrollReport,
    InventoryValuationReport,
    ReceivablesDueReport,
    ProfitSummaryReport,
    PurchasesSummaryReport,
    SalesByProductReport,
    SalesSummaryReport,
    ZakatReport,
)

urlpatterns = [
    path("reports/hr-summary/", HrSummaryReport.as_view(), name="report-hr-summary"),
    path("reports/payroll/", PayrollReport.as_view(), name="report-payroll"),
    path(
        "reports/sales-summary/",
        SalesSummaryReport.as_view(), name="report-sales-summary",
    ),
    path(
        "reports/sales-by-product/",
        SalesByProductReport.as_view(), name="report-sales-by-product",
    ),
    path(
        "reports/inventory-valuation/",
        InventoryValuationReport.as_view(), name="report-inventory-valuation",
    ),
    path("reports/ar-aging/", ARAgingReport.as_view(), name="report-ar-aging"),
    path("reports/ap-aging/", APAgingReport.as_view(), name="report-ap-aging"),
    path(
        "reports/purchases-summary/",
        PurchasesSummaryReport.as_view(), name="report-purchases-summary",
    ),
    path(
        "reports/profit-summary/",
        ProfitSummaryReport.as_view(), name="report-profit-summary",
    ),
    path(
        "reports/income-statement/",
        IncomeStatementReport.as_view(), name="report-income-statement",
    ),
    path(
        "reports/cash-flow/",
        CashFlowReport.as_view(), name="report-cash-flow",
    ),
    path(
        "reports/receivables-due/",
        ReceivablesDueReport.as_view(), name="report-receivables-due",
    ),
    path(
        "reports/payables-due/",
        PayablesDueReport.as_view(), name="report-payables-due",
    ),
    path("reports/cfo-kpis/", CfoKpiReport.as_view(), name="report-cfo-kpis"),
    path("reports/zakat/", ZakatReport.as_view(), name="report-zakat"),
    path("reports/sales-returns/", SalesReturnsReport.as_view(), name="report-sales-returns"),
    path(
        "reports/purchase-returns/", PurchaseReturnsReport.as_view(),
        name="report-purchase-returns",
    ),
    path(
        "reports/payment-reconciliation/", PaymentReconciliationReport.as_view(),
        name="report-payment-reconciliation",
    ),
    path("reports/crm/", CrmReport.as_view(), name="report-crm"),
    path(
        "reports/cash-flow-forecast/",
        CashFlowForecastReport.as_view(), name="report-cash-flow-forecast",
    ),
]
