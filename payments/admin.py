"""Payments in Database admin (superusers with 2FA, accounts/admin_site.py).

Recording happens in the app (views.py). Here rows can be looked at and, as a
last resort for a mistake, deleted, but never edited: a changed amount would
leave no trace that it was ever different.
"""

from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("paid_on", "payer_name", "amount", "method", "member", "recorded_by_label", "created_at")
    list_filter = ("method",)
    search_fields = ("payer_name", "note", "member__email")
    date_hierarchy = "paid_on"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
