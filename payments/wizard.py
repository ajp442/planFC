"""Recording a payment one step at a time (superusers only):

    Who paid → Amount → Method & date → Review

Every step page starts with the same list of steps, which doubles as the
navigation: the current one stands out, and any step already reached can be
opened again. What has been entered so far is kept in the session (the
"draft") until the payment is recorded, so going back to a step loses
nothing. Leaving a step through the list also keeps whatever valid value was
typed on it (payment_wizard.js submits the step's form on the way out).

A payer who isn't listed is typed in on the first step and becomes an
unconfirmed account (accounts.members.create_unconfirmed_member) when the
payment is recorded, not before, so an abandoned draft leaves nothing behind.
"""

import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.formats import date_format

from accounts.context_processors import display_name
from accounts.members import create_unconfirmed_member, label, superuser_required
from accounts.models import UnconfirmedAccount

from . import history
from .forms import AmountForm, DetailsForm, NewMemberForm, NoteForm
from .models import Payment, PaymentMethod

User = get_user_model()

SESSION_KEY = "payment_draft"

STEPS = [
    ("who", "Who paid"),
    ("amount", "Amount"),
    ("details", "Method & date"),
    ("review", "Review"),
]
ORDER = [key for key, _ in STEPS]
URL_NAMES = {key: f"payment_new_{key}" for key in ORDER}


class Draft:
    """The payment being entered, as plain values in the session:
    member_id or new_name, amount, method_id, paid_on and note."""

    def __init__(self, request):
        self.request = request
        self.data = dict(request.session.get(SESSION_KEY) or {})
        self._member = self._method = None

    def save(self):
        self.request.session[SESSION_KEY] = self.data

    def clear(self):
        self.request.session.pop(SESSION_KEY, None)

    def update(self, **values):
        self.data.update(values)
        self.save()

    def member(self):
        """The account picked, or None if none was or it has since gone."""
        member_id = self.data.get("member_id")
        if member_id and (self._member is None or self._member.pk != member_id):
            self._member = User.objects.filter(pk=member_id).first()
        return self._member if member_id else None

    def new_name(self):
        return "" if self.data.get("member_id") else self.data.get("new_name", "")

    def amount(self):
        try:
            return Decimal(self.data["amount"])
        except (KeyError, InvalidOperation):
            return None

    def method(self):
        """The method picked, if it is still on offer."""
        method_id = self.data.get("method_id")
        if method_id and (self._method is None or self._method.pk != method_id):
            self._method = PaymentMethod.objects.filter(pk=method_id, active=True).first()
        return self._method if method_id else None

    def paid_on(self):
        try:
            return datetime.date.fromisoformat(self.data["paid_on"])
        except (KeyError, ValueError):
            return None

    def note(self):
        return self.data.get("note", "")

    def payer_name(self):
        member = self.member()
        return display_name(member) if member else self.new_name()

    def done(self, step):
        if step == "who":
            return bool(self.member() or self.new_name())
        if step == "amount":
            return self.amount() is not None
        if step == "details":
            return bool(self.method() and self.paid_on())
        return False

    def reachable(self, step):
        """A step can be opened once every step before it is filled in."""
        return all(self.done(earlier) for earlier in ORDER[:ORDER.index(step)])

    def first_open_step(self):
        return next((step for step in ORDER if not self.done(step)), "review")

    def summary(self, step):
        """What a step holds, in a few words, for the list of steps."""
        if not self.done(step):
            return ""
        if step == "who":
            return self.payer_name()
        if step == "amount":
            return f"${self.amount():.2f}"
        if step == "details":
            return f"{self.method()} · {date_format(self.paid_on(), 'M j')}"
        return ""


def _url(step):
    return reverse(URL_NAMES[step])


def _render(request, draft, step, template, context):
    steps = []
    for number, (key, title) in enumerate(STEPS, start=1):
        if key == step:
            state = "current"
        elif draft.reachable(key):
            state = "open"
        else:
            state = "locked"
        steps.append({
            "key": key, "title": title, "number": number, "state": state,
            "url": _url(key), "summary": draft.summary(key),
        })
    return render(request, template, {
        "steps": steps,
        "step": step,
        "step_title": dict(STEPS)[step],
        "draft": draft,
        **context,
    })


def _go_on(request, draft):
    """Where to after a step is saved: the step picked in the list of steps,
    if any, otherwise the next one still to fill in (Review once they all
    are, so a correction goes straight back to it)."""
    goto = request.POST.get("goto")
    if goto in ORDER and draft.reachable(goto):
        return redirect(_url(goto))
    return redirect(_url(draft.first_open_step()))


