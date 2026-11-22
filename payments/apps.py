from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self):
        # Connects the receiver that moves payments when an unconfirmed
        # account is linked to a real one.
        from . import linking  # noqa: F401
