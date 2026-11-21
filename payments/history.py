"""Every change to a payment goes through here, so each one leaves an entry
in its history (models.PaymentChange) in the same transaction."""

from django.utils.formats import date_format

from accounts.members import label

from .models import PaymentChange

Action = PaymentChange.Action

# The fields a payment's history follows, in the order the form shows them.
FIELDS = {
    "payer_name": "Who paid",
    "member": "Account",
    "amount": "Amount",
    "paid_on": "Date paid",
    "method": "Method",
    "note": "Note",
}


def snapshot(payment):
    """A payment's values as text, the way people read them, so the history
    stays meaningful whatever later happens to the account or the code."""
    return {
        "payer_name": payment.payer_name,
        "member": label(payment.member) if payment.member else "",
        "amount": f"${payment.amount:.2f}",
        "paid_on": date_format(payment.paid_on, "M j, Y"),
        "method": payment.get_method_display(),
        "note": payment.note,
    }


def _record(actor, payment, action, values, reason=""):
    return PaymentChange.objects.create(
        payment_id=payment.pk,
        action=action,
        actor=actor,
        actor_label=label(actor) if actor else "Unknown",
        values=values,
        reason=reason[:320],
    )


def record_created(actor, payment):
    return _record(actor, payment, Action.CREATED, snapshot(payment))


def record_edited(actor, payment, before, reason=""):
    """`before` is snapshot() taken before the edit. Returns None, recording
    nothing, when nothing actually changed."""
    after = snapshot(payment)
    changed = {field: [before[field], after[field]] for field in FIELDS if before[field] != after[field]}
    if not changed:
        return None
    return _record(actor, payment, Action.EDITED, changed, reason)


def record_deleted(actor, payment):
    return _record(actor, payment, Action.DELETED, snapshot(payment))


def lines(change):
    """What a history entry says, one (label, text) pair per field."""
    if change.action == Action.EDITED:
        return [
            (FIELDS.get(field, field), f"{before or '(empty)'} → {after or '(empty)'}")
            for field, (before, after) in change.values.items()
        ]
    return [(FIELDS[field], change.values[field]) for field in FIELDS if change.values.get(field)]
