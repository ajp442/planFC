from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Payment


class PaymentForm(forms.Form):
    """Recording one payment, in the order it is usually read off a phone:
    who, how much, when, how, and anything else worth knowing."""

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
    amount = forms.DecimalField(
        label="Amount ($)",
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={
            "inputmode": "decimal", "step": "0.01", "min": "0.01", "placeholder": "0.00",
        }),
    )
    paid_on = forms.DateField(
        label="Date paid",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    method = forms.ChoiceField(
        label="Method",
        choices=Payment.Method.choices,
        widget=forms.RadioSelect,
    )
    note = forms.CharField(
        label="Note",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 2, "placeholder": "Optional: paying for a friend, a donation, a check number…",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Today in the club's time zone, worked out per request, not at import.
        self.fields["paid_on"].initial = timezone.localdate()

    def clean_payer_name(self):
        return " ".join(self.cleaned_data["payer_name"].split())

    def clean_amount(self):
        # "7" becomes 7.00, so it reads the same everywhere it is shown.
        return self.cleaned_data["amount"].quantize(Decimal("0.01"))

    def clean_member(self):
        member_id = self.cleaned_data.get("member")
        if member_id is None:
            return None
        member = get_user_model().objects.filter(pk=member_id).first()
        if member is None:
            raise ValidationError("That account no longer exists. Pick the name again.")
        return member

    def clean_paid_on(self):
        paid_on = self.cleaned_data["paid_on"]
        if paid_on > timezone.localdate():
            raise ValidationError("That date is in the future.")
        return paid_on

    @classmethod
    def for_payment(cls, payment):
        """The form filled in with a payment's current values, for editing."""
        return cls(initial={
            "payer_name": payment.payer_name,
            "member": payment.member_id,
            "amount": payment.amount,
            "paid_on": payment.paid_on,
            "method": payment.method,
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
