from django.urls import include, path
from rest_framework.routers import DefaultRouter

from finance.views import BudgetViewSet, ExpenseViewSet

router = DefaultRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("budgets", BudgetViewSet, basename="budget")

urlpatterns = [
    path("", include(router.urls)),
]
