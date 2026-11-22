"""Payments: admins can look, superusers can also record and edit.

- /payments/ lists payments. Superusers record a new one step by step from
  /payments/new/ (wizard.py), which comes back here when it is done.
- /payments/<id>/ shows one payment and its history; superusers edit it there.
- /payments/changes/ is the history of every payment, for auditing.

Every change goes through history.py in the same transaction, and nobody can
edit that history (models.PaymentChange).
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.context_processors import display_name
from accounts.members import admin_required, is_active_superuser
from accounts.models import UnconfirmedAccount

from . import history
from .forms import PaymentEditForm
from .models import Payment, PaymentChange

RECENT = 100
CHANGES_SHOWN = 200


def _suggestions():
    """Every account, for the "Who paid" box to filter as you type. At the
    club's size (hundreds at most) sending the whole list beats a search
    request per keystroke, and matching stays instant on a slow phone."""
    users = get_user_model().objects.order_by("first_name", "last_name", "email")
    unconfirmed = set(UnconfirmedAccount.objects.values_list("user_id", flat=True))
    return [
        {
            "id": user.pk, "name": display_name(user), "email": user.email,
            "active": user.is_active, "unconfirmed": user.pk in unconfirmed,
        }
        for user in users
    ]


def _apply(payment, data):
    """Copies the form's values onto the payment. A linked payment carries
    the account's own name, whatever was typed."""
    member = data["member"]
    payment.member = member
    payment.payer_name = display_name(member) if member else data["payer_name"]
    payment.amount = data["amount"]
    payment.paid_on = data["paid_on"]
    payment.method = data["method"]
    payment.note = data["note"].strip()


def _entries(changes):
    return [{"change": change, "lines": history.lines(change)} for change in changes]


@admin_required
def payments(request):
    can_record = is_active_superuser(request.user)
    recent = Payment.objects.select_related("method").annotate(
        edits=Count("changes", filter=Q(changes__action=PaymentChange.Action.EDITED)),
    )[:RECENT]
    return render(request, "payments/payments.html", {
        "can_record": can_record,
        "recent": recent,
        "recent_limit": RECENT,
        "total_count": Payment.objects.count(),
    })


@admin_required
def payment_detail(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("member", "method"), pk=payment_id)
    can_edit = is_active_superuser(request.user)
    if request.method == "POST" and not can_edit:
        raise PermissionDenied
    form = None
    if can_edit:
        if request.method == "POST":
            form = PaymentEditForm(request.POST, current_method=payment.method_id)
        else:
            form = PaymentEditForm.for_payment(payment)
    if request.method == "POST" and form.is_valid():
        before = history.snapshot(payment)
        _apply(payment, form.cleaned_data)
        with transaction.atomic():
            change = history.record_edited(request.user, payment, before, form.cleaned_data["reason"].strip())
            if change:
                payment.save()
        if change:
            messages.success(request, "Saved. The history below keeps what it was before.")
        else:
            messages.info(request, "Nothing was changed.")
        return redirect("payment_detail", payment_id=payment.pk)
    return render(request, "payments/detail.html", {
        "payment": payment,
        "form": form,
        "can_edit": can_edit,
        "suggestions": _suggestions() if can_edit else None,
        "history": _entries(payment.changes.all()),
    })


@admin_required
def payment_changes(request):
    changes = list(PaymentChange.objects.all()[:CHANGES_SHOWN])
    live_ids = set(Payment.objects.filter(pk__in=[c.payment_id for c in changes]).values_list("pk", flat=True))
    return render(request, "payments/changes.html", {
        "history": _entries(changes),
        "live_ids": live_ids,
        "shown": CHANGES_SHOWN,
    })
