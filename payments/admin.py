"""Payments in Database admin (superusers with 2FA, accounts/admin_site.py).

Recording and editing happen in the app (views.py), where every change is
written to the payment's history. Here payments can be looked at and, as a
last resort for a duplicate, deleted one at a time; the deletion is written
to the history too. The history itself is view-only, here as everywhere.
"""

from django.contrib import admin

from . import history
from .models import Payment, PaymentChange


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

    def get_actions(self, request):
        # One at a time, through delete_model(), so each deletion is recorded.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def delete_model(self, request, obj):
        history.record_deleted(request.user, obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


@admin.register(PaymentChange)
class PaymentChangeAdmin(admin.ModelAdmin):
    list_display = ("created_at", "payment_id", "action", "actor_label", "reason")
    list_filter = ("action",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
