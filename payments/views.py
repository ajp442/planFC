"""Recording payments: one page, the form on top and what was recorded
below, so a run of payments can be entered one after another."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.utils.formats import date_format

from accounts.context_processors import display_name
from accounts.members import label, superuser_required

from .forms import PaymentForm
from .models import Payment

RECENT = 100


def _suggestions():
    """Every account, for the "Who paid" box to filter as you type. At the
    club's size (hundreds at most) sending the whole list beats a search
    request per keystroke, and matching stays instant on a slow phone."""
    users = get_user_model().objects.order_by("first_name", "last_name", "email")
    return [
        {"id": user.pk, "name": display_name(user), "email": user.email, "active": user.is_active}
        for user in users
    ]


@superuser_required
def payments(request):
    form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        member = data["member"]
        payment = Payment.objects.create(
            member=member,
            # A linked payment carries the account's own name, whatever was typed.
            payer_name=display_name(member) if member else data["payer_name"],
            amount=data["amount"],
            paid_on=data["paid_on"],
            method=data["method"],
            note=data["note"].strip(),
            recorded_by=request.user,
            recorded_by_label=label(request.user),
        )
        messages.success(
            request,
            f"Recorded ${payment.amount} from {payment.payer_name} "
            f"({payment.get_method_display()}, {date_format(payment.paid_on, 'M j, Y')}).",
        )
        # Redirect, so reloading the page can't record the payment twice.
        return redirect("payments")
    return render(request, "payments/payments.html", {
        "form": form,
        "suggestions": _suggestions(),
        "recent": Payment.objects.all()[:RECENT],
        "recent_limit": RECENT,
        "total_count": Payment.objects.count(),
    })
