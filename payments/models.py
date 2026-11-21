"""The ledger's money coming in: payments a superuser recorded by hand.

The first version tracks payments rather than processing them (PLAN.md,
Payments). Members pay by PayPal, Venmo, Zelle or cash as they already do,
and a superuser writes it down here.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models


class Payment(models.Model):
    """One payment received.

    `member` is optional on purpose: a payment from someone without an
    account (yet) must still be recorded, under the name as typed. Linking
    such a row to an account later only has to fill in `member`.

    The labels copy names at the time, as AdminAction does, so a row still
    reads properly after either account is deleted and its foreign key has
    gone null. `created_at` is the non-editable entry time PLAN.md asks for;
    `paid_on` is when the money changed hands, which may be earlier.
    """

    class Method(models.TextChoices):
        PAYPAL = "paypal", "PayPal"
        VENMO = "venmo", "Venmo"
        ZELLE = "zelle", "Zelle"
        CASH = "cash", "Cash"
        OTHER = "other", "Other"

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    # The member's name when linked, otherwise exactly what was typed.
    payer_name = models.CharField(max_length=150)
    # Decimal, never float: balances must add up to the cent.
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(max_length=16, choices=Method.choices)
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="payments_recorded",
    )
    recorded_by_label = models.CharField(max_length=320)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["-paid_on", "-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0")),
                name="payment_amount_positive",
            ),
        ]

    def __str__(self):
        return f"${self.amount} from {self.payer_name} ({self.get_method_display()}, {self.paid_on})"
