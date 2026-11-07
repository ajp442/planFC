from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .pictures import make_profile_jpeg


class NameFields(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )


class SignupForm(NameFields):
    """Extra fields on allauth's sign-up form (ACCOUNT_SIGNUP_FORM_CLASS).

    allauth adds its own email and password fields and calls signup() once
    the user exists.
    """

    # Name first, the order people expect from other sign-up forms.
    field_order = ["first_name", "last_name", "email", "password1", "password2"]

    def signup(self, request, user):
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save(update_fields=["first_name", "last_name"])


class ProfileForm(NameFields):
    # A FileField, not an ImageField: ImageField would decode the upload
    # with Pillow before clean_picture() could turn a huge file away. All the
    # decoding happens in make_profile_jpeg(), after the size check.
    picture = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/*"}),
        help_text="A square crop of it is shown, 256 pixels across.",
    )
    remove_picture = forms.BooleanField(required=False, label="Remove my picture")

    def clean_picture(self):
        upload = self.cleaned_data.get("picture")
        if not upload:
            return None
        if upload.size > settings.PROFILE_PICTURE_MAX_UPLOAD_BYTES:
            raise ValidationError("That file is over 10 MB. Use a smaller photo.")
        upload.seek(0)
        return make_profile_jpeg(upload)
