from django.urls import path

from . import views, wizard

urlpatterns = [
    # Admins can look; only superusers can record and edit (views.py).
    # docs/ADMIN_GUIDE.md walks through them.
    path("payments/", views.payments, name="payments"),
    path("payments/changes/", views.payment_changes, name="payment_changes"),
    path("payments/<int:payment_id>/", views.payment_detail, name="payment_detail"),
    # Recording one, step by step (wizard.py). /new/ starts a fresh one.
    path("payments/new/", wizard.start, name="payment_new"),
    path("payments/new/who/", wizard.who, name="payment_new_who"),
    path("payments/new/amount/", wizard.amount, name="payment_new_amount"),
    path("payments/new/details/", wizard.details, name="payment_new_details"),
    path("payments/new/review/", wizard.review, name="payment_new_review"),
]