@superuser_required
def start(request):
    """Menu → Record a payment: always a fresh, empty payment."""
    Draft(request).clear()
    return redirect(_url("who"))


@superuser_required
def who(request):
    draft = Draft(request)
    if request.method == "POST":
        if request.POST.get("member"):
            member_id = request.POST["member"]
            member = User.objects.filter(pk=member_id).first() if member_id.isdigit() else None
            if member is None:
                messages.error(request, "That account no longer exists. Pick someone else.")
                return redirect(_url("who"))
            draft.update(member_id=member.pk, new_name="")
            return _go_on(request, draft)
        form = NewMemberForm(request.POST)
        if form.is_valid():
            draft.update(member_id=None, new_name=form.cleaned_data["new_name"])
            return _go_on(request, draft)
        if request.POST.get("goto"):
            return _go_on(request, draft)
        messages.error(request, "Pick someone from the list, or type a name to add them.")
        return redirect(_url("who"))

    query = request.GET.get("q", "").strip()
    users = User.objects.order_by("first_name", "last_name", "email")
    # Without JavaScript the box searches here; with it, payment_wizard.js
    # filters the whole list as you type and this never runs.
    for word in query.split():
        users = users.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word) | Q(email__icontains=word))
    users = list(users)
    unconfirmed = set(UnconfirmedAccount.objects.values_list("user_id", flat=True))
    chosen = draft.member()
    rows = [{
        "id": user.pk,
        "name": display_name(user),
        "email": user.email,
        "active": user.is_active,
        "unconfirmed": user.pk in unconfirmed,
        "chosen": chosen is not None and user.pk == chosen.pk,
        "search": f"{display_name(user)} {user.get_full_name()} {user.email}".lower(),
    } for user in users]
    return _render(request, draft, "who", "payments/wizard/who.html", {
        "rows": rows,
        "query": query,
        "total": User.objects.count(),
    })


def _step(request, step, form_class, initial, save):
    """Amount and Method & date: one small form each. `save` turns the
    form's cleaned data into draft values."""
    draft = Draft(request)
    if not draft.reachable(step):
        return redirect(_url(draft.first_open_step()))
    form = form_class(request.POST or None, initial=initial(draft))
    if request.method == "POST":
        if form.is_valid():
            draft.update(**save(form.cleaned_data))
            return _go_on(request, draft)
        if request.POST.get("goto"):
            # Leaving through the list of steps: an unfinished value is dropped.
            return _go_on(request, draft)
    return _render(request, draft, step, f"payments/wizard/{step}.html", {"form": form})


@superuser_required
def amount(request):
    return _step(
        request, "amount", AmountForm,
        initial=lambda draft: {"amount": draft.amount()},
        save=lambda data: {"amount": str(data["amount"])},
    )


@superuser_required
def details(request):
    def initial(draft):
        values = {"method": draft.method()}
        if draft.paid_on():
            values["paid_on"] = draft.paid_on()
        return values

    return _step(
        request, "details", DetailsForm,
        initial=initial,
        save=lambda data: {"method_id": data["method"].pk, "paid_on": data["paid_on"].isoformat()},
    )


@superuser_required
def review(request):
    draft = Draft(request)
    if not draft.reachable("review"):
        return redirect(_url(draft.first_open_step()))
    form = NoteForm(request.POST or None, initial={"note": draft.note()})
    if request.method == "POST" and form.is_valid():
        draft.update(note=form.cleaned_data["note"])
        if request.POST.get("goto"):
            return _go_on(request, draft)
        payment = _record(request, draft)
        draft.clear()
        messages.success(
            request,
            f"Recorded ${payment.amount} from {payment.payer_name} "
            f"({payment.method}, {date_format(payment.paid_on, 'M j, Y')}).",
        )
        # The list, so the new payment can be checked at the top of it.
        return redirect("payments")
    return _render(request, draft, "review", "payments/wizard/review.html", {
        "form": form,
        "member": draft.member(),
        "new_name": draft.new_name(),
        "amount": draft.amount(),
        "method": draft.method(),
        "paid_on": draft.paid_on(),
    })


@transaction.atomic
def _record(request, draft):
    member = draft.member() or create_unconfirmed_member(request, draft.new_name())
    payment = Payment(
        member=member,
        payer_name=display_name(member),
        amount=draft.amount(),
        paid_on=draft.paid_on(),
        method=draft.method(),
        note=draft.note(),
        recorded_by=request.user,
        recorded_by_label=label(request.user),
    )
    payment.save()
    history.record_created(request.user, payment)
    return payment
