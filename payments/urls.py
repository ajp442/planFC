from django.urls import path

from . import views

urlpatterns = [
    # Admins can look; only superusers can record and edit (views.py).
    # docs/ADMIN_GUIDE.md walks through them.
    path("payments/", views.payments, name="payments"),
    path("payments/changes/", views.payment_changes, name="payment_changes"),
    path("payments/<int:payment_id>/", views.payment_detail, name="payment_detail"),
]
