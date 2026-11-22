from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import PaymentMethod

# The longest name accepted for a new unconfirmed member: first and last
# name are 150 characters each on Django's User.
NEW_NAME_MAX = 300


def amount_field():
    return forms.DecimalField(
        label="Amount ($)",
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={
            "inputmode": "decimal", "step": "0.01", "min": "0.01", "placeholder": "0.00",
        }),
    )


def paid_on_field():
    return forms.DateField(
        label="Date paid",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )


def method_field(current=None):
    """The methods on offer (Database admin → Payment methods), plus the one
    a payment already has, so editing it doesn't force a change of method
    after that one was retired."""
    methods = Q(active=True)
    if current is not None:
        methods |= Q(pk=getattr(current, "pk", current))
    return forms.ModelChoiceField(
        label="Method",
        queryset=PaymentMethod.objects.filter(methods),
        empty_label="Choose…",
    )


def clean_amount(amount):
    # "7" becomes 7.00, so it reads the same everywhere it is shown.
    return amount.quantize(Decimal("0.01"))


def clean_paid_on(paid_on):
    if paid_on > timezone.localdate():
        raise ValidationError("That date is in the future.")
    return paid_on


class PaymentForm(forms.Form):
    """A payment's details, in the order they are usually read off a phone:
    who, how much, when, how, and anything else worth knowing. Used for
    editing; recording goes through the steps in wizard.py."""

    payer_name = forms.CharField(
        label="Who paid",
        max_length=150,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "autocapitalize": "words",
            "spellcheck": "false",
            "placeholder": "Start typing a name",
        }),
    )
    # Filled in by payments.js when a suggestion is picked, and cleared again
    # as soon as the name is edited. Empty means "not linked to an account".
    member = forms.IntegerField(required=False, widget=forms.HiddenInput)
    note = forms.CharField(
        label="Note",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 2, "placeholder": "Optional: paying for a friend, a donation, a check number…",
        }),
    )

    field_order = ["payer_name", "member", "amount", "paid_on", "method", "note"]

    def __init__(self, *args, current_method=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"] = amount_field()
        self.fields["paid_on"] = paid_on_field()
        self.fields["method"] = method_field(current_method)
        self.order_fields(self.field_order)
        # Today in the club's time zone, worked out per request, not at import.
        self.fields["paid_on"].initial = timezone.localdate()

    def clean_payer_name(self):
        return " ".join(self.cleaned_data["payer_name"].split())

    def clean_amount(self):
        return clean_amount(self.cleaned_data["amount"])

    def clean_member(self):
        member_id = self.cleaned_data.get("member")
        if member_id is None:
            return None
        member = get_user_model().objects.filter(pk=member_id).first()
        if member is None:
            raise ValidationError("That account no longer exists. Pick the name again.")
        return member

    def clean_paid_on(self):
        return clean_paid_on(self.cleaned_data["paid_on"])

    @classmethod
    def for_payment(cls, payment):
        """The form filled in with a payment's current values, for editing."""
        return cls(current_method=payment.method_id, initial={
            "payer_name": payment.payer_name,
            "member": payment.member_id,
            "amount": payment.amount,
            "paid_on": payment.paid_on,
            "method": payment.method_id,
            "note": payment.note,
        })


class PaymentEditForm(PaymentForm):
    """A superuser correcting a payment. Every field can change; the history
    keeps what each one was before."""

    reason = forms.CharField(
        label="Reason for the change",
        required=False,
        max_length=320,
        widget=forms.TextInput(attrs={"placeholder": "Optional, kept in the history"}),
    )

    field_order = PaymentForm.field_order + ["reason"]


# --- Recording, one step at a time (wizard.py) ----------------------------------

class NewMemberForm(forms.Form):
    """Step 1, when the payer isn't in the list: the name for a new
    unconfirmed account, made when the payment is recorded."""

    new_name = forms.CharField(max_length=NEW_NAME_MAX)

    def clean_new_name(self):
        name = " ".join(self.cleaned_data["new_name"].split())
        if not name:
            raise ValidationError("Type the name of the person who paid.")
        return name


class AmountForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"] = amount_field()
        self.fields["amount"].widget.attrs["autofocus"] = True

    def clean_amount(self):
        return clean_amount(self.cleaned_data["amount"])


class DetailsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"] = method_field()
        self.fields["method"].widget.attrs["autofocus"] = True
        self.fields["paid_on"] = paid_on_field()
        self.fields["paid_on"].initial = timezone.localdate()

    def clean_paid_on(self):
        return clean_paid_on(self.cleaned_data["paid_on"])


class NoteForm(forms.Form):
    note = forms.CharField(
        label="Comment",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3, "placeholder": "Optional: paying for a friend, a donation, a check number…",
        }),
    )

    def clean_note(self):
        return self.cleaned_data["note"].strip()
