"""When an admin links an unconfirmed account to the person's real one
(accounts.members.link), their payments move with it, each leaving an edit in
its history like any other change."""

from django.dispatch import receiver

from accounts.context_processors import display_name
from accounts.members import label
from accounts.signals import unconfirmed_account_linked

from . import history
from .models import Payment


@receiver(unconfirmed_account_linked)
def move_payments(sender, actor, unconfirmed, account, **kwargs):
    payments = list(Payment.objects.select_related("member", "method").filter(member=unconfirmed))
    reason = f"Unconfirmed account “{label(unconfirmed)}” linked to {label(account)}"
    for payment in payments:
        before = history.snapshot(payment)
        payment.member = account
        payment.payer_name = display_name(account)
        payment.save(update_fields=["member", "payer_name"])
        history.record_edited(actor, payment, before, reason)
    count = len(payments)
    return f"{count} payment{'' if count == 1 else 's'}" if count else ""
