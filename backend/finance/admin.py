from django.contrib import admin

from finance.models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("category", "amount", "method", "date", "company", "recorded_by")
    list_filter = ("company", "method", "category")
    search_fields = ("category", "description")
