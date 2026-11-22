"""The ledger's money coming in: payments a superuser recorded by hand.

The first version tracks payments rather than processing them (PLAN.md,
Payments). Members pay by PayPal, Venmo, Zelle or cash as they already do,
and a superuser writes it down here.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from .money import money


class PaymentMethod(models.Model):
    """How money arrives: Venmo, Zelle, cash and so on.

    A table rather than fixed choices, so a superuser can add, rename or
    reorder methods in Database admin. A method a payment uses can't be
    deleted (PROTECT); untick `active` instead, and it stops being offered
    while old payments keep it. Renaming one leaves the history as it was
    written, since history.py copies the name at the time.
    """

    name = models.CharField(max_length=50, unique=True)
    active = models.BooleanField(default=True, help_text="Offered when recording a payment.")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Lower comes first.")

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


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

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    # The member's name when linked, otherwise exactly what was typed.
    payer_name = models.CharField(max_length=150)
    # Decimal, never float: balances must add up to the cent. Negative for a
    # refund or a correction in the other direction; never zero.
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    paid_on = models.DateField()
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="payments")
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
                condition=~models.Q(amount=Decimal("0")),
                name="payment_amount_not_zero",
            ),
        ]

    def __str__(self):
        return f"{money(self.amount)} from {self.payer_name} ({self.method}, {self.paid_on})"


class PaymentChange(models.Model):
    """One entry in a payment's history: recorded, edited or deleted, by
    whom, when, and the values involved. Written by history.py only.

    Append-only, for auditing. The model refuses to save an existing row or
    delete one, and a Postgres trigger (migration 0002) refuses UPDATE and
    DELETE outright, so not even Database admin or a stray query can rewrite
    it. That is also why neither foreign key has a database constraint or an
    on_delete action: deleting a payment or an account must not touch these
    rows. `payment_id` and `actor_id` stay as plain numbers, and the labels
    and values copied in keep the entry readable on its own.
    """

    class Action(models.TextChoices):
        CREATED = "created", "Recorded"
        EDITED = "edited", "Edited"
        DELETED = "deleted", "Deleted"

    payment = models.ForeignKey(
        Payment,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="changes",
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    # Null only for changes made outside a request (none yet).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    actor_label = models.CharField(max_length=320)
    # CREATED and DELETED: every field's value, as shown to people.
    # EDITED: only the fields that changed, as {field: [before, after]}.
    values = models.JSONField()
    reason = models.CharField(max_length=320, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Payment {self.payment_id} {self.get_action_display().lower()} by {self.actor_label}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Payment history can't be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Payment history can't be deleted.")
