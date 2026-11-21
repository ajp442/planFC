from django.urls import path

from . import views

urlpatterns = [
    # Superusers only. docs/ADMIN_GUIDE.md walks through it.
    path("payments/", views.payments, name="payments"),
]
